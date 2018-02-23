#! /usr/bin/env python3.6
# coding: utf-8
from hashlib import sha256
import hmac

import dropbox
from flask import Flask, request, abort, g
import uwsgi

import config
import database_manager as db
import main

dbx = dropbox.Dropbox(config.DBX_TOKEN)
dbx.users_get_current_account()

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
def hello_world():
    return f'Hello'


@app.route('/kamera', methods=['GET'])
def verify():
    '''Respond to the webhook verification (GET request) by echoing back the challenge parameter.'''

    return request.args.get('challenge')


@app.route('/kamera', methods=['POST'])
def webhook() -> str:
    signature = request.headers.get('X-Dropbox-Signature')
    print("incoming request")
    if not hmac.compare_digest(signature, hmac.new(config.APP_SECRET, request.data, sha256).hexdigest()):
        print(abort)
        abort(403)

    cur = get_db().cursor()
    uwsgi.lock()
    try:
        media_list = db.get_media_list(cur)
        for entry in main.dbx_list_entries():
            if entry.name in media_list:
                continue
            db.add_entry_to_media_list(cur, entry)
        get_db().commit()
    finally:
        uwsgi.unlock()
