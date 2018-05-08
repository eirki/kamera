#! /usr/bin/env python3.6
# coding: utf-8
from kamera.logger import log

import sys
import os
from hashlib import sha256
import hmac

import redis
from flask import Flask, request, abort, Response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import rq

from kamera import task
from kamera import config
from kamera import cloud


app = Flask(__name__)
limiter = Limiter(app, key_func=get_remote_address)

redis_url = os.getenv('REDISTOGO_URL', 'redis://localhost:6379')
conn = redis.from_url(redis_url)
queue = rq.Queue(connection=conn)
listen = ['default']


redis_url = os.getenv('REDISTOGO_URL', 'redis://localhost:6379')
r = redis.from_url(redis_url)


@app.errorhandler(429)
def ratelimit_handler(e):
    log.info("rate limit exceeded, autoreturning 200 OK")
    return Response(status=200)


@app.route('/')
def hello_world() -> str:
    return f"{config.app_id}.home"


@app.route('/kamera', methods=['GET'])
def verify():
    '''Respond to the webhook verification (GET request) by echoing back the challenge parameter.'''

    return request.args.get('challenge')


@app.route('/kamera', methods=['POST'])
@limiter.limit(config.flask_rate_limit)
def webhook() -> str:
    log.info("request incoming")
    signature = request.headers.get('X-Dropbox-Signature')
    digest = hmac.new(config.APP_SECRET, request.data, sha256).hexdigest()
    if not hmac.compare_digest(signature, digest):
        log.info(abort)
        abort(403)

    queued_jobs = set(queue.job_ids)
    for entry in cloud.list_entries(config.uploads_path):
        if entry.name not in queued_jobs:
            job = queue.enqueue_call(
                func=task.process_entry,
                args=(
                    entry,
                    config.review_path,
                    config.backup_path,
                    config.errors_path
                ),
                result_ttl=5000,
                job_id=entry.name
            )
            log.info(job.get_id())
    log.info("request finished")
    return ""


def main():
    cloud.dbx.users_get_current_account()
    config.load_settings(cloud.dbx)
    if sys.argv[1] == "server":
        app.run()
    else:
        config.load_location_data(cloud.dbx)
        config.load_recognition_data(cloud.dbx)
        if sys.argv[1] == "worker":
            with rq.Connection(conn):
                worker = rq.Worker(list(map(rq.Queue, listen)))
                worker.work()
        elif sys.argv[1] == "run_once":
            in_dir = sys.argv[2] if len(sys.argv[2]) >= 3 else config.uploads_path
            out_dir = sys.argv[3] if len(sys.argv[3]) >= 4 else config.review_path
            backup_dir = sys.argv[4] if len(sys.argv[4]) >= 5 else config.backup_path
            error_dir = sys.argv[5] if len(sys.argv[5]) >= 6 else config.errors_path
            task.run_once(
                in_dir=in_dir,
                out_dir=out_dir,
                backup_dir=backup_dir,
                error_dir=error_dir,
            )


if __name__ == '__main__':
    main()
