Supybot bz (bugzilla) plugin
=================================

This plugin tracks  a bugzilla instance, It detects new bugs by
polling, and can report status for known bugs.

* Notifies IRC channel about new bugs and bug status changes
* Reports info on bugs for selected products mentioned in IRC conversations.
* Disply status for given bugs.
* Highly configurable.

Bugzilla instances typically handles vast amount of bugs. This plugin has
no way of handling anything near these datasets. In order to be usable
you must restrain the bugs followed using the `watchquery` command and
possibly also the `firstbug` configuration option, see below.

There is already a supybot-bugzilla plugin [2]. Compared to supybot-bugzilla
the supybot-bz  plugin differs in being based on the python-bugzilla package
to access the different bugzillas and by not relying on parsing bugmail to
find new bugs. The net result is that the bz plugin is simpler, but also
sacrifices the scalability and flexibity of the supybot-bugzilla plugin.

Dependencies
------------

This plugin depends on the Python packages:

* BugzillaPython (tested with 0.7.0)
* Supybot (tested with 0.83.1)


Getting started
---------------
* Refer to the supybot documentation to install supybot and configure
  your server e. g., using supybot-wizard. Verify that you can start and
  contact your bot.

* Unpack the plugin into the plugins directory (created by supybot-wizard):
```
      $ cd plugins
      $ git clone https://github.com/leamas/supybot-bz Bz
```

* Identify yourself for the bot in a *private window*. Creating user +
  password is part of the supybot-wizard process.
```
     <leamas> identify al my-secret-pw
     <al-bot-test> The operation succeeded.
```

* Load the plugin and use `list` to verify (from now on in private window):
```
    <leamas> load Bz
    <al-bot-test> The operation succeeded.
    <leamas> list
    <al-bot-test> leamas: Admin, Channel, Config, Bz, Owner, and User
```

* Bz is governed by a set of watches. Each defines a name, a
  bugzilla url and a list of channels you want to feed. Create one using
  `watchadd` e. g.:
```
    <leamas> watchadd test1 http://bugzilla.redhat.com/xmlrpc.cgi  #al-bot-test
    <al-bot-test> leamas: The operation succeeded.
```
* In order to work you must add a search string which defines the set of bugs
  to watch. This is done using the watchquery command
```
    <leamas> watchquery test1 product:Fedora component:fedora-review
    <al-bot-test> leamas: Watching 28 bugs
```

* If there are timeouts in watchquery, try using the firstbug option
  to limit the the amount of bugs retrieved from bugzilla. Having reasonably
  frequent timeouts is a nuisance, but the plugin should still work.
```
    <leamas> watchquery test1 product:gnome component:gnome-shell
    <al-bot-test> leamas: Error: Can't read bug data: The read operation timed out.
    <leamas> config plugins.bz.watches.test1.firstbug 765432
    <al-bot-test> leamas: The operation succeeded.
    <leamas> watchquery test1 product:gnome component:gnome-shell
    <al-bot-test> leamas: Watching 20 bugs
```

* If you create a new bug matching the query it will be displayed:
```
    <al-bot-test> Bug 768769: Missing dependency: wget, new state: OPEN - https://bugzilla.redhat.com/show_bug.cgi?id=768769",
```

* If a bug is mentioned in a conversation the bot will provide info on it.
```
    <leamas> what about 980930?
    <al-bot-test>  908830: check-large-docs.sh doesn't properly skip -doc  subpackages
    - CLOSED - 0 attachments - 19 comments
    - https://bugzilla.redhat.com/show_bug.cgi?id=908830
```


Configuration
-------------

The configuration is done completely in the supybot registry. There are general
setting and watch-specific ones. To see the general settings:
```
    @config list plugins.Bz
    leamas: @watches, pollPeriod, public, watchlist
```

Each setting has help info and could be inspected and set using the config
plugin, see it's documents. Quick crash course using pollPeriod as example:
* Getting help: `@config help plugins.git.pollPeriod`
* See actual value: `@config plugins.git.pollPeriod`
* Setting value: `@config plugins.git.pollPeriod 60`

The `public` and `watchlist` options are internal, please don't touch.

To see the list of watches:
```
    @config list plugins.bz.watches
    leamas: test1, test2
```

Settings for each watch are below these. To see available settings:
```
    @config list plugins.bz.watches.test1
    leamas: channels, url, query, firstbug
```

These variables can be manipulated using the @config command in the same way.

It's possible to edit the config file "by hand" as described in documentation
for @config. However, structural changes is better done by `watchadd` and
`watchkill` even if the config  file is edited after that.


Command List
------------

Plugin commands:

* `watchadd`: Takes a watch  name, an url and a comma-separated
  list of channels. Creates a watch feeding data to current channel.
  Remains inactivated until `watchquery` is run.

* `watchquery`: defines the query i. e., the selection of bugs being
   monitored by a watch. Uses the bugzilla simplified search syntax e. g.,
  'watchquery test1 product:Fedora component:fedora-review`

* `watchlist`: List all watches

* `watchkill`: Delete a watch given it's name.

* `watchconf`: Display configuration for a watch.

* `watchpoll`: Run a poll on a watch if given one, else poll all of them.

* `watchhelp` : Display url to help (i. e., this file).

Other useful commands:

* `config plugins.bz.pollPeriod [seconds]`  Read/set the number of seocnds
   between each attempt to poll the bugzilla instance for changes.

* `config plugins.bz.watches.<watch name>.firstbug [bug id]`. Setting firstbug
   means "discard all bugs with a number less than firstbug". Used to limit the
   dataset used.

* `reload Bz`: Read new configuration, restart polling.


Static checking & unit tests
----------------------------

pep8 (in the Bz directory):
```
  $ pep8 --config pep8.conf . > pep8.log
```
pylint: (in the Bz directory):
```
  $ pylint --rcfile pylint.conf \*.py > pylint.log
```
Unit tests - run in supybot home directory
```
  $ supybot-test  plugins/Bz
```

References:
-----------

[1] python-bugzilla: https://fedorahosted.org/python-bugzilla/
[2] supybot-bugzilla: http://code.google.com/p/supybot-bugzilla
