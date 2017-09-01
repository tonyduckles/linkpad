# Linkpad: A command-line bookmark manager
# https://github.com/tonyduckles/linkpad
# Copyright (c) 2017 Tony Duckles

# Features:
# =========
# - Supports multiple separate bookmark databases under ~/.linkpad/<dbname>/.
# - Each database is version-controlled via Git, which [aside from version
#   control!] provides an easy way to synchronize databases between machines.
#
# Database Structure:
# ===================
# - Bookmarks are stored as a JSON dict at "$dbpath/entries.json".
# - Optional webpage archive is stored at "$dbpath/archive/<id>.html".
# - Internal schema veraion stored at "$dbpath/format".
#
# Dependencies:
# =============
# - python 3.x
# - git
# - wget (for archiving)

import os
import sys
import collections
import copy
import click
import yaml
import json
import sh
import datetime
import uuid
import urllib.parse
import bs4
import http.client
import tempfile
import requests
import time
import random
import multiprocessing.dummy
import functools
import tqdm

# Workaround for "http.client.HTTPException: got more than 100 headers" exceptions.
# Some servers can be misconfigured and can return an expected # of headers.
http.client._MAXHEADERS = 1000

VERSION = 1.0
PROGRAM = os.path.basename(sys.argv[0])

USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'

LINKPAD_BASEDIR = os.environ.get('LINKPAD_BASEDIR') or os.path.expanduser('~/.linkpad')
LINKPAD_DBNAME = os.environ.get('LINKPAD_DBNAME') or "default"
LINKPAD_DBPATH = os.path.join(LINKPAD_BASEDIR, LINKPAD_DBNAME)

DB_ENTRY_REQUIRED_FIELDS = [ 'id',
                             'url',
                             'title',
                             'tags',
                             'created_date' ]
DB_ENTRY_OPTIONAL_FIELDS = [ 'archived',
                             'archived_date',
                             'extended',
                             'removed',
                             'removed_date',
                             'removed_reason' ]
DB_ENTRY_USEREDIT_FIELDS = copy.deepcopy(DB_ENTRY_REQUIRED_FIELDS)



###
### Misc helpers
###

def datetime_utc_to_local(utc_dt):
    """ Convert a UTC datetime to local datetime """
    # https://stackoverflow.com/a/13287083
    return utc_dt.replace(tzinfo=datetime.timezone.utc).astimezone(tz=None)

def datetime_format_relative(utc_dt):
    """ Format date relative to the current time, e.g. "2 hours ago" """
    delta = datetime.datetime.now(datetime.timezone.utc) - utc_dt
    if delta.days < 2:
        seconds = (delta.days * 86400) + delta.seconds
        minutes = seconds // 60
        hours = minutes // 60
        if seconds < 120:
            return "{} seconds ago".format(seconds)
        if minutes < 120:
            return "{} minutes ago".format(minutes)
        return "{} hours ago".format(hours)
    else:
        days = delta.days
        weeks = days // 7
        months = int(days / (365/12))
        years = days // 365
        if days < 14:
            return "{} days ago".format(days)
        if weeks < 8:
            return "{} weeks ago".format(weeks)
        if years < 1:
            return "{} months ago".format(months)
        months_mod = months % 12
        return "{} years, {} months ago".format(years, months_mod) if months_mod > 0 else "{} years ago".format(years)

def format_colorize(format):
    """
    Given a format template string, replace any format mnemonics
    with literal ANSI color escape sequences.

    Support Tmux-style formatting strings: #[...]
    """
    retval=""
    if '#[' in format:
        pos1=0
        pos2=0
        pos3=format.find('#[', pos1)  # Find first format-start marker
        retval += format[pos1:pos3]   # Append any text before the first format-start marker
        while True:
            pos1 = pos3
            pos2 = format.find(']', pos1+2)  # Find next format-end marker
            if pos2 < 0:
                retval += format[pos1:]  # No counterpart format-end marker, just append remainder of string
                break
            for style in format[pos1+2:pos2].split(','):
                # styles
                if style == 'none': retval += "\x1b[0m"
                if style == 'bold': retval += "\x1b[1m"
                if style == 'bright': retval += "\x1b[1m"
                if style == 'dim': retval += "\x1b[2m"
                if style == 'italics': retval += "\x1b[3m"
                if style == 'underscore': retval += "\x1b[4m"
                if style == 'blink': retval += "\x1b[5m"
                if style == 'reverse': retval += "\x1b[7m"
                # foreground
                if style == 'fg=black': retval += "\x1b[30m"
                if style == 'fg=red': retval += "\x1b[31m"
                if style == 'fg=green': retval += "\x1b[32m"
                if style == 'fg=yellow': retval += "\x1b[33m"
                if style == 'fg=blue': retval += "\x1b[34m"
                if style == 'fg=magenta': retval += "\x1b[35m"
                if style == 'fg=cyan': retval += "\x1b[36m"
                if style == 'fg=white': retval += "\x1b[37m"
                if style == 'fg=default': retval += "\x1b[39m"
                if style == 'fg=brightblack': retval += "\x1b[90m"
                if style == 'fg=brightred': retval += "\x1b[91m"
                if style == 'fg=brightgreen': retval += "\x1b[92m"
                if style == 'fg=brightyellow': retval += "\x1b[93m"
                if style == 'fg=brightblue': retval += "\x1b[94m"
                if style == 'fg=brightmagenta': retval += "\x1b[95m"
                if style == 'fg=brightcyan': retval += "\x1b[96m"
                if style == 'fg=brightwhite': retval += "\x1b[97m"
                # background
                if style == 'bg=black': retval += "\x1b[40m"
                if style == 'bg=red': retval += "\x1b[41m"
                if style == 'bg=green': retval += "\x1b[42m"
                if style == 'bg=yellow': retval += "\x1b[43m"
                if style == 'bg=blue': retval += "\x1b[44m"
                if style == 'bg=magenta': retval += "\x1b[45m"
                if style == 'bg=cyan': retval += "\x1b[46m"
                if style == 'bg=white': retval += "\x1b[47m"
                if style == 'bg=default': retval += "\x1b[49m"
                if style == 'bg=brightblack': retval += "\x1b[100m"
                if style == 'bg=brightred': retval += "\x1b[101m"
                if style == 'bg=brightgreen': retval += "\x1b[102m"
                if style == 'bg=brightyellow': retval += "\x1b[103m"
                if style == 'bg=brightblue': retval += "\x1b[104m"
                if style == 'bg=brightmagenta': retval += "\x1b[105m"
                if style == 'bg=brightcyan': retval += "\x1b[106m"
                if style == 'bg=brightwhite': retval += "\x1b[107m"
            pos3 = format.find('#[',pos2+1)  # Find next format-start marker
            retval += format[pos2+1:pos3 if (pos3 > 0) else None]  # Append text between current format-end and next format-start marker
            if pos3 < 0:
                break
    else:
        retval=format
    return retval

