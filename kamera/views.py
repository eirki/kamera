#! /usr/bin/env python3.6
# coding: utf-8
from kamera.logger import log

from hashlib import sha256
import hmac
from flask import request, abort

from kamera import config
from kamera.server import app, lock, get_db
from kamera import database_manager as db
from kamera import cloud


@app.route('/')
def hello_world() -> str:
    return f"{config.app_id}.home"


@app.route('/kamera', methods=['GET'])
def verify():
    '''Respond to the webhook verification (GET request) by echoing back the challenge parameter.'''

    return request.args.get('challenge')


@app.route('/kamera', methods=['POST'])
def webhook() -> str:
    log.info("request incoming")
    signature = request.headers.get('X-Dropbox-Signature')
    digest = hmac.new(config.APP_SECRET, request.data, sha256).hexdigest()
    if not hmac.compare_digest(signature, digest):
        log.info(abort)
        abort(403)

    with lock(), get_db() as cursor:
        media_list = db.get_media_list(cursor)
        for entry in cloud.list_entries():
            if entry.name not in media_list:
                db.add_entry_to_media_list(cursor, entry)
    log.info("request finished")
    return ""

