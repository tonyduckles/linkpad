# Linkpad: A command-line bookmark manager
# https://github.com/tonyduckles/linkpad
# Copyright (c) 2017 Tony Duckles

# Features:
# =========
# - Supports multiple separate bookmark databases under ~/.linkpad/<db>/.
# - Each database is version-controlled via Git, which -- aside from version
#   control -- provides an easy way to synchronize databases between machines.
#
# Database Structure:
# ===================
# - Bookmarks are YAML files stored at $db/entries/<id>.yml
# - Index of bookmarks is maintained in plain text file at $db/index
# - Optional cache of full-text webpage is stored at $db/cache/<id>.html
#
# Dependencies:
# =============
# - python 3.x
# - git

import os
import sys
import click
import yaml
import json
import sh
import datetime
import pkg_resources

VERSION=0.1
PROGRAM=os.path.basename(sys.argv[0])

LINKPAD_BASEDIR=os.environ.get('LINKPAD_BASEDIR') or os.path.expanduser('~/.linkpad')
LINKPAD_DBNAME=os.environ.get('LINKPAD_DBNAME') or "default"
LINKPAD_DB=os.path.join(LINKPAD_BASEDIR, LINKPAD_DBNAME)

INDEXFILE_FIELDS = { 'id': 1,
                     'url': 2,
                     'title': 3,
                     'tags': 4,
                     'created_date': 5 }

DB_DATETIMEFMT_INTERNAL_FULL    = "%Y-%m-%dT%H:%M:%SZ%z"   # Ex: "2011-09-23T04:36:00Z+0000"
DB_DATETIMEFMT_INTERNAL_COMPACT = "%Y-%m-%dT%H:%M:%SZ"     # Ex: "2011-09-23T04:36:00Z"
DB_DATETIMEFMT_EXTERNAL         = "%Y-%m-%d %H:%M:%S %Z"   # Ex: "2011-09-23 04:36:00 UTC"

def db_index_parse_row(line):
    """ Given a raw line from the DB index file, map that to a dict """
    line_fields = line.split('\t')
    index_entry = {}
    for name, pos in INDEXFILE_FIELDS.items():
        index_entry[name] = line_fields[pos-1]
    return index_entry

def datetime_utc_to_local(utc_dt):
    """ Convert a UTC datetime to local datetime """
    # https://stackoverflow.com/a/13287083
    return utc_dt.replace(tzinfo=datetime.timezone.utc).astimezone(tz=None)

def datetime_format_relative(utc_dt):
    """ Format date relative to the current time, e.g. "2 hours ago" """
    delta = datetime.datetime.utcnow() - utc_dt
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



CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])
@click.group(context_settings=CONTEXT_SETTINGS)
def cli():
    """
    Linkpad: A command-line bookmark manager
    https://github.com/tonyduckles/linkpad
    """
    pass

@cli.command(name='add', short_help='Add new entry')
@click.option('--comment', 'comment', metavar='TEXT', help='Comment text')
@click.option('--tags', 'tags', metavar='TAGS', help='List of tags')
@click.option('--cache-webpage', 'cache_webpage', is_flag=True, help='Maintain a cached copy of this webpage')
@click.option('--no-edit', 'no_edit', is_flag=True, help='Suppress launching $EDITOR to edit new entry file')
@click.option('--title', 'title', metavar='TITLE', help='Title. By default title will be fetched at run-time')
@click.option('--created-date', 'created_date', metavar='DATE', help='Override creation date')
@click.option('--id', 'id', metavar='ID', help='Override internal ID')
@click.argument('url', required=True)
def command_add(url, id, title, tags, comment, created_date, cache_webpage, no_edit):
    """
    Add a new bookmark to the database using $EDITOR
    """
    click.echo("add: url=%s, title=%s, tags=%s, comment=%s" % (url, title, tags, comment))

@cli.command(name='edit', short_help='Edit existing entry')
@click.argument('id', required=True, nargs=-1)
def command_edit(id):
    """
    Edit an existing bookmark in the database using $EDITOR
    """
    click.echo("edit")