def url_open(url, timeout=None):
    """ Get a webpage, check if it exists """
    headers = requests.utils.default_headers()
    headers.update({'User-Agent': USER_AGENT})
    page_exists = False
    error = None
    content = None

    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        if response.ok:
            page_exists = True
            content = response.content
        else:
            error = 'HTTP error: {} {}'.format(response.status_code, response.reason.title())
    except requests.exceptions.SSLError as e:
        error = "SSL error: {}".format(e)
    except requests.exceptions.HTTPError as e:
        error = 'HTTP error: {}'.format(e)
    except requests.exceptions.ConnectionError as e:
        # Prettify common connection errors
        if hasattr(e, 'args') and len(e.args) > 0:
            if type(e.args[0]) == requests.packages.urllib3.exceptions.MaxRetryError:
                reason = e.args[0].reason
                if type(reason) == requests.packages.urllib3.exceptions.NewConnectionError:
                    if hasattr(reason, 'args') and len(reason.args) > 0:
                        if type(reason.args[0]) == str:
                            message = reason.args[0]
                            # Filter DNS lookup error from other connection errors
                            # (until https://github.com/shazow/urllib3/issues/1003 is resolved)
                            if ("[Errno 11001] getaddrinfo failed" in message or      # Windows
                                "[Errno -2] Name or service not known" in message or  # Linux
                                "[Errno 8] nodename nor servname " in message):       # OS X
                                error = 'Connection error: DNS lookup error'
                            else:
                                error = 'Connection error{}'.format(message[message.find(':'):])
                if type(reason) == requests.packages.urllib3.exceptions.ConnectTimeoutError:
                    if hasattr(reason, 'args') and len(reason.args) > 0:
                        if type(reason.args[0]) == requests.packages.urllib3.connection.HTTPConnection:
                            conn = reason.args[0]
                            error = 'Connection error: HTTP connection timeout (connect timeout={})'.format(conn.timeout)
                        if type(reason.args[0]) == requests.packages.urllib3.connection.VerifiedHTTPSConnection:
                            conn = reason.args[0]
                            error = 'Connection error: HTTPS connection timeout (connect timeout={})'.format(conn.timeout)
        if error is None:
            error = "Connection error: {}".format(e)
    except requests.exceptions.MissingSchema as e:
        error = "Invalid URL: No schema supplied."
    except requests.exceptions.InvalidSchema as e:
        error = "Invalid URL: Invalid schema supplied."
    except requests.exceptions.RequestException as e:
        error = "Error: {}".format(e)
    except Exception as e:
        error = "Exception: {}".format(e)

    return page_exists, error, content

def is_page_exists(url, timeout=None):
    """ Check if a webpage exists """
    exists, error, resp = url_open(url, timeout=timeout)
    return exists, error

def page_title(url):
    """ Get webpage title """
    exists, error, resp = url_open(url)
    if not exists:
        return ''
    if error is not None and len(error) > 0:
        return ''
    try:
        page = bs4.BeautifulSoup(resp, "html.parser")
        return page.title.string.strip() if page.title else ''
    except Exception as e:
        return ''

def archive_url(url, archive_dir, verbose=False, throttle_downloads=False):
    """ Save an archived version of a webpage, along with all the
        required media you'll need to view the page offline """

    # Abort early if target url doesn't exist
    page_exists, error = is_page_exists(url)
    if not page_exists:
        click.echo('error: '+error)
        return None

    # Use 'wget' to download an archive version of the webpage
    tmpdir = tempfile.TemporaryDirectory()
    wget_args = [
        '--no-verbose',        # turn off verboseness, without being quiet
        '--span-hosts',        # go to foreign hosts when recursive
        '--timestamping',      # don't re-retrieve files unless newer than local
        '--convert-links',     # make links in downloaded HTML or CSS point to local files
        '--page-requisites',   # get all images, etc. needed to display HTML page
        '--directory-prefix', tmpdir.name,   # save files to PREFIX/..
        '--user-agent', USER_AGENT ]         # identify as AGENT instead of Wget/VERSION
    if throttle_downloads:
        wget_args.extend([
            '--wait=3',        # wait SECONDS between retrievals
            '--random-wait' ]  # wait from 0.5*WAIT...1.5*WAIT secs between retrievals
        )

    html_file = None
    for line in sh.wget(wget_args, url,
                        #_err_to_out=True,
                        #_out=sys.stdout,
                        _ok_code=[ 0, 4, 8 ],
                        _iter="err"):
        # Get the target filename by scraping the wget output
        if html_file is None and ' URL:{} ['.format(url) in line:
            base = os.path.join(tmpdir.name, "")
            pos1 = line.find(base)
            if pos1 > 0:
                pos2 = line.find('"', pos1)
                if pos2 > 0:
                    html_file = line[pos1:pos2]
        if not verbose:
            continue
        click.echo(
            format_colorize("#[fg=blue]{}#[none]".format(line)),
            nl=False
        )

    # Verify we extracted the target filename correctly
    if not os.path.isfile(html_file):
        raise RuntimeError('Expected archive file does not exist: {}'.format(html_file))

    # Wipe any pre-existing contents, so we don't leave orphaned files around
    sh.mkdir(archive_dir, parents=True)
    for f in os.scandir(archive_dir):
        if f.is_dir():
            sh.rm('-r', '-f', f.path)
        if f.is_file():
            sh.rm(f.path)

    # Copy the downloaded files to archive_dir
    sh.rsync('-a', os.path.join(tmpdir.name, ""), archive_dir)

    # Create a symlink pointing to the target html file
    html_file = html_file.replace(tmpdir.name, archive_dir)
    symlink_source = html_file.replace(os.path.join(archive_dir, ""), "")  # Relative path
    symlink_target = os.path.join(archive_dir, 'index.html')
    sh.cd(archive_dir)
    sh.ln('-f', '-s', symlink_source, symlink_target)

    # Cleanup staging directory
    tmpdir.cleanup()

    return html_file



