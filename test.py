# Copyright (c) 2011-2012, Mike Mueller
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

# Unused wildcard imports:
# pylint: disable=W0614,W0401
# Missing docstrings:
# pylint: disable=C0111
# supybot's typenames are irregular
# pylint: disable=C0103
# Too many public methods:
# pylint: disable=R0904

# http://sourceforge.net/apps/mediawiki/gribble/index.php?title=Plugin_testing

from supybot.test import *
from supybot import conf

import os
import shutil
import time

# are not getting responses, you may need to bump this higher.
LOOP_TIMEOUT = 1.0


class PluginTestCaseUtilMixin(object):
    "Some additional utilities used in this plugin's tests."

    def _feedMsgLoop(self, query, timeout_=None, **kwargs):
        "Send a message and wait for a list of responses instead of just one."
        if timeout_ is None:
            timeout_ = LOOP_TIMEOUT
        responses = []
        start = time.time()
        r = self._feedMsg(query, timeout=timeout_, **kwargs)
        # Sleep off remaining time, then start sending empty queries until
        # the replies stop coming.
        remainder = timeout_ - (time.time() - start)
        time.sleep(remainder if remainder > 0 else 0)
        query = conf.supybot.reply.whenAddressedBy.chars()[0]
        while r:
            responses.append(r)
            r = self._feedMsg(query, timeout=0, **kwargs)
        return responses

    def assertResponses(self, query, expectedResponses, **kwargs):
        "Run a command and assert that it returns the given list of replies."
        responses = self._feedMsgLoop(query, **kwargs)
        responses = map(lambda m: m.args[1], responses)
        self.assertEqual(sorted(responses), sorted(expectedResponses),
                         '\nActual:\n%s\n\nExpected:\n%s' %
                         ('\n'.join(responses), '\n'.join(expectedResponses)))
        return responses


class BzReloadTest(ChannelPluginTestCase, PluginTestCaseUtilMixin):
    channel = '#test'
    plugins = ('Bz', 'User', 'Config')

    def setUp(self, nick='test'):      # pylint: disable=W0221
        ChannelPluginTestCase.setUp(self)
        conf.supybot.plugins.Bz.pollPeriod.setValue(0)
        conf.supybot.plugins.Bz.watchlist.setValue([])
        self.assertNotError('register suptest suptest', private=True)
        expected = ['Bz reinitialized with 0 watches.',
                    'The operation succeeded.'
        ]
        self.assertResponses('reload Bz', expected)

    def testReloadOne(self):
        self.assertNotError('identify suptest suptest', private=True)
        self.assertResponse(
            'watchadd test1' +
                ' file://plugins/Bz/testdata/bz.test1.pickle.0 #test',
            'The operation succeeded.')
        expected = ['Bz reinitialized with 1 watch.',
                    'The operation succeeded.'
        ]
        self.assertResponses('reload Bz', expected)


class BzListTest(ChannelPluginTestCase, PluginTestCaseUtilMixin):
    channel = '#test'
    plugins = ('Bz', 'User', 'Config')

    def setUp(self, nick='test'):      # pylint: disable=W0221
        ChannelPluginTestCase.setUp(self)
        if os.path.exists('bz.test1.pickle'):
            os.unlink('bz.test1.pickle')
        if os.path.exists('bz.test2.pickle'):
            os.unlink('bz.test2.pickle')
        conf.supybot.plugins.Bz.pollPeriod.setValue(0)
        conf.supybot.plugins.Bz.watchlist.setValue([])
        expected = ['Bz reinitialized with 0 watches.',
                    'The operation succeeded.'
        ]
        self.assertResponses('reload Bz', expected)

        self.assertResponse(
            'watchadd test1' +
                ' file://plugins/Bz/testdata/bz.test1.pickle.0 #test',
            'The operation succeeded.')
        self.assertResponse(
            'watchadd test2' +
                ' file://plugins/Bz/testdata/bz.test1.pickle.0 #test',
            'The operation succeeded.')

    def testListKill(self):
        self.assertResponse("watchlist",
                            "Watches: test1, test2")
        self.assertResponse("watchkill test4",
                            "Error: no such watch.")
        self.assertResponse("watchkill test1",
                            "Watch deleted.")
        self.assertResponse("watchlist",
                            "Watches: test2")
        self.assertResponse("watchkill test2",
                            "Watch deleted.")
        self.assertResponse("watchlist",
                            "No configured watches")

    def testQueryConf(self):
        self.assertResponse("watchquery test1 product:Fedora component:foo",
                            "Watching 28 bugs.")
        self.assertResponse(
            "watchconf test1",
            "url: file://plugins/Bz/testdata/bz.test1.pickle.0," +
                " channels: #test," +
                " query: ['product:Fedora', 'component:foo']")

    def testPollStatusChange(self):
        self.assertResponse("watchpoll test1",
                            "Polled 1 watch.")
        self.assertResponse(
            "config plugins.bz.watches.test1.url" +
                " file://plugins/Bz/testdata/bz.test1.pickle.1",
            "The operation succeeded.")
        expected = [
            "Bug 768769: Missing dependency: wget, new state: OPEN -"
                " https://bugzilla.redhat.com/show_bug.cgi?id=768769",
            "Polled 1 watch."
        ]
        self.assertResponses("watchpoll test1", expected)
        self.assertResponse("watchpoll test1",
                            "Polled 1 watch.")

    def testPollCommentChange(self):
        self.assertResponse("watchpoll test1",
                            "Polled 1 watch.")
        self.assertResponse(
            "config plugins.bz.watches.test1.url" +
                " file://plugins/Bz/testdata/bz.test1.pickle.2",
            "The operation succeeded.")
        expected = [
            "Bug 757351: [abrt] fedora-review-0.1.1-1.fc16:"
                " transaction.py:35:parseSpec:ValueError: can't parse"
                " specfile, new comment from: Fedora Update System"
                " - https://bugzilla.redhat.com/show_bug.cgi?id=757351",
            "Polled 1 watch."
        ]
        self.assertResponses("watchpoll test1", expected)
        self.assertResponse("watchpoll test1",
                            "Polled 1 watch.")

    def testSnarf(self):
        self.assertResponse("watchquery test1 product:Fedora component:foo",
                            "Watching 28 bugs.")
        expected = \
            "908830: check-large-docs.sh doesn't properly skip -doc" \
            " subpackages - CLOSED - 0 attachments - 19 comments -" \
            " https://bugzilla.redhat.com/show_bug.cgi?id=908830"
        self.assertResponse("what about 908830?", expected,
                             usePrefixChar=False)


# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:
