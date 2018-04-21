#! /usr/bin/env python3.6
# coding: utf-8
from kamera.logger import log

from hashlib import sha256
import hmac

from flask import Flask, request, abort, g

from kamera import config
from kamera import cloud
from kamera import database_manager as db

cloud.dbx.users_get_current_account()

application = Flask(__name__)


def get_db():
    db_connection = getattr(g, '_database', None)
    if db_connection is None:

        connection, tunnel = db.connect_ssh()
        g._database = db_connection
        g.tunnel = tunnel
    return db_connection


@application.teardown_appcontext
def close_connection(exception):
    db_connection = getattr(g, '_database', None)
    if db_connection is not None:
        db_connection.close()
        tunnel = getattr(g, '_tunnel', None)
        tunnel.stop()


@application.route('/')
def hello_world() -> str:
    return f"{config.app_id}.home"


@application.route('/kamera', methods=['GET'])
def verify():
    '''Respond to the webhook verification (GET request) by echoing back the challenge parameter.'''

    return request.args.get('challenge')


@application.route('/kamera', methods=['POST'])
def webhook() -> str:
    log.info("request incoming")
    signature = request.headers.get('X-Dropbox-Signature')
    digest = hmac.new(config.APP_SECRET, request.data, sha256).hexdigest()
    if not hmac.compare_digest(signature, digest):
        log.info(abort)
        abort(403)

    with get_db() as cursor:
        entry_queue = db.get_queued_entries(cursor)
        for entry in cloud.list_entries():
            if entry not in entry_queue:
                db.add_entry_to_queue(cursor, entry)
    log.info("request finished")
    return ""


def main():
    application.run()


if __name__ == '__main__':
    main()