###
### YAML helpers
###

def yaml_represent_OrderedDict(dumper, data):
    """ Representer for collections.OrderedDict, for yaml.dump """
    return dumper.represent_mapping(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        data.items())

yaml.add_representer(collections.OrderedDict, yaml_represent_OrderedDict)



###
### Database utilities
###

def db_exists(dbname = None):
    """ Check if database exists """
    dbname = dbname or LINKPAD_DBNAME
    dbpath = os.path.join(LINKPAD_BASEDIR, dbname)
    return True if os.path.isdir(dbpath) and os.path.isfile(os.path.join(dbpath, 'format')) else False

def db_filepath_format_file(dbpath=None):
    dbpath = dbpath or LINKPAD_DBPATH
    return os.path.join(dbpath, 'format')

def db_filepath_database_file(dbpath=None):
    dbpath = dbpath or LINKPAD_DBPATH
    return os.path.join(dbpath, 'entries.json')

def db_filepath_entry_archive_dir(id, dbpath=None):
    dbpath = dbpath or LINKPAD_DBPATH
    return os.path.join(dbpath, 'archive', id)

def db_create_db(dbname):
    """ Initialize new database """
    dbpath = os.path.join(LINKPAD_BASEDIR, dbname)
    if os.path.isdir(dbpath):
        sys.exit("Error: db_create_db(): directory already exists: {}".format(dbpath))
    _git = sh.git.bake('-C', dbpath)  # Helper to run 'git' commands against this specific repo

    sh.mkdir('-p', dbpath)   # Create directory (and any needed parent directories)
    sh.chmod('700', dbpath)
    _git.init('-q')          # Init git repo

    format_file = db_filepath_format_file(dbpath)
    sh.echo("1", _out=format_file)
    _git.add(format_file)

    _git.commit('-q', '-m', "Create database")

def db_load_db():
    """ Load all entries from database file """
    if not db_exists():
        sys.exit("Error: database '{}' does not exist".format(LINKPAD_DBNAME))

    dbfile = db_filepath_database_file()
    if os.path.isfile(dbfile):
        with open(dbfile, 'r', encoding='utf-8') as f:
            db_entry_list = [ db_entry_internalize(entry) for entry in json.load(f) ]
    else:
        db_entry_list = []
    return db_entry_list

def db_save_db(db_entry_list):
    """ Save all entries to database file """
    if not db_exists():
        sys.exit("Error: database '{}' does not exist".format(LINKPAD_DBNAME))

    dbfile = db_filepath_database_file()
    with open(dbfile, 'w', encoding='utf-8') as f:
        # JSON encode each entry individually so we can enforce
        # newlines between each row
        first = True
        for entry in sorted(db_entry_list, key=lambda entry: entry['created_date']):
            f.write('[' if first else ',\n')
            first = False
            f.write(json.dumps(db_entry_externalize(copy.deepcopy(entry)), separators=(',', ':')))
        f.write(']')

def db_entry_get(db_entry_list, url):
    """ Find an existing entry in the database based on url """
    matches = [ entry for entry in db_entry_list if entry['url'] == url ]
    if len(matches) > 1:
        raise Exception('Internal Error: found multiple matching entries for url "{}"'.format(url))
    return matches[0] if len(matches) > 0 else None

def db_entry_generate_id():
    """ Generate a new uuid for a new entry """
    return str(uuid.uuid4()).lower().replace('-','')

def db_entry_externalize(entry, datetime_format='%Y-%m-%dT%H:%M:%SZ%z', datetime_as_local=False):
    """ Convert an entry dict from internal to external format """
    for field in entry:
        if field in [ 'created_date', 'archived_date', 'removed_date' ]:
            date = entry[field].replace(tzinfo=datetime.timezone.utc)
            if datetime_as_local:
                date = datetime_utc_to_local(date)
            entry[field] = date.strftime(datetime_format)
    return entry

def db_entry_internalize(entry, datetime_format='%Y-%m-%dT%H:%M:%SZ%z'):
    """ Convert an entry dict from external to internal format """
    entry = db_entry_internalize_trim(entry)  # Remove empty optional fields
    for field in entry:
        if field in [ 'created_date', 'archived_date', 'removed_date' ]:
            date = datetime.datetime.strptime(entry[field], datetime_format)
            entry[field] = date.astimezone(datetime.timezone.utc)  # Make sure datetime is UTC
    return entry

def db_entry_internalize_trim(entry):
    """ Remove empty optional fields from an internal-format entry """
    for field in DB_ENTRY_OPTIONAL_FIELDS:
        if field in entry and type(entry[field]) is str and len(entry[field]) == 0:
            del entry[field]
    return entry

def db_entry_to_editdoc(entry, all_fields=False, datetime_format='%Y-%m-%d %H:%M:%S %z', datetime_as_local=True):
    """ Return an OrderedDict containing the editable fields for an entry, for user-editing """
    doc = collections.OrderedDict()
    fields = []
    if all_fields:
        # Include all fields
        fields.extend(DB_ENTRY_REQUIRED_FIELDS)
        fields.extend(DB_ENTRY_OPTIONAL_FIELDS)
    else:
        # Only include user-editable fields
        fields.extend(DB_ENTRY_USEREDIT_FIELDS)

    for field in fields:
        if field in entry:
            doc[field] = entry[field]

    return db_entry_externalize(doc, datetime_format, datetime_as_local)

