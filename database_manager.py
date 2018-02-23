#! python3.6
# coding: utf-8
import MySQLdb
from MySQLdb.cursors import Cursor

import config

import dropbox

from typing import Set


class LoggingCursor(Cursor):
    def execute(self, query, args=None):
        print(query % args if args else query)
        super().execute(query, args)

    def executemany(self, query, args=None):
        print(query % args if args else query)
        super().executemany(query, args)


def connect():
    connection = MySQLdb.connect(
        host=config.db_host,
        user=config.db_user,
        passwd=config.db_passwd,
        db=config.db_name,
        charset="utf8",
        cursorclass=LoggingCursor
    )
    return connection


def add_entry_to_media_list(cursor: Cursor, media: dropbox.files.Metadata):
    sql_cmd = "INSERT INTO entries_processing (name) VALUES (%(name)s)"
    sql_data = {"name": media.name}
    cursor.execute(sql_cmd, sql_data)


def get_media_list(cursor: Cursor) -> Set[str]:
    cursor.execute("SELECT * FROM entries_processing")
    media_list = set(name[0] for name in cursor.fetchall())
    print(f"media: {media_list}")
    return media_list


def remove_entry_from_media_list(cursor: Cursor, media: dropbox.files.Metadata):
    sql_cmd = "DELETE FROM entries_processing where name = %(name)s"
    sql_data = {"name": media.name}
    cursor.execute(sql_cmd, sql_data)
