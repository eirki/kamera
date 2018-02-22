#! python3.6
# coding: utf-8
import contextlib

import MySQLdb
from MySQLdb.cursors import Cursor

import config

from typing import Optional, List
import dropbox


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


@contextlib.contextmanager
def lock(cursor: Cursor, timeout: int=1):
    """Get a named mysql lock on a DB session
    http://arr.gr/blog/2016/05/mysql-named-locks-in-python-context-managers/
    """
    cursor.execute(
        "SELECT GET_LOCK(%(lock_name)s, %(timeout)s)",
        {"lock_name": config.app_id, "timeout": timeout}
    )
    lock = cursor.fetchone()[0]
    print(f"lock: {lock}")
    if lock:
        try:
            yield
        finally:
            cursor.execute("SELECT RELEASE_LOCK(%(name)s)", {"name": config.app_id})
    else:
        raise RuntimeError(f"Could not obtain named lock {config.app_id} within {timeout} seconds")


def get_entry_from_queue(cursor: Cursor) -> Optional[str]:
    cursor.execute("SELECT name FROM entries_waiting")
    entry = cursor.fetchone()
    print(entry)
    if entry is None:
        return None
    sql_cmd = "DELETE FROM entries_waiting where name = %(name)s"
    sql_data = {"name": entry.name}
    cursor.execute(sql_cmd, sql_data)
    return entry


def populate_queue(cursor: Cursor, entries: List[dropbox.files.Metadata]):
    for entry in entries:
        sql_cmd = "INSERT INTO entries_waiting (name) VALUES (%(name)s)"
        sql_data = {"name": entry.name}
        cursor.execute(sql_cmd, sql_data)


def check_entry_in_processing_list(cursor: Cursor, entry: dropbox.files.Metadata) -> bool:
    cursor.execute("SELECT 1 FROM entries_processing WHERE name = %(name)s", {"name": entry.name})
    entry = cursor.fetchone()
    print(f"proc: {entry}")
    return entry is not None


def add_entry_to_processing_list(cursor: Cursor, entry: dropbox.files.Metadata):
    sql_cmd = "INSERT INTO entries_processing (name) VALUES (%(name)s)"
    sql_data = {"name": entry.name}
    cursor.execute(sql_cmd, sql_data)


def remove_entry_from_processing_list(cursor: Cursor, entry: dropbox.files.Metadata):
    sql_cmd = "DELETE FROM entries_processing where name = %(name)s"
    sql_data = {"name": entry.name}
    cursor.execute(sql_cmd, sql_data)
