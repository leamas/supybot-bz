###
# Copyright (c) 2009, Mike Mueller
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

''' Overall configuration reflecting plugins.bz.* config variables. '''

# pylint: disable=W0612

from supybot import conf
from supybot import registry

_URL_TEXT = ''' Bugzilla url e. g.,
 https://bugzilla.redhat.com/xmlrpc.cgi. '''

_CHANNELS_TXT = """ The channels receiving data from a watch. """

_QUERY_TXT = """ A bugzilla query string selecting the bugs being
 monitored e. g., 'product:Fedora component:fedora-review'."""

_FIRSTBUG_TXT = """The id of the first bug we care about,
 older bugs are silently dropped. Use to limit the number of bugs
 retrieved from bugzilla and related timeouts."""

_WATCH_OPTIONS = {
    'url':
        lambda: registry.String('', _URL_TEXT),
    'firstbug':
        lambda: registry.NonNegativeInteger(0, _FIRSTBUG_TXT),
    'channels':
        lambda: registry.SpaceSeparatedListOfStrings('', _CHANNELS_TXT),
    'query':
        lambda: registry.SpaceSeparatedListOfStrings('*', _QUERY_TXT),
}


def global_option(option):
    ''' Return an overall plugin option (registered at load time). '''
    return conf.supybot.plugins.get('bz').get(option)


def watch_option(watchname, option):
    ''' Return a watch-specific option, registering on the fly. '''
    watches = global_option('watches')
    try:
        watch = watches.get(watchname)
    except registry.NonExistentRegistryEntry:
        watch = conf.registerGroup(watches, watchname)
    try:
        return watch.get(option)
    except registry.NonExistentRegistryEntry:
        conf.registerGlobalValue(watch, option, _WATCH_OPTIONS[option]())
        return watch.get(option)


def unregister_watch(watchname):
    ''' Unregister  watch from registry. '''
    try:
        global_option('watches').unregister(watchname)
    except registry.NonExistentRegistryEntry:
        pass


def configure(advanced):
    ''' Advanced configuration, not used. '''
    conf.registerPlugin('Bz', True)


Bz = conf.registerPlugin('Bz')

conf.registerGroup(Bz, 'watches',
    help = "Internal list of watches (hands off, please).")

conf.registerGlobalValue(Bz, 'watchlist',
        registry.SpaceSeparatedListOfStrings([],
           "Internal list of configured watches, please don't touch "))

conf.registerGlobalValue(Bz, 'pollPeriod',
    registry.NonNegativeInteger(600, """ How often (in seconds) that
  bugzillas will be polled for changes. Zero disables periodic polling."""))


# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:
