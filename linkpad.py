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

#class Config(dict):

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
    format=format or "#[fg=yellow]%id_short#[none] %title #[fg=cyan][%url]#[none] #[bold]#[fg=black](%tags)#[none]"

    # Map sort_field to field position in the index file
    sort_pos = INDEXFILE_FIELDS.get(sort_field, 5)

    #click.echo("command_list: id:%s, show_all:%s, sort_field:%s, sort_pos:%s, format:%s" % (id, show_all, sort_field, sort_pos, format))

    args_cat = [ os.path.join(LINKPAD_DB, 'index') ]
    args_sort = [ '-t\t', '-k%s' % (sort_pos) ]
    for line in sh.sort(sh.cat(args_cat[0]), args_sort[0], args_sort[1]):
        index_entry = db_index_parse_row(line)
        click.echo("{} {} {} {} {}".format(
            click.style(index_entry['id'][0:8], fg='yellow'),
            index_entry['title'],
            click.style('['+index_entry['url']+']', fg='cyan'),
            click.style('('+index_entry['tags']+')', fg='green', bold=True),
            click.style(index_entry['created_date'], fg='black', bold=True)))

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
    click.echo("%s %s" % (PROGRAM, VERSION))

@cli.group(name='database', short_help='Manage database')
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
