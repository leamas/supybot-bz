###
# Copyright (c) 2011-2012, Mike Mueller <mike.mueller@panopticdev.com>
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
###

"""
A Supybot plugin that monitors a bugzilla instance(s) for changes in
certain bugs.  See README for configuration and usage.

This code is threaded. A separate thread run the potential long-running
fetching of data from bugzilla. The rest is handled by the main thread.

The critical sections are:
   - The _Watch instances, locked with an instance attribute lock.
   - The _Watches instance (watches) in the Bz class, locked by a
     internal lock (all methods are synchronized).

See: The supybot docs, notably ADVANCED_PLUGIN_CONFIG.rst and
     ADVANCED_PLUGIN_TESTING.rst.
"""

import os
import pickle
import ssl

import bugzilla

from supybot import callbacks
from supybot import log
from supybot import schedule
from supybot import world
from supybot.commands import commalist
from supybot.commands import optional
from supybot.commands import threading
from supybot.commands import time
from supybot.commands import wrap
from supybot.utils.str import nItems

import config


HELP_URL = 'https://github.com/leamas/supybot-bz'

_FIELDS = ['id', 'status', 'url', 'short_desc', 'attachments', 'longdescs']


def _bug_change_msg(bug):
    ''' Message printed for bugs changing status. '''
    msg = 'Bug ' + str(bug.id) + ': ' + bug.short_desc + ', new state: ' \
           + bug.status + ' - ' + bug.url
    return msg


def _bug_commented_msg(bug):
    ''' Message printed for bugs being commented. '''
    msg = 'Bug ' + str(bug.id) + ': ' + bug.short_desc  \
           + ', new comment from: ' + bug.longdescs[-1]['author'] \
           + ' - ' + bug.url
    return msg


def _snarf_msg(bug):
    ''' Message printed if bug id found in irc chat. '''
    msg = "%d: %s - %s - %d attachments - %d comments - %s" % \
              (bug.id, bug.short_desc, bug.status, len(bug.attachments),
                  len(bug.longdescs), bug.url)
    return msg


def _on_bug_change(oldbug, newbug, irc):
    ''' Report diffs in newbug state compared to oldbug. '''
    if oldbug.status != newbug.status:
        irc.reply(_bug_change_msg(newbug))
    elif len(oldbug.longdescs) != len(newbug.longdescs):
        irc.reply(_bug_commented_msg(newbug))


class BzPluginError(Exception):
    ''' Common base class for exceptions in this plugin. '''
    pass


class _PickleBug:
    ''' Simple, non-proxy bug data container. '''
    pass


