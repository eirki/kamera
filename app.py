#! /usr/bin/env python3.6
# coding: utf-8
from kamera.logger import log

from hashlib import sha256
import hmac

from flask import Flask, request, abort, Response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import rq
# from rq.job import Job

from worker import conn
from kamera import task
from kamera import config
from kamera import cloud


app = Flask(__name__)
limiter = Limiter(app, key_func=get_remote_address)
queue = rq.Queue(connection=conn)


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
    for entry in cloud.list_entries():
        if entry.name not in queued_jobs:
            job = queue.enqueue_call(
                func=task.process_entry,
                args=(entry,),
                result_ttl=5000,
                job_id=entry.name
            )
            log.info(job.get_id())
    log.info("request finished")
    return ""


def main():
    cloud.dbx.users_get_current_account()
    app.run()


if __name__ == '__main__':
    main()