def db_entry_from_editdoc(doc, datetime_format='%Y-%m-%d %H:%M:%S %z'):
    """ Return a dict from a user-edited entry """
    # TODO: Gracefully error if user removed a required field
    #       and/or added a non-user-editable optional field?
    entry = {}
    for field in DB_ENTRY_REQUIRED_FIELDS:
        entry[field] = doc[field]
    for field in DB_ENTRY_OPTIONAL_FIELDS:
        if field in doc:
            entry[field] = doc[field]

    return db_entry_internalize(entry, datetime_format)

def db_entry_add(db_entry_list, url, title, tags, extended, use_editor=True):
    """ Add a new entry to the database """
    # If we already have an entry with this same url, abort
    match = db_entry_get(db_entry_list, url)
    if match:
        sys.exit('Error: entry already exists for url "{}"'.format(url))

    # Create a new entry
    entry = { 'id': db_entry_generate_id(),
              'url': url,
              'title': title if title is not None else page_title(url),
              'tags': list(sorted(dict.fromkeys(tags))) if tags is not None else [],  # Remove duplicate tags
              'created_date': datetime.datetime.now(datetime.timezone.utc),
              'extended': extended if extended is not None else '' }

    # Launch editor to allow user to finalize data
    entry_list = [ entry ]
    if use_editor:
        entry_list = db_entry_list_edit(entry_list)

    return entry_list

def db_entry_list_edit(entry_list):
    """ Edit a list of entries """
    # Map the internal format entries to external edit-doc format
    doc_list = [ db_entry_to_editdoc(entry) for entry in entry_list ]

    # Convert the edit-doc list to YAML format and launch the editor
    yaml_edited = click.edit(yaml.dump_all(doc_list),
                             extension='.yaml',
                             require_save=True)
    if yaml_edited is None:
        return None

    # Map the post-edited external format back to internal format
    doc_list = yaml.safe_load_all(yaml_edited)
    entry_list = [ db_entry_from_editdoc(doc) for doc in doc_list ]
    return entry_list

def db_entry_list_update(db_entry_list, entry_list):
    """ Add/update entries in the database """
    changed_list = []
    for new_entry in entry_list:
        found = False
        for pos, old_entry in enumerate(db_entry_list):
            if old_entry['id'] == new_entry['id']:
                found = True
                changed = False
                for key in old_entry:
                    if not key in new_entry:
                        changed = True
                        break
                    if old_entry[key] != new_entry[key]:
                        changed = True
                        break
                for key in new_entry:
                    if not key in old_entry:
                        changed = True
                        break
                    if old_entry[key] != new_entry[key]:
                        changed = True
                        break
                if changed:
                    db_entry_list[pos] = new_entry
                    changed_list.append(new_entry)
                break
        if not found:
            db_entry_list.append(new_entry)
            changed_list.append(new_entry)

    return changed_list if len(changed_list) > 0 else None

def db_entry_list_archive(entry_list, verbose=False):
    changed_list = []
    for entry in entry_list:
        if not entry['url'].lower().startswith('http'):
            continue

        url = entry['url']
        click.echo('archiving "{}" ...'.format(url))
        archive_dir = db_filepath_entry_archive_dir(entry['id'])
        if os.path.isdir(archive_dir):
            # Wipe pre-existing contents, so we don't leave orphaned files around
            for f in os.scandir(archive_dir):
                if f.is_dir():
                    sh.rm('-r', '-f', f.path)
                if f.is_file():
                    sh.rm(f.path)
        archive_file = archive_url(url, archive_dir, verbose=verbose)
        if archive_file is None:
            continue

        edit_entry = copy.deepcopy(entry)
        edit_entry['archived'] = True
        edit_entry['archived_date'] = datetime.datetime.now(datetime.timezone.utc)
        changed_list.append(edit_entry)

    return changed_list if len(changed_list) > 0 else None

def db_entry_list_remove(db_entry_list, entry_list, hard_delete=False):
    """ Remove (or purge) a list of entries """
    changed_list = []
    for rm_entry in entry_list:
        for pos, entry in enumerate(db_entry_list):
            if entry['id'] == rm_entry['id']:
                if hard_delete:
                    del db_entry_list[pos]
                    entry['hard_deleted'] = True
                    changed_list.append(entry)
                else:
                    if (not 'removed' in entry) or (not entry['removed']):
                        entry['removed'] = True
                        entry['removed_date'] = datetime.datetime.now(datetime.timezone.utc)
                        changed_list.append(entry)
                break
    return changed_list if len(changed_list) > 0 else None

def db_entry_list_search(db_entry_list, search_args, include_removed=False):
    """ Find matching entries in the database """
    # Parse the search args
    search_all_list = []
    search_not_list = []
    search_any_list = []
    for arg in search_args:
        if arg[0] == "+":
            search_all_list.append(arg[1:])
        elif arg[0] == "-":
            search_not_list.append(arg[1:])
        else:
            search_any_list.append(arg)

    # Build list of matching entries
    entry_list = []
    for entry in db_entry_list:
        # Hide removed entries by default
        if entry.get('removed', False) and not include_removed:
            continue

        # Filter by search_args
        if len(search_not_list) > 0:
            if any(db_entry_search_match(entry, search_arg) for search_arg in search_not_list):
                continue
        if len(search_all_list) > 0:
            if not all(db_entry_search_match(entry, search_arg) for search_arg in search_all_list):
                continue
        if len(search_any_list) > 0:
            if not any(db_entry_search_match(entry, search_arg) for search_arg in search_any_list):
                continue

        entry_list.append(entry)

    return entry_list if len(entry_list) > 0 else None