class _Watch(object):
    """
    Represents a watch. The watch is a critical zone
    accessed both by main thread and the Fetcher, guarded by the
    lock attribute.
    """

    def __init__(self, watchname):
        """
        Initialize a watch with the given name. Setup data is read
        from supybot registry.
        """

        self.log = log.getPluginLogger('bzwatch.bug')
        self.name = watchname
        self.lock = threading.Lock()
        self.bugs = None
        self.bugzilla = None
        url = config.watch_option(watchname, 'url').value
        if not url.startswith('file://'):
            try:
                self.bugzilla = bugzilla.Bugzilla(url=url)
            except IOError:
                self.log.error("Cannot create Bugzilla for " + str(url))
        self._load(url)

    def _get_query(self):
        ''' Convert querystrings to bz query format, throws ValueError. '''
        # pylint: disable=E1101
        dict_ = {}
        for item in config.watch_option(self.name, 'query').value:
            key, value = item.split(':', 1)
            dict_[key] = value
        dict_['include_fields'] = list(_FIELDS)
        return self.bugzilla.build_query(**dict_)   # pylint: disable=W0142

    def _load(self, url):
        ''' Load bugs from pickled data on disk '''
        path = os.path.join('bz.' + self.name + '.pickle')
        try:
            with open(path, 'r') as f:
                self.bugs = pickle.load(f)
            self.log.debug("_load: loaded %d bugs" % len(self.bugs))
        except (IOError, ValueError):
            self.bugs = []
            self.log.warning("Cannot load bugs from: " + path,
                              exc_info=True)
            self._dump()

    def _dump(self):
        ''' Dump bugs as pickled data to disk. '''
        path = os.path.join('bz.' + self.name + '.pickle')
        try:
            with open(path, 'w') as f:
                pickle.dump(self.bugs, f)
        except IOError:
            self.log.warning("Cannot dump bugs to : " + path)

    def _read_from_bz(self):
        ''' Return list of new, loaded bugs from url source. '''
        url = config.watch_option(self.name, 'url').value
        firstbug = config.watch_option(self.name, 'firstbug').value
        if url.startswith('file://'):
            path = url.replace('file://', '')
            with open(path, 'r') as f:
                bugs = pickle.load(f)
            self.log.debug("Taking testdata from: " + path)
            if firstbug:
                bugs = [b for b in bugs if b.id >= firstbug]
        else:
            query = self._get_query()
            try:
                # pylint: disable=E1101
                start = time.time()
                proxybugs = self.bugzilla.query(query)
                self.log.debug("Found: " + str(time.time() - start))
                if firstbug:
                    proxybugs = [b for b in proxybugs if b.id > firstbug]
                bugs = self.bugzilla.getbugs([b.id for b in proxybugs])
                self.log.debug("Loaded: " + str(time.time() - start))
            except ssl.SSLError as e:
                raise BzPluginError(str(e))
        return bugs

    def _store_bugs(self, bz_bugs):
        ''' Save bugs as PickleBug so that, well, pickle works. '''
        bugs = []
        for bz_bug in bz_bugs:
            bug = _PickleBug()
            for field in _FIELDS:
                setattr(bug, field, getattr(bz_bug, field))
            bugs.append(bug)
        self.bugs = bugs
        self._dump()

    def update(self):
        ''' Read bugs data from bugzilla. '''
        with self.lock:
            bz_bugs = self._read_from_bz()
            self._store_bugs(bz_bugs)

    def poll(self, poll_cb, break_func=lambda: False):
        """Contact bugzilla and update bugs appropriately. For
        each changed bug call poll_cb(oldbug, newbug);
        break this loop if break_func returns True
        """
        with self.lock:
            newbugs = self._read_from_bz()
            for i in range(0, len(newbugs)):
                if break_func():
                    return
                if not newbugs[i]:
                    continue
                try:
                    poll_cb(self.bugs[i], newbugs[i])
                except IndexError:
                    pass
            self._store_bugs(newbugs)

    @staticmethod
    def create(watchname, url, channels):
        ''' Create a new initially inactive watch, '''
        config.watch_option(watchname, 'url').setValue(url)
        config.watch_option(watchname, 'channels').setValue(channels)
        config.watch_option(watchname, 'firstbug').setValue(0)
        return _Watch(watchname)


class _Watches(object):
    '''
    Synchronized access to the list of _Watch and related conf settings.
    '''

    def __init__(self):
        self._lock = threading.Lock()
        self._list = []
        for watch in config.global_option('watchlist').value:
            self.append(_Watch(watch))

    def get_by_name(self, name):
        ''' Return watch with given name, or None. '''
        with self._lock:
            watches = [w for w in self._list if w.name == name]
            return watches[0] if watches else None

    def set(self, watches):
        ''' Update the repository list. '''
        with self._lock:
            self._list = watches
            watchlist = [w.name for w in watches]
            config.global_option('watchlist').setValue(watchlist)

    def append(self, watch):
        ''' Add new watch to shared list. '''
        with self._lock:
            self._list.append(watch)
            watchlist = [w.name for w in self._list]
            config.global_option('watchlist').setValue(watchlist)

    def remove(self, watch):
        ''' Remove watch from list. '''
        with self._lock:
            self._list.remove(watch)
            watchlist = [w.name for w in self._list]
            config.global_option('watchlist').setValue(watchlist)
            config.unregister_watch(watch.name)

    def get(self):
        ''' Return copy of the watch list. '''
        with self._lock:
            return list(self._list)

    length = property(lambda self: len(self._list))   # pylint: disable=W0212


