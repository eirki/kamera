#! python3.6
# coding: utf-8
from kamera.logger import log

import MySQLdb
from MySQLdb.cursors import DictCursor
import sshtunnel

from kamera import config
from kamera.mediatypes import KameraEntry

from typing import Set


class Cursor(DictCursor):
    def execute(self, query, args=None):
        log.debug(query % args if args else query)
        super().execute(query, args)

    def executemany(self, query, args=None):
        log.debug(query % args if args else query)
        super().executemany(query, args)


def connect():
    connection = MySQLdb.connect(
        host=config.db_host,
        user=config.db_user,
        passwd=config.db_passwd,
        db=config.db_name,
        charset="utf8",
        cursorclass=Cursor
    )
    return connection


def connect_ssh():
    sshtunnel.SSH_TIMEOUT = 5.0
    sshtunnel.TUNNEL_TIMEOUT = 5.0
    tunnel = sshtunnel.SSHTunnelForwarder(
        config.ssh_host,
        ssh_username=config.ssh_user,
        ssh_password=config.ssh_passwd,
        remote_bind_address=config.ssh_remote_bind_address
    )
    tunnel.start()

    connection = MySQLdb.connect(
        host='127.0.0.1',
        user=config.db_user,
        port=tunnel.local_bind_port,
        passwd=config.db_passwd,
        db=config.db_name,
        charset="utf8",
    )
    return connection, tunnel


def add_entry_to_queue(
        cursor: Cursor,
        entry: KameraEntry,
        ):
    columns = ', '.join(entry.db_data.keys())
    placeholders = ', '.join(['%s'] * len(entry.db_data))
    sql_cmd = f"INSERT INTO entries_processing ({columns}) VALUES ({placeholders})"
    cursor.execute(sql_cmd, entry.db_data.values())


def get_queued_entries(cursor: Cursor) -> Set[KameraEntry]:
    cursor.execute("SELECT * FROM entries_processing")
    result = cursor.fetchall()
    queued_entries = {
        KameraEntry.from_db_data(data)
        for data in result
    }
    return queued_entries


def remove_entry_from_queue(cursor: Cursor, entry: KameraEntry):
    sql_cmd = "DELETE FROM entries_processing where path = %(path)s"
    sql_data = {"path": entry.path.as_posix()}
    cursor.execute(sql_cmd, sql_data)