def db_entry_search_match(entry, search_arg):
    """ Check if this entry matches the given search_arg """
    if search_arg[:6] == 'title:':
        val = search_arg[6:]
        return (val.lower() in entry['title'].lower() if len(val) > 0 else len(entry['title']) == 0)
    elif search_arg[:4] == 'tag:':
        val = search_arg[4:]
        return (any(val.lower() in tag.lower() for tag in entry['tags']) if len(val) > 0 else len(entry['tags']) == 0)
    elif search_arg[:5] == 'site:':
        val = search_arg[5:]
        url_domain = "{0.netloc}".format(urllib.parse.urlsplit(entry['url']))
        return (val.lower() in url_domain.lower() if len(val) > 0 else len(url_domain) == 0)
    elif search_arg[:4] == 'url:':
        val = search_arg[4:]
        return (val.lower() in entry['url'].lower() if len(val) > 0 else len(entry['url']) == 0)
    elif search_arg[:3] == 'id:':
        val = search_arg[3:]
        return (val.lower() in entry['id'][0:len(val)].lower() if len(val) > 0 else len(entry['id']) == 0)
    elif search_arg[:9] == 'archived:':
        val = (search_arg[9:].lower() == 'true')
        return (entry.get('archived', False) == val)
    else:
        string = "{} {} {} {}".format(entry['id'],
                                      entry['title'],
                                      entry['url'],
                                      ' '.join(entry['tags']))
        return (search_arg.lower() in string.lower())

def db_entry_print(entry_list, print_format=None):
    """ Print entries based on print_format template """
    print_format = print_format or "#[fg=yellow]%shortid#[none] %title #[fg=cyan][%url]#[none] #[fg=brightgreen](%tags)#[none] #[fg=brightblack](%created_ago)#[none]"
    print_format_line = format_colorize(print_format)  # Evaluate style mnemonics ahead of time

    for entry in entry_list:
        # Build the final output line based on the print_format template
        line = print_format_line
        subs = [ ('%shortid', entry['id'][:8]),
                 ('%id', entry['id']),
                 ('%url', entry['url']),
                 ('%title', entry['title']),
                 ('%tags', ','.join(entry['tags'])),
                 ('%created_date', datetime_utc_to_local(entry['created_date']).strftime('%Y-%m-%d %H:%M:%S %Z')),
                 ('%created_ago', datetime_format_relative(entry['created_date'])) ]
        for search, replacement in subs:
            line = line.replace(search, replacement)
        click.echo(line)

def db_git_commit(commit_desc, archive_list=None):
    """ Use 'git add' and 'git commit' to commit any pending edits """
    _git = sh.git.bake('-C', LINKPAD_DBPATH)  # Helper to run 'git' commands against this specific repo

    # Track any changes to the database file
    db_file = db_filepath_database_file()
    if os.path.isfile(db_file):
        _git.add(db_file)

    # Track any changes in entry archive files
    if archive_list is not None:
        for entry in archive_list:
            archive_dir = db_filepath_entry_archive_dir(entry['id'])
            if not entry.get('archived', False):
                continue
            if entry.get('hard_deleted', False):
                _git.rm('-r', '-f', archive_dir)
            else:
                _git.add('-A', '-f', archive_dir)

    # Commit the tracked changes
    _git.commit('-q', '-m', commit_desc)


###
### Main command-line entry point: "$PROGRAM ..."
###

CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])
@click.group(context_settings=CONTEXT_SETTINGS)
def cli():
    """
    Linkpad: A command-line bookmark manager
    https://github.com/tonyduckles/linkpad
    """
    pass

@cli.command(name='search', short_help='Help for entry searching')
def command_search():
    """
    All the `linkpad` subcommands which act upon a list of entries
    [e.g. list, show, edit] take in a list of SEARCH terms and then
    act upon the resulting matchset.

    Searching is always case-insensitive.

    \b
    SEARCH TERM FORMAT:
       Enter a specific entry ID (or short ID) to match a single entry,
       or enter multiple ID's to select multiple entries.

    \b
       If you enter multiple terms, match any entries which contain *any* of
       those terms [in id, title, tags, or url fields].

    \b
       You can further control the search results by using Search Operators
       and/or Inclusion/Exclusion prefixes.

    \b
       Search Operators
       ----------------
       TEXT            Search for text in any -- id, title, tags, url (default)
       title:TEXT      Search for text in title
       tag:TEXT        Search for text in tag
       url:TEXT        Search for text in url
       site:TEXT       Search for text in url domain name
       id:TEXT         Search for entry id prefix match

    \b
       Inclusion/Exclusion
       -------------------
       Prefix search string for AND/OR/NOT handling:
       +TEXT           All these words
        TEXT           Any of these words (default)
       -TEXT           None of these words

    \b
       Note: when using exclusions, you must pass in "--" as the first
       argument as the separator between options and arguments, which is the
       POSIX convention.

    """
    pass

@cli.command(name='add', short_help='Add new entry')
@click.option('--title', 'title', metavar='TITLE',
        help='Title, by default webpage title will be fetched')
@click.option('--tags', 'tags', metavar='TAGS',
        help='Comma separated list of tags')
@click.option('--extended', 'extended', metavar='TEXT',
        help='Extended comments/notes')
@click.option('--archive', 'archive', is_flag=True,
        help='Archive an offline copy of this webpage')
@click.option('--no-edit', 'no_edit', is_flag=True,
        help='Suppress launching $EDITOR to edit new entry file')
@click.argument('url', required=True)
def command_add(url, title, tags, extended, archive, no_edit):
    """
    Add a new entry using $EDITOR
    """
    db_entry_list = db_load_db()
    entry_list = db_entry_add(db_entry_list,
                              url,
                              title,
                              [ tag.strip() for tag in tags.split(',') ] if tags is not None else [],
                              extended,
                              use_editor=False if no_edit else True)
    if entry_list is None:
        sys.exit('User aborted')

    # Update the database with the new entry
    changed_list = db_entry_list_update(db_entry_list, entry_list)
    if changed_list is None:
        sys.exit('No changes found')

    archived_list = None
    if archive:
        archived_list = db_entry_list_archive(changed_list)

    # Save results
    db_save_db(db_entry_list)
    commit_desc = 'Add {}'.format("'"+changed_list[0]['url']+"'")
    db_git_commit(commit_desc, archived_list)

    # Display changed entries
    db_entry_print(changed_list)

@cli.command(name='edit', short_help='Edit existing entries')
@click.option('-a', '--all', 'include_removed', is_flag=True,
        help='All entries, including removed entries')