class _Fetcher(threading.Thread):
    """
    Thread polling watches for changes.
    """

    def __init__(self, watches, fetch_done_cb):
        self.watches = watches
        self.log = log.getPluginLogger('bz.fetcher')
        threading.Thread.__init__(self)
        self._shutdown = False
        self._callback = fetch_done_cb

    def stop(self):
        """
        Shut down the thread as soon as possible. May take some time if
        inside a long-running fetch operation.
        """
        self._shutdown = True

    def run(self):
        start = time.time()
        for watch in self.watches.get():
            try:
                watch.poll(self._callback, lambda: self._shutdown)
            except BzPluginError as e:
                self.log.warning(
                    "Cannot poll: %s :%s" % (watch.name, str(e)))
        self.log.debug("Exiting bz thread, elapsed: " +
                       str(time.time() - start))


class _Scheduler(object):
    '''
    Handles scheduling of fetch tasks.

    '''

    def __init__(self, watches, fetch_done_cb):
        self.watches = watches
        self._fetch_done_cb = fetch_done_cb
        self.log = log.getPluginLogger('bz.conf')
        self.fetcher = None
        self.reset()

    fetching_alive = \
        property(lambda self: self.fetcher and self.fetcher.is_alive())

    def reset(self, die=False):
        '''
        Revoke scheduled events, start a new fetch right now unless
        die or testing.
        '''
        try:
            schedule.removeEvent('watchfetch')
        except KeyError:
            pass
        if die or world.testing:
            return
        pollPeriod = config.global_option('pollPeriod').value
        if not pollPeriod:
            self.log.debug(
                "WatchScheduling: ignoring reset with pollPeriod 0")
            return
        schedule.addPeriodicEvent(lambda: _Scheduler.start_fetch(self),
                                  pollPeriod,
                                  'watchfetch',
                                  not self.fetching_alive)
        self.log.debug("Restarted watch polling")

    def stop(self):
        '''
        Stop  the Fetcher. Never allow an exception to propagate since
        this is called in die()
        '''
        # pylint: disable=W0703
        if self.fetching_alive:
            try:
                self.fetcher.stop()
                self.fetcher.join()    # This might take time, but it's safest.
            except Exception, e:
                self.log.error('Stopping fetcher: %s' % str(e),
                               exc_info=True)
        self.reset(die = True)

    def start_fetch(self):
        ''' Start next Fetcher run. '''
        if not config.global_option('pollPeriod').value:
            return
        if self.fetching_alive:
            self.log.error("Fetcher running when about to start!")
            self.fetcher.stop()
            self.fetcher.join()
            self.log.info("Stopped fetcher")
        self.fetcher = _Fetcher(self.watches, self._fetch_done_cb)
        self.fetcher.start()

    @staticmethod
    def run_callback(callback, id_):
        ''' Run the callback 'now' on main thread. '''
        try:
            schedule.removeEvent(id_)
        except KeyError:
            pass
        schedule.addEvent(callback, time.time(), id_)


