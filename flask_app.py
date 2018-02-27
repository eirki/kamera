#! /usr/bin/env python3.6
# coding: utf-8
from logger import log

from hashlib import sha256
import hmac
import contextlib
from flask import Flask, request, abort, g
import uwsgi

import config
import cloud
import database_manager as db

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


@app.route('/')
def hello_world() -> str:
    return f'Hello'


@app.route('/kamera', methods=['GET'])
def verify():
    '''Respond to the webhook verification (GET request) by echoing back the challenge parameter.'''

    return request.args.get('challenge')


@contextlib.contextmanager
def lock():
    """wrapper around uwsgi.lock"""
    uwsgi.lock()
    try:
        yield
    finally:
        uwsgi.unlock()


@app.route('/kamera', methods=['POST'])
def webhook() -> str:
    signature = request.headers.get('X-Dropbox-Signature')
    log.info("request incoming")
    if not hmac.compare_digest(signature, hmac.new(config.APP_SECRET, request.data, sha256).hexdigest()):
        log.info(abort)
        abort(403)

    with lock(), get_db() as cursor:
        media_list = db.get_media_list(cursor)
        for entry in cloud.list_entries():
            if entry.name not in media_list:
                db.add_entry_to_media_list(cursor, entry)
    log.info("request finished")
    return ""