@click.argument('search_args', metavar='[SEARCH]...', nargs=-1)
def command_edit(search_args, include_removed):
    """
    Edit existing entries using $EDITOR

    \b
    SEARCH TERM FORMAT:
       (See `linkpad search --help`)

    """
    db_entry_list = db_load_db()
    entry_list = db_entry_list_search(db_entry_list, search_args, include_removed=include_removed)
    if entry_list is None:
        sys.exit('No selected entries')

    click.echo('{} entries to edit'.format(len(entry_list)))
    if len(entry_list) > 5 and not click.confirm('Do you want to continue?'):
        sys.exit('User aborted')
    entry_list = db_entry_list_edit(entry_list)
    if entry_list is None:
        sys.exit('User aborted')

    # TODO: Support user adding "archived: True" to the YAML text,
    #       and then doing archiving here?

    # Update the database with the new entry
    changed_list = db_entry_list_update(db_entry_list, entry_list)
    if changed_list is None:
        sys.exit('No changes found')

    # Save results
    db_save_db(db_entry_list)
    commit_desc = 'Edit {}'.format("'"+(' '.join(search_args))+"'" if search_args else 'all')
    db_git_commit(commit_desc)

    # Display changed entries
    db_entry_print(changed_list)

@cli.command(name='archive', short_help='Create offline webpage archive of entries')
@click.option('-v', '--verbose', 'verbose', is_flag=True,
        help='Show verbose wget output')
@click.argument('search_args', metavar='[ID]...', nargs=-1)
def command_archive(search_args, verbose):
    """
    Create/update an offline webpage archive for selected entries.
    """
    db_entry_list = db_load_db()
    entry_list = db_entry_list_search(db_entry_list, search_args)
    if entry_list is None:
        sys.exit('No selected entries')

    click.echo('{} entries to archive'.format(len(entry_list)))
    if len(entry_list) > 5 and not click.confirm('Do you want to continue?'):
        sys.exit('User aborted')
    archived_list = db_entry_list_archive(entry_list, verbose=verbose)
    if archived_list is None:
        sys.exit('No changes found')

    # Update database
    _ = db_entry_list_update(db_entry_list, archived_list)

    # Save results
    db_save_db(db_entry_list)
    commit_desc = 'Archive {}'.format("'"+(' '.join(search_args))+"'" if search_args else 'all')
    db_git_commit(commit_desc, archived_list)

@cli.command(name='remove',
             short_help='Remove entries')
@click.option('-f', '--force', 'hard_delete', is_flag=True,
        help='Permanently purge entry')
@click.argument('search_args', metavar='[SEARCH]...', nargs=-1)
def command_remove(search_args, hard_delete):
    """
    Remove entries from the database.

    By default this command will only "soft-delete" entries -- meaning keeping
    them in the database and marking them as removed (inactive). These inactive
    entries will be ignored search results by default (unless you pass --all).

    Use the --force option if you want to permanently purge (hard-delete)
    this entry from the database.
    """
    db_entry_list = db_load_db()
    entry_list = db_entry_list_search(db_entry_list, search_args, include_removed=True)
    if entry_list is None:
        sys.exit('No selected entries')

    click.echo('{} entries to {}'.format(len(entry_list), ('purge' if hard_delete else 'remove')))
    if len(entry_list) > 5 and not click.confirm('Do you want to continue?'):
        sys.exit('User aborted')
    changed_list = db_entry_list_remove(db_entry_list, entry_list, hard_delete=hard_delete)
    if changed_list is None:
        sys.exit('No changes found')
    archive_list = []
    for entry in changed_list:
        if entry.get('archived', False):
            archive_list.append(entry)

    # Save results
    db_save_db(db_entry_list)
    commit_desc = '{} {}'.format(('Purge' if hard_delete else 'Remove'), "'"+(' '.join(search_args))+"'" if search_args else 'all')
    db_git_commit(commit_desc, archive_list)

#@cli.command(name='grep', short_help='Find entries by grep\'ing through archived offline webpage files')
#def command_grep():
#    click.echo("grep")

@cli.command(name='list', short_help='List entries')
@click.option('-a', '--all', 'include_removed', is_flag=True,
        help='All entries, including removed entries')
@click.option('-s', '--sort', 'sort_key', type=click.Choice(DB_ENTRY_REQUIRED_FIELDS),
        default='created_date', show_default=True,
        help='Sort list by entry field')
@click.option('-r', '--reverse', 'sort_reverse', is_flag=True,
        help='Reverse the sort order')
@click.option('-f', '--format', 'print_format', metavar='FORMAT',
        help='Custom print format -- see "PRINT FORMAT"')
@click.argument('search_args', metavar='[SEARCH]...', nargs=-1)
def command_list(search_args, include_removed, sort_key, sort_reverse, print_format):
    """
    List all entries, or list all selected entries.

    List all entries by default (i.e. no search filters).
    Optionally pass in a list of SEARCH terms to select specific entries.

    \b
    SEARCH TERM FORMAT:
       (See `linkpad search --help`)

    \b
    PRINT FORMAT:
       The `--format` option allows you to control the text that is printed
       for each matched entry.

    \b
       Variables:
          %id             Full ID
          %shortid        Short ID
          %url            URL
          %title          Title
          %tags           Tag list, comma-delimited
          %created_date   Absolute date
          %created_ago    Relative date

    \b
       Style sequences:
          #[style] where 'style' are any Tmux-style style strings

    \b
       Example: "#[fg=yellow]%shortid#[none] %title [%url] (%tags) (%created_ago)"
    """
    db_entry_list = db_load_db()
    entry_list = db_entry_list_search(db_entry_list, search_args, include_removed=include_removed)
    if entry_list is None:
        #sys.exit('No selected entries')
        sys.exit()

    # Display match entries, sorted by sort_key
    entry_list = sorted(entry_list, key=lambda entry: entry[sort_key])
    if sort_reverse:
        entry_list.reverse()
    db_entry_print(entry_list, print_format)

@cli.command(name='show',
             short_help='Show full contents of entries')
@click.option('-a', '--all', 'include_removed', is_flag=True,
        help='All entries, including removed entries')