class Bz(callbacks.PluginRegexp):
    """ See the README.md file to configure and use this plugin."""
    # pylint: disable=R0904,R0913

    threaded = True
    unaddressedRegexps = ['snarf_bug']

    def __init__(self, irc):

        def poll_cb(oldbug, newbug):
            ''' Report diffs in newbug state compared to oldbug. '''
            _on_bug_change(oldbug, newbug, irc)

        callbacks.PluginRegexp.__init__(self, irc)
        self.watches = _Watches()
        self.scheduler = _Scheduler(self.watches, poll_cb)
        if hasattr(irc, 'reply'):
            n = self.watches.length
            irc.reply('Bz reinitialized with %s.' % nItems(n, 'watch'))

    def die(self):
        ''' Stop all threads.  '''
        self.scheduler.stop()
        callbacks.PluginRegexp.die(self)

    def snarf_bug(self, irc, msg, match):
        ".*([0-9]{6,7}).*"
        # docstring (ab)used for plugin introspection. Called by
        # framework if string matching regexp above is found in chat.
        bugid = int(match.group(1))
        for w in self.watches.get():
            found = [b for b in w.bugs if b.id == bugid]
            if found:
                irc.reply(_snarf_msg(found[0]))
                return

    def watchadd(self, irc, msg, args, name, url, channels):
        """ <watch name> <url> <channel [,channnel...]>

        Add a new watch with name, url and a list of channels to feed.
        """
        if self.watches.get_by_name(name):
            irc.reply("Error: watch exists")
            return
        w = _Watch.create(name, url, channels)
        self.watches.append(w)
        irc.replySuccess()

    watchadd = wrap(watchadd, ['owner',
                               'somethingWithoutSpaces',
                               'somethingWithoutSpaces',
                               commalist('somethingWithoutSpaces')])

    def watchquery(self, irc, msg, args, name, query):
        """ <watch name> <query string>

        Sets the  bugzilla query string for a watch e. g.,
        'watchquery my-watch product:Gnome component:gnome-shell'
        """
        watch = self.watches.get_by_name(name)
        if not watch:
            irc.reply("Error: no such watch.")
            return
        config.watch_option(name, 'query').setValue(query.split())
        try:
            watch.update()
        except BzPluginError as e:
            irc.reply("Error: Can't read bug data: " + str(e))
        else:
            irc.reply("Watching %d bugs." % len(watch.bugs))

    watchquery = wrap(watchquery,
                      ['owner', 'somethingWithoutSpaces', 'text'])

    def watchkill(self, irc, msg, args, name):
        """ <watch name>

        Removes an existing watch given it's name.
        """
        watch = self.watches.get_by_name(name)
        if not watch:
            irc.reply("Error: no such watch.")
            return
        self.watches.remove(watch)
        irc.reply('Watch deleted.')

    watchkill = wrap(watchkill, ['owner', 'somethingWithoutSpaces'])

    def watchlist(self, irc, msg, args):
        """ <takes no arguments>

        Print list of watches.
        """
        watches = config.global_option('watchlist').value
        if watches:
            irc.reply("Watches: " + ', '.join(watches))
        else:
            irc.reply("No configured watches")

    watchlist = wrap(watchlist, [])

    def watchconf(self, irc, msg, args, watchname):
        """ <watch name>

        Display configuration for a watch given it's name.
        """
        w = self.watches.get_by_name(watchname)
        if not w:
            irc.reply("Error: no such watch.")
            return
        url = config.watch_option(w.name, 'url').value
        query = config.watch_option(watchname, 'query').value
        channels = config.watch_option(watchname, 'channels').value
        irc.reply("url: %s, channels: %s, query: %s"
                   % (url, ','.join(channels), query))

    watchconf = wrap(watchconf, ['owner', 'somethingWithoutSpaces'])

    def watchpoll(self, irc, msg, args, watchname):
        """ [watch name]

        Poll a named watch, or all if none given.
        """

        def watch_cb(oldbug, newbug):
            ''' Report if newbug is changed compared to oldbug. '''
            _on_bug_change(oldbug, newbug, irc)

        if watchname:
            watch = self.watches.get_by_name(watchname)
            if not watch:
                irc.reply("Error: no such watch.")
                return
            watches = [watch]
        else:
            watches = self.watches.get()
        for w in watches:
            try:
                w.poll(watch_cb)
            except BzPluginError as e:
                irc.reply("Error updating " + w.name + ': ' + str(e))
        irc.reply("Polled " + nItems(len(watches), "watch") + '.')

    watchpoll = wrap(watchpoll, ['owner', optional('somethingWithoutSpaces')])

    def watchhelp(self, irc, msg, args):
        """ Takes no arguments

        Display the help url.
        """
        irc.reply('See: ' + HELP_URL)

    watchhelp = wrap(watchhelp, [])


Class = Bz


# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:
