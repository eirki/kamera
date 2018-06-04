#! /usr/bin/env python3.6
# coding: utf-8
from kamera.logger import log

import sys
import os
from hashlib import sha256
import hmac
import json
import datetime as dt
from pathlib import Path

from flask import Flask, request, abort, Response, g
import redis
import rq
import rq_dashboard
import redis_lock
import dropbox

from kamera import task
from kamera import config
from kamera.mediatypes import KameraEntry

from typing import Optional, Generator


app = Flask(__name__)

redis_client = redis.from_url(config.redis_url)
queue = rq.Queue(connection=redis_client)
listen = ['default']
running_jobs_registry = rq.registry.StartedJobRegistry(connection=redis_client)


def get_redis_client():
    redis_client = getattr(g, '_redis_client', None)
    if redis_client is None:
        redis_client = redis.from_url(config.redis_url)
        g._redis_client = redis_client
    return redis_client


# Define and apply rq-dashboard authenication,
# from https://github.com/eoranged/rq-dashboard/issues/75
def check_auth(username, password) -> bool:
    return (
        username == config.rq_dashboard_username and
        password == config.rq_dashboard_password
    )


def basic_auth() -> Optional[Response]:
    """Ensure basic authorization."""
    error_resp = Response(
        'Could not verify your access level for that URL.\n'
        'You have to login with proper credentials', 401,
        {'WWW-Authenticate': 'Basic realm="Login Required"'}
    )

    auth = request.authorization
    return (error_resp
            if not (auth or check_auth(auth.username, auth.password))
            else None)


app.config.from_object(rq_dashboard.default_settings)
app.config["REDIS_URL"] = config.redis_url
rq_dashboard.blueprint.before_request(basic_auth)
app.register_blueprint(rq_dashboard.blueprint, url_prefix="/rq")


def set_time_of_request(account_id: str):
    now = dt.datetime.utcnow()
    redis_client.hset(f"user:{account_id}", "last_request_at", now.timestamp())


def time_since_last_request_greater_than_limit(account_id: str) -> bool:
    timestamp = redis_client.hget(f"user:{account_id}", "last_request_at")
    if timestamp is None:
        return True
    last_request_at = dt.datetime.utcfromtimestamp(int(timestamp))
    delta = dt.datetime.utcnow() - last_request_at
    if delta >= dt.timedelta(seconds=config.flask_rate_limit):
        return True
    return False


@app.route('/')
def hello_world() -> str:
    return f"{config.app_id}.home"


@app.route('/kamera', methods=['GET'])
def verify() -> str:
    '''Respond to the webhook verification (GET request) by echoing back the challenge parameter.'''

    return request.args.get('challenge')


def check_enqueue_entries(account_id: str):
    queued_and_running_jobs = (
        set(queue.job_ids) | set(running_jobs_registry.get_job_ids())
    )
    token = config.get_dbx_token(redis_client, account_id)
    dbx = dropbox.Dropbox(token)
    for entry in dbx_list_entries(dbx, account_id, config.uploads_path):
        if entry.job_id in queued_and_running_jobs:
            continue
        log.info(f"enqueing entry: {entry}")
        queue.enqueue_call(
            func=task.process_entry,
            args=(
                entry,
                config.review_path,
                config.backup_path,
                config.errors_path
            ),
            result_ttl=600,
            job_id=entry.job_id
        )


@app.route('/kamera', methods=['POST'])
def webhook() -> str:
    log.info("request incoming")
    signature = request.headers.get('X-Dropbox-Signature')
    digest = hmac.new(config.APP_SECRET, request.data, sha256).hexdigest()
    if not hmac.compare_digest(signature, digest):
        abort(403)

    accounts = json.loads(request.data)["list_folder"]["accounts"]
    for account_id in accounts:
        if not time_since_last_request_greater_than_limit(account_id):
            log.info(f"rate limit exceeded: {account_id}")
            continue
        lock = redis_lock.Lock(redis_client, name=account_id, expire=60)
        if not lock.acquire(blocking=False):
            log.info(f"User request already being processed: {account_id}")
            continue
        try:
            check_enqueue_entries(account_id)
        except Exception:
            log.exception(f"Exception occured, when handling request: {account_id}")
        finally:
            set_time_of_request(account_id)
            lock.release()
            log.info("request finished")
    return ""


def dbx_list_entries(
    dbx: dropbox.Dropbox,
    account_id: str,
    path: Path
) -> Generator[KameraEntry, None, None]:
    result = dbx.files_list_folder(
        path=path.as_posix(),
        include_media_info=True
    )
    while True:
        log.info(f"Entries in upload folder: {len(result.entries)}")
        for entry in result.entries:
            # Ignore deleted files, folders
            if not (entry.path_lower.endswith(config.media_extensions) and
                    isinstance(entry, dropbox.files.FileMetadata)):
                continue

            dbx_photo_metadata = entry.media_info.get_metadata() if entry.media_info else None
            kamera_entry = KameraEntry(account_id, entry, dbx_photo_metadata)
            yield kamera_entry

        # Repeat only if there's more to do
        if result.has_more:
            result = dbx.files_list_folder_continue(result.cursor)
        else:
            break


def main(mode: str) -> None:
    if mode == "server":
        redis_lock.reset_all()
        app.run()
    else:
        if mode == "worker":
            with rq.Connection(redis_client):
                worker = rq.Worker(list(map(rq.Queue, listen)))
                worker.work()
        elif mode == "run_once":
            account_id = sys.argv[2]
            dbx = task.Cloud(account_id).dbx  # Instantiate cloud obj since dbx will cached
            for entry in dbx_list_entries(dbx, account_id, config.uploads_path):
                task.process_entry(
                    entry=entry,
                    out_dir=config.review_path,
                    backup_dir=config.backup_path,
                    error_dir=config.errors_path,
                )


if __name__ == '__main__':
    main(sys.argv[1])