@click.option('-s', '--sort', 'sort_key', type=click.Choice(DB_ENTRY_REQUIRED_FIELDS),
        default='created_date', show_default=True,
        help='Sort list by entry field')
@click.option('-r', '--reverse', 'sort_reverse', is_flag=True,
        help='Reverse the sort order')
@click.argument('search_args', metavar='[SEARCH]...', nargs=-1)
def command_show(search_args, include_removed, sort_key, sort_reverse):
    """
    Show full contents of selected entries.

    \b
    SEARCH TERM FORMAT:
       (See `linkpad search --help`)

    """
    db_entry_list = db_load_db()
    entry_list = db_entry_list_search(db_entry_list, search_args, include_removed=include_removed)
    if entry_list is None:
        #sys.exit('No selected entries')
        sys.exit()

    # Sort entry_list
    entry_list = sorted(entry_list, key=lambda entry: entry[sort_key])

    # Map the internal format entries to external edit-doc format
    doc_list = [ db_entry_to_editdoc(entry, all_fields=True) for entry in entry_list ]
    if sort_reverse:
        doc_list.reverse()

    # Convert the edit-doc list to YAML format and launch the editor
    click.echo(yaml.dump_all(doc_list))

@cli.command(name='tags',
             short_help='List tags')
@click.option('-a', '--all', 'include_removed', is_flag=True,
        help='All entries, including removed entries')
@click.option('-c', '--count', 'show_count', is_flag=True,
        help='Show number of entries per tag')
@click.option('-s', '--sort', 'sort_key', type=click.Choice(['name', 'count']),
        default='name', show_default=True,
        help='Sort list by entry field')
@click.option('-r', '--reverse', 'sort_reverse', is_flag=True,
        help='Reverse the sort order')
@click.argument('search_args', metavar='[SEARCH]...', nargs=-1)
def command_tags(search_args, include_removed, show_count, sort_key, sort_reverse):
    """
    List tags

    \b
    SEARCH TERM FORMAT:
       If you enter multiple words, match any tag-names which contain *any* of
       those terms.

    \b
       You can further control the search results by using Inclusion/Exclusion
       prefixes.

    \b
       Inclusion/Exclusion
       -------------------
       Prefix search string for AND/OR/NOT handling:
       +TEXT           All these words
        TEXT           Any of these words (default)
       -TEXT           None of these words
    """
    # Parse the search args
    search_all_list = []
    search_not_list = []
    search_any_list = []
    for arg in search_args:
        if arg[0] == "+":
            search_all_list.append(arg[1:])
        elif arg[0] == "-":
            search_not_list.append(arg[1:])
        else:
            search_any_list.append(arg)

    tag_list = {}
    db_entry_list = db_load_db()
    for entry in db_entry_list:
        # Hide removed entries by default
        if entry.get('removed', False) and not include_removed:
            continue
        for tag in entry['tags']:
            # Apply search filters
            if len(search_not_list) > 0:
                if any((arg.lower() in tag.lower()) for arg in search_not_list):
                    continue
            if len(search_all_list) > 0:
                if not all((arg.lower() in tag.lower()) for arg in search_all_list):
                    continue
            if len(search_any_list) > 0:
                if not any((arg.lower() in tag.lower()) for arg in search_any_list):
                    continue

            if tag in tag_list:
                tag_list[tag] += 1
            else:
                tag_list[tag] = 1

    sorted_list = tag_list.keys()
    if sort_key == 'name':
        sorted_list = sorted(tag_list.keys())
    if sort_key == 'count':
        sorted_list = [ key for key in sorted(tag_list, key=tag_list.get) ]
    if sort_reverse:
        sorted_list.reverse()

    for tag in sorted_list:
        if show_count:
            click.echo('{}\t{}'.format(tag_list[tag], tag))
        else:
            click.echo('{}'.format(tag))

@cli.command(name='check',
             short_help='Check for broken links')
@click.option('-j', '--jobs', 'thread_count', metavar='NUM', default=16,
        help='Set number of threads to use for processing')
@click.option('-t', '--timeout', 'timeout', metavar='SECS', default=30,
        help='Set connection timeout threshold')
@click.argument('search_args', metavar='[SEARCH]...', nargs=-1)
def command_check(search_args, thread_count, timeout):
    """
    Check for broken links
    """
    # Create a list of dict's to process
    db_entry_list = db_load_db()
    entry_list = db_entry_list_search(db_entry_list, search_args)
    click.echo('{} urls to check (using {} threads) ...'.format(len(entry_list), thread_count), err=True)

    # Multi-thread the processing
    fail_count = 0
    fail_list = {}
    pool = multiprocessing.dummy.Pool(thread_count)
    with tqdm.tqdm(pool.imap_unordered(functools.partial(check_url, timeout=timeout), entry_list),
                   total=len(entry_list),
                   ascii=True) as bar:
        for result in bar:
            if not result['exists']:
                fail_count += 1
                error = result['error']
                entry = result['entry']
                if error in fail_list:
                    fail_list[error].append(entry)
                else:
                    fail_list[error] = [ entry ]

    # Summary
    for error in sorted(fail_list.keys()):
        click.echo(error)
        for entry in fail_list[error]:
            db_entry_print([ entry ], "  #[fg=yellow]%shortid#[none] #[fg=cyan]%url#[none]")
        click.echo("")

    click.echo('found {} broken links'.format(fail_count), err=True)

def check_url(entry, timeout):
    # Sleep between calls to prevent swamping remote server (if there are
    # multiple adjacent entries on the same website), to avoid getting
    # transient 502/503 status errors
    time.sleep(random.uniform(0,3))

    page_exists, error = is_page_exists(entry['url'], timeout=timeout)
    ret = {
        'entry': copy.deepcopy(entry),
        'exists': page_exists,
        'error': error,
    }
    return ret

@cli.command(name='version',
             short_help='Show version')
def command_version():
    click.echo("{} {}".format(PROGRAM, VERSION))

###
### Command-line: "$PROGRAM database ..."
###

@cli.group(name='database', short_help='Database management')
def command_database():
    """ Database management """
    pass

