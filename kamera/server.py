#! /usr/bin/env python3.6
# coding: utf-8
from kamera.logger import log

import contextlib
from flask import Flask, g
import uwsgi

from kamera import cloud
from kamera import database_manager as db
import kamera.views

cloud.dbx.users_get_current_account()

app = Flask(__name__)


def get_db():
    db_connection = getattr(g, '_database', None)
    if db_connection is None:
        db_connection = db.connect()
        g._database = db_connection
    return db_connection


@app.teardown_appcontext
def close_connection(exception):
    db_connection = getattr(g, '_database', None)
    if db_connection is not None:
        db_connection.close()


@contextlib.contextmanager
def lock():
    """wrapper around uwsgi.lock"""
    uwsgi.lock()
    try:
        yield
    finally:
        uwsgi.unlock()


def main():
    # app.run() uwsgi does this
    pass


if __name__ == '__main__':
    main()
