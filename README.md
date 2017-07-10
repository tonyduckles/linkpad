# Linkpad

`linkpad` is a command-line bookmark manager written in Python3.

## Overview / Features

- Bookmark databases are stored in a dotfile subdirectory under your `$HOME`
  directory -- `$HOME/.linkpad/<dbname>/`.
- Supports multiple bookmark databases.
- Edit bookmarks as YAML documents using your favorite `$EDITOR`.
- Optionally create an offline archive of selected bookmark entries (using
  `wget`), similar to the [Pinboard page archiving
  tool](https://pinboard.in/tour/#archive).
- Each database is version-controlled via Git, which serves both as version
  control and an an easy way to synchronize databases between machines.
- The entire database folder structure is easily portable -- the bookmark
  database is stored as plain-text (JSON).

## Motivation

Often while diving into a new subject, I find myself with *lots* of open browser
tabs.

These are webpages I don't want to necessarily save as a *permanent bookmark*
in my online bookmark manager (e.g. [Pinboard](https://pinboard.in/)), nor do I
want to save these pages in my *read-it-later* list (e.g.
[Pocket](https://getpocket.com/)).

For a long time, I ended-up just keeping these pages around as open tabs in my
web browser to serve as perpetual "to-do" reminders. But left my web browser
cluttered with lots of tabs and often caused some performance/memory woes.

What I *really* wanted was a "middle-ground": somewhere I could keep track of
these lingering pages [*and get them out of my open browser tabs*] but yet
retain most of the organization and searching features of a bookmark manager.
Basically, I wanted *different* bookmark collection than my normal [permanent]
bookmark collection.

While investigating potential options, I came across several command-line based
bookmark managers -- [Buku](https://github.com/jarun/Buku),
[Jotmuch](https://github.com/davidlazar/jotmuch),
[Mbm](https://github.com/quentinsence/mbm) -- which I loved the idea of, but
none of those projects quite had the featureset I wanted. So, in [true
developer form](https://xkcd.com/927/), I rolled my own solution.

## Installation

Requires Python 3.3+.

Clone this repository and install dependencies with `pip`:

```bash
$ git clone https://github.com/tonyduckles/linkpad.git
$ cd linkpad
$ pip install -r requirements.txt
```

Or if you want to sandbox the Python run-time environment, setup a new
`virtualenv` and install dependencies via `setuptools`:

```bash
$ git clone https://github.com/tonyduckles/linkpad.git
$ cd linkpad
$ virtualenv .venv
$ . .venv/bin/activate
$ pip install --editable .
```

## Usage

Run `linkpad --help` to get usage information:

    $ linkpad --help
    Usage: linkpad [OPTIONS] COMMAND [ARGS]...

      Linkpad: A command-line bookmark manager
      https://github.com/tonyduckles/linkpad

    Options:
      -h, --help  Show this message and exit.

    Commands:
      add       Add new entry
      archive   Create offline webpage archive of entries
      database  Database management
      edit      Edit existing entries
      import    Import bookmarks
      list      List entries
      search    Help for entry searching
      show      Show full contents of entries



Run `linkpad <command> --help` to get help on a specific sub-command:

    $ linkpad add --help
    Usage: linkpad add [OPTIONS] URL

      Add a new bookmark using $EDITOR

    Options:
      --title TITLE    Title, by default webpage title will be fetched
      --tags TAGS      Comma separated list of tags
      --extended TEXT  Extended comments/notes
      --archive        Archive an offline copy of this webpage
      --no-edit        Suppress launching $EDITOR to edit new entry file
      -h, --help       Show this message and exit.

### Managing Databases

Databases are stored in `$HOME/.linkpad/<dbname>/`.  You can have multiple
databases, to let you organize bookmarks into whatever groups/collections you
want.

Create a new database:

    $ linkpad database create bookmarks

Switch to using a different database:

```bash
$ linkpad database env bookmarks
export LINKPAD_DBNAME='bookmarks'
# Run this command to configure your shell:
# eval $(linkpad database env 'bookmarks')

$ eval $(linkpad database env bookmarks)
```

### Bookmarks

Each bookmark entry is a collection of fields:

- `url`: (Required) Webpage URL
- `title`: (Required) Bookmark title
- `tags`: (Required) List of tags
- `extended`: (Optional) Extended notes/comments
- `id`: (Internal) Internal ID
- `created_date`: (Internal) Created-on datetime

Here is an example bookmark (presented in YAML format):

    $ linkpad show 53ee08d3
    id: 53ee08d3b5274eab93158f36a2c91ebf
    url: https://github.com/zfsonlinux/zfs-auto-snapshot
    title: GitHub - zfsonlinux/zfs-auto-snapshot
    tags: [backup, snapshot, zfs]
    created_date: 2017-02-04 10:44:11 -0600
    extended: ZFS Automatic Snapshot Service for Linux

### Adding Bookmarks

Add a new bookmark:

    $ linkpad add http://www.example.com

This will launch your default `$EDITOR` to allow you to finalize the new
bookmark entry.  You can change the `url`, `title`, and `tags` list values as
you want.

If you don't pass an explicit  `--title` value then the webpage title will be
looked up in real-time and that will be used as the initial `title` value.

If you don't save the file then `linkpad` will abort the `add`.

### Searching / Selecting Bookmarks

All the  `linkpad` subcommands which work upon a *list* of bookmarks -- e.g.
`list`, `show`, `edit` -- really take in a *list of search criteria* and then
act upon the resulting matchset of bookmarks.

For example, in the simplest form, you can select individual bookmarks by
supplying the full `id`:

    $ linkpad list 53ee08d3b5274eab93158f36a2c91ebf
    53ee08d3 GitHub - zfsonlinux/zfs-auto-snapshot [https://github.com/zfsonlinux/zfs-auto-snapshot] (backup,snapshot,zfs) (5 months ago)

You can select based on the "short ID" -- e.g. the first 8 chars:

    $ linkpad list 53ee08d3
    53ee08d3 GitHub - zfsonlinux/zfs-auto-snapshot [https://github.com/zfsonlinux/zfs-auto-snapshot] (backup,snapshot,zfs) (5 months ago)

Behind the scenes, the search engine is looking for any bookmark entries which
contain the supplied (case-insensitive) text in *any* of the `id`, `title`,
`url`, or `tags` fields. Since the short ID value is likely unique (enough), it
will tend to only match the single desired bookmark entry.

#### Advanced Search

There are several advanced search operators for limiting which bookmark fields
to search against:

- `title:` - Search for match in `title` value.
- `tag:` - Search for match in `tags` list values.
- `url:` - Search for match in `url` value.
- `site:` - Search for match in domain name of `url` value.
- `id:` - Search for match in `id` value.

You can also do inclusive vs exclusive searching by prefixing each search term
with a `+` or `-` (respectively).

#### Searching Examples

1. List all bookmarks (no search arguments):

    ```bash
    $ linkpad list | head -n2
    593c6def Syswear [http://www.syswear.com/] (clothing,shopping) (10 years, 4 months ago)
    055be1cd PortForward [http://www.portforward.com/cports.htm] (firewall,reference) (10 years, 4 months ago)
    ```

2. Search by keyword (matching against any field):

    ```bash
    $ linkpad list docker | head -n2
    8bc51606 Docker: A future without boot2docker, featuring Docker Machine [http://sticksnglue.com/wordpress/a-future-without-boot2docker-featuring-docker-machine/] (docker) (1 years, 3 months ago)
    07c9243d Efficient development workflow using Git submodules and Docker Compose [https://www.airpair.com/docker/posts/efficiant-development-workfow-using-git-submodules-and-docker-compose] (docker,git) ( 4 weeks ago)
    ```

3. Search by tag-name:

    ```bash
    $ linkpad list tag:zfs | head -n2
    92059a10 ZFS Best Practices Guide [http://www.solarisinternals.com/wiki/index.php/ZFS_Best_Practices_Guide] (storage,zfs) (6 years, 5 months ago)
    e26de77e A Home Fileserver using ZFS [http://breden.org.uk/2008/03/02/a-home-fileserver-using-zfs/] (hardware,storage,zfs) (6 years, 5 months ago)
    ```

4. Search by url domain name:

    ```bash
    $ linkpad list site:reddit.com | head -n2
    6f3c68cf HUGE List of Common EDM Drum Patterns, Rhythms, and Fills : edmproduction [https://www.reddit.com/r/edmproduction/comments/2dttc0/huge_list_of_common_edm_drum_patterns_rhythms_and/] (drums,edmpr od) (5 months ago)
    5f5f53b1 Layering percussion, what a lot of people seem to miss. : edmproduction [https://www.reddit.com/r/edmproduction/comments/324eoi/layering_percussion_what_a_lot_of_people_seem_to/] (drums,edmprod) (5 months ago)
    ```

5. Find any bookmarks with *no* tags:

    ```bash
    $ linkpad list +tag: | head -n2
    55e66fe1 Know Your Rights: Photographers | American Civil Liberties Union [http://www.aclu.org/free-speech/know-your-rights-photographers] () (5 years, 9 months ago)
    8ee2bc57 Spice Crust Salmon Recipe by Yongfook | Cookpad [http://cookpad.it/recipes/spice-crust-salmon] () (5 years, 9 months ago)
    ```

## License

MIT License