@command_database.command(name='name')
@click.option('-f', '--full', 'full_path', is_flag=True, help='Print full filepath')
def command_database_name(full_path):
    """
    Show current database name
    """
    click.echo(LINKPAD_DBPATH if full_path else LINKPAD_DBNAME)

@command_database.command(name='list')
@click.option('-f', '--full', 'full_path', is_flag=True, help='Print full filepath')
def command_database_list(full_path):
    """
    List available database names
    """
    for entry in os.scandir(LINKPAD_BASEDIR):
        if entry.is_dir() and db_exists(entry.name):
            click.echo(entry.path if full_path else entry.name)

@command_database.command(name='env')
@click.argument('dbname', required=False)
def command_database_env(dbname):
    """
    Display the commands to setup the shell environment for a database
    """
    dbname = dbname or LINKPAD_DBNAME
    if not db_exists(dbname):
        sys.exit("Error: database '{}' does not exist".format(dbname))

    click.echo('export LINKPAD_DBNAME=\'{}\''.format(dbname))
    click.echo('# Run this command to configure your shell:')
    click.echo('# eval $(linkpad database env \'{}\')'.format(dbname))

@command_database.command(name='create', short_help='Create a new database')
@click.argument('dbname')
def command_database_create(dbname):
    """
    Create a new database
    """
    if db_exists(dbname):
        sys.exit("Error: database '{}' already exists".format(dbname))
    db_create_db(dbname)
    dbpath = os.path.join(LINKPAD_BASEDIR, dbname)
    click.echo("created '{}'".format(dbpath))

@command_database.command(name='clone',
             short_help='Git-clone an existing database')
@click.argument('url', metavar='GIT_URL', required=True)
@click.argument('dbname', required=True)
def command_database_clone(url, dbname):
    """
    Clone an existing database from a Git repo

    Shortcut for `git clone GIT_URL $HOME/.linkpad/$DBNAME`
    """
    if db_exists(dbname):
        sys.exit("Error: database '{}' already exists".format(dbname))
    sh.cd(LINKPAD_BASEDIR)
    sh.git('clone', url, dbname, _fg=True)
    click.echo()
    dbpath = os.path.join(LINKPAD_BASEDIR, dbname)
    if not db_exists(dbname):
        click.echo("Deleting '{}' ...".format(dbpath))
        sh.rm('-rf', dbpath)
        sys.exit("Error: url '{}' did not contain a valid Linkpad database".format(url))
    click.echo("cloned '{}'".format(dbpath))

@command_database.command(name='git',
             short_help='Run Git commands against backend database folder')
@click.argument('git_args', metavar='[ARGS]...', nargs=-1)
def command_database_git(git_args):
    """
    Run Git commands against backend database folder
    """
    #subprocess.run(['git', '-C', LINKPAD_DBPATH] + [ arg for arg in git_args ], shell=False)
    sh.git(['-C', LINKPAD_DBPATH] + [ arg for arg in git_args ], _fg=True, _tty_out=False)

###
### Command-line: "$PROGRAM import ..."
###

@cli.group(name='import', short_help='Import entries')
def command_import():
    """ Import entries from a flat file """
    pass

@command_import.command(name='pinboard-json')
@click.option('-n', '--dry-run', 'dry_run', is_flag=True,
        help='Show what would have been imported')
@click.option('-v', '--verbose', 'verbose', is_flag=True,
        help='Show verbose details on what was imported')
@click.argument('jsonfile', type=click.Path(exists=True))
def command_import_pinboard(jsonfile, verbose, dry_run):
    """ Import entries from a Pinboard JSON export """
    # Load JSON file
    with open(jsonfile, 'r', encoding='utf-8') as f:
        import_list = reversed(json.load(f))  # Reverse list to process in oldest -> newest order

    # Load existing entries, for de-duplication
    db_entry_list = db_load_db()

    # Process all the import entries
    dry_run_prefix = '(dry-run) ' if dry_run else ''
    edit_list = []
    for import_item in import_list:
        # Map import schema to local schema
        import_entry = {
            'url': import_item['href'],
            'title': import_item.get('description',"").replace("\n"," ").replace("\r","").strip(),
            'extended': import_item.get('extended',"").strip(),
            'tags': sorted(import_item.get('tags',"").split(' ')) if len(import_item.get('tags')) > 0 else [],
            'created_date': datetime.datetime.strptime(
                import_item['time'],"%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
            }
        import_entry = db_entry_internalize_trim(import_entry)

        # If there's an existing entry with this same url, update that entry instead
        matches = [ entry for entry in db_entry_list if import_entry['url'] == entry['url'] ]
        if len(matches) > 1:
            raise Exception('Internal Error: found multiple matching entries for url "{}"'.format(import_entry['url']))
        if len(matches) > 0:
            entry = copy.deepcopy(matches[0])  # Make a mutable copy of 'entry'

            # Look for difference between entry vs import_entry
            changed = False
            for key in import_entry:
                if entry.get(key) != import_entry.get(key):
                    if verbose:
                        click.echo(
                            format_colorize('{}#[fg=yellow]{}#[none] updated {}: "{}" --> "{}"').format(
                            dry_run_prefix, entry['id'][:8], key, entry.get(key), import_entry.get(key)))
                    entry[key] = import_entry[key]
                    changed = True
                if changed:
                    edit_list.append(entry)
        # Othewise create a brand-new entry
        else:
            entry = copy.deepcopy(import_entry)
            entry['id'] = db_entry_generate_id()
            if verbose:
                click.echo('{}imported {}: {}'.format(dry_run_prefix, entry['id'][0:8], entry['url']))
            edit_list.append(entry)

    if len(edit_list) < 1:
        sys.exit('No changes to import')
    changed_list = db_entry_list_update(db_entry_list, edit_list)
    if changed_list is None:
        sys.exit('No changes found')
    click.echo('{}imported {} entries'.format(dry_run_prefix, len(changed_list)))

    if dry_run:
        return
    db_save_db(db_entry_list)
    commit_desc = 'Import pinboard-json \'{}\''.format(click.format_filename(jsonfile, shorten=True))
    db_git_commit(commit_desc)

if __name__ == '__main__':
    cli()
