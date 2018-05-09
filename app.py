#! /usr/bin/env python3.6
# coding: utf-8
from kamera.logger import log

import sys
import os
from hashlib import sha256
import hmac
import json

from flask import Flask, request, abort, Response
import flask_limiter
import redis
import rq
import rq_dashboard
import redis_lock

from kamera import task
from kamera import config
from kamera import cloud


redis_url = os.environ['REDISTOGO_URL']
conn = redis.from_url(redis_url)
queue = rq.Queue(connection=conn)
listen = ['default']
running_jobs_registry = rq.registry.StartedJobRegistry(connection=conn)

app = Flask(__name__)


# Define and apply rate limiting
@app.errorhandler(429)
def ratelimit_handler(e):
    log.info("rate limit exceeded, autoreturning 200 OK")
    return "rate limit exceeded"


def get_dbx_user_from_req():
    try:
        return str(json.loads(request.data)["delta"]["users"][0])
    except (KeyError, json.decoder.JSONDecodeError):
        return flask_limiter.util.get_remote_address()


limiter = flask_limiter.Limiter(app, key_func=get_dbx_user_from_req)


# Define and apply rq-dashboard authenication,
# from https://github.com/eoranged/rq-dashboard/issues/75
def check_auth(username, password):
    return (
        username == config.rq_dashboard_username and
        password == config.rq_dashboard_password
    )


def basic_auth():
    """Ensure basic authorization."""
    error_resp = Response(
        'Could not verify your access level for that URL.\n'
        'You have to login with proper credentials', 401,
        {'WWW-Authenticate': 'Basic realm="Login Required"'}
    )

    auth = request.authorization
    if not auth or not check_auth(auth.username, auth.password):
        return error_resp


app.config.from_object(rq_dashboard.default_settings)
app.config["REDIS_URL"] = redis_url
rq_dashboard.blueprint.before_request(basic_auth)
app.register_blueprint(rq_dashboard.blueprint, url_prefix="/rq")


@app.route('/')
@limiter.limit(config.flask_rate_limit)
def hello_world() -> str:
    return f"{config.app_id}.home"


@app.route('/kamera', methods=['GET'])
def verify():
    '''Respond to the webhook verification (GET request) by echoing back the challenge parameter.'''

    return request.args.get('challenge')


@app.route('/kamera', methods=['POST'])
@limiter.limit(config.flask_rate_limit)
def webhook() -> str:
    user_id = get_dbx_user_from_req()
    log.info(f"request incoming, from {user_id}")
    signature = request.headers.get('X-Dropbox-Signature')
    digest = hmac.new(config.APP_SECRET, request.data, sha256).hexdigest()
    if not hmac.compare_digest(signature, digest):
        abort(403)

    lock = redis_lock.Lock(conn, name=user_id, expire=60)
    if lock.acquire(blocking=False):
        log.info("lock acquired")
    else:
        log.info("User request already being processed, autoreturning 200 OK")
        return "User request already being processed"

    try:
        queued_and_running_jobs = (
            set(queue.job_ids) | set(running_jobs_registry.get_job_ids())
        )
        log.info(f"queued_and_running_jobs: {queued_and_running_jobs}")
        for entry in cloud.list_entries(config.uploads_path):
            if entry.name in queued_and_running_jobs:
                log.info(f"entry already queued: {entry}")
                continue
            log.info(f"enqueing entry: {entry}")
            job = queue.enqueue_call(
                func=task.process_entry,
                args=(
                    entry,
                    config.review_path,
                    config.backup_path,
                    config.errors_path
                ),
                result_ttl=600,
                job_id=entry.name
            )
            log.info(job.get_id())
    finally:
        lock.release()
        log.info("request finished")
    return ""


def main(mode):
    cloud.dbx.users_get_current_account()
    config.load_settings(cloud.dbx)
    if mode == "server":
        redis_lock.reset_all()
        app.run()
    else:
        config.load_location_data(cloud.dbx)
        config.load_recognition_data(cloud.dbx)
        if mode == "worker":
            with rq.Connection(conn):
                worker = rq.Worker(list(map(rq.Queue, listen)))
                worker.work()
        elif mode == "run_once":
            task.run_once(
                in_dir=config.uploads_path,
                out_dir=config.review_path,
                backup_dir=config.backup_path,
                error_dir=config.errors_path,
            )


if __name__ == '__main__':
    main(sys.argv[1])