@cli.command(name='grep', short_help='Find entries by grep\'ing through cached webpage')
def command_grep():
    click.echo("grep")

@cli.command(name='list', short_help='List entries')
@click.option('-a', '--all', 'show_all', is_flag=True, help='All entries, including soft-deleted entries')
@click.option('-s', '--sort', 'sort_field', type=click.Choice(['id','url','title','tags','created_date']), default='created_date', help='Sort list by entry field')
@click.option('-f', '--format', 'format', metavar='FORMAT', help='Custom output format')
@click.argument('id', nargs=-1)
def command_list(id, show_all, sort_field, format):
    """ List entries """
    id_list = id

    # Define output line format
    #format = format or "#[fg=yellow]%id_short#[none] %title #[fg=cyan][%url]#[none] #[bold]#[fg=black](%tags)#[none]"
    format = format or "#[fg=yellow]%id_short#[none] %title #[fg=cyan][%url]#[none] #[fg=brightgreen](%tags)#[none] #[fg=brightblack](%created_ago)#[none]"
    format_line=format_colorize(format)  # Evaluate style mnemonics ahead of time

    # Map sort_field to field position in the index file
    sort_pos = INDEXFILE_FIELDS.get(sort_field, 5)

    for line in sh.sort(sh.cat(os.path.join(LINKPAD_DB, 'index')),
                        '-t\t', '-k' + str(sort_pos)):
        index_entry = db_index_parse_row(line)
        created_dt = datetime.datetime.strptime(index_entry['created_date'], "%Y-%m-%d %H:%M:%S %Z")

        # Filter by caller-supplied id list
        if len(id_list) > 0:
            if not any(id_val == index_entry['id'][0:len(id_val)] for id_val in id_list):
                continue

        # Build the final output line based on the 'format' template
        entry_line = format_line
        subs = [
            ('%id_short', index_entry['id'][0:8]),
            ('%id', index_entry['id']),
            ('%url', index_entry['url']),
            ('%title', index_entry['title']),
            ('%tags', index_entry['tags']),
            ('%created_date', created_dt.strftime('%Y-%m-%d %H:%M:%S %Z')),
            ('%created_ago', datetime_format_relative(created_dt))]
        for search, replacement in subs:
            entry_line = entry_line.replace(search, replacement)
        click.echo(entry_line)

@cli.command(name='remove', short_help='Remove entry')
def command_remove():
    click.echo("remove")

@cli.command(name='search', short_help='Find entries by keyword')
def command_search():
    click.echo("search")

@cli.command(name='show', short_help='Show entry contents')
def command_show():
    click.echo("show")

@cli.command(name='tags', short_help='List tags')
def command_tags():
    click.echo("tags")

@cli.command(name='update',
             short_help='Update bookmark titles, re-cache webpage',
             help='Update bookmark titles, re-cache webpage')
@click.option('--all', 'update_all', is_flag=True, help='Refresh all entries')
@click.option('--cache', 'update_cache', is_flag=True, help='Refresh cached webpage')
@click.argument('id', required=False, nargs=-1)
def command_update(id, update_all, update_cache):
    click.echo("update")

@cli.command(name='version', short_help='Show version')
def command_version():
    click.echo("{} {}".format(PROGRAM, VERSION))

@cli.command(name='printf')
@click.argument('format', required=True)
def command_printf(format):
    click.echo(format_colorize(format))

@cli.group(name='database', short_help='Database management')
def command_database():
    pass

@command_database.command(name='name', short_help='Show current database name')
def command_database_name():
    click.echo("db name")

@command_database.command(name='list', short_help='List available database names')
def command_database_list():
    click.echo("db list")

@command_database.command(name='env', short_help='Display the commands to setup the shell environment for a database')
def command_database_env():
    click.echo("db env")

@command_database.command(name='create', short_help='Create a new database')
def command_database_list():
    click.echo("db list")

if __name__ == '__main__':
    cli()
