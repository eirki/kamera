#! /usr/bin/env python3.6
# coding: utf-8
from kamera.logger import log

from hashlib import sha256
import hmac
import json
import datetime as dt
from pathlib import Path

from flask import Flask, request, abort, g
import redis
import rq
import rq_dashboard
from rq_dashboard.cli import add_basic_auth
import redis_lock
import dropbox

from kamera.task import Task
from kamera import config

from typing import Optional, Generator, Tuple, Set


app = Flask(__name__)

redis_client = redis.from_url(config.redis_url)
queue = rq.Queue(connection=redis_client)
running_jobs_registry = rq.registry.StartedJobRegistry(connection=redis_client)


def get_redis_client():
    redis_client = getattr(g, "_redis_client", None)
    if redis_client is None:
        redis_client = redis.from_url(config.redis_url)
        g._redis_client = redis_client
    return redis_client


app.config.from_object(rq_dashboard.default_settings)
app.config["REDIS_URL"] = config.redis_url
add_basic_auth(
    rq_dashboard.blueprint, config.rq_dashboard_username, config.rq_dashboard_password
)
app.register_blueprint(rq_dashboard.blueprint, url_prefix="/rq")


def set_time_of_request(account_id: str):
    now = dt.datetime.utcnow()
    get_redis_client().hset(f"user:{account_id}", "last_request_at", now.timestamp())


def time_since_last_request_greater_than_limit(account_id: str) -> bool:
    timestamp = get_redis_client().hget(f"user:{account_id}", "last_request_at")
    if timestamp is None:
        return True
    last_request_at = dt.datetime.fromtimestamp(float(timestamp))
    delta = dt.datetime.utcnow() - last_request_at
    if delta >= dt.timedelta(seconds=config.flask_rate_limit):
        return True
    return False


@app.route("/")
def hello_world() -> str:
    return f"{config.app_id}.home"


@app.route("/kamera", methods=["GET"])
def verify() -> str:
    """Respond to the webhook verification (GET request) by echoing back the challenge parameter."""

    return request.args.get("challenge")


@app.route("/queued/<account_id>", methods=["GET"])
def get_n_queued(account_id: str) -> str:
    queued_and_running_jobs = get_queued_and_running_jobs()
    account_jobs = [
        job_id for job_id in queued_and_running_jobs if job_id.startswith(account_id)
    ]
    n_queued = len(account_jobs)
    return str(n_queued)


def get_queued_and_running_jobs() -> Set[str]:
    queued_and_running_jobs = set(queue.job_ids) | set(
        running_jobs_registry.get_job_ids()
    )
    return queued_and_running_jobs


def check_enqueue_entries(account_id: str):
    queued_and_running_jobs = get_queued_and_running_jobs()
    log.debug(queued_and_running_jobs)
    token = config.get_dbx_token(get_redis_client(), account_id)
    dbx = dropbox.Dropbox(token)
    for entry, metadata in dbx_list_entries(dbx, config.uploads_path):
        job_id = f"{account_id}:{entry.name}"
        if job_id in queued_and_running_jobs:
            continue
        log.info(f"enqueing entry: {entry}")
        task = Task(
            account_id,
            entry,
            metadata,
            config.review_path,
            config.backup_path,
            config.errors_path,
        )
        queue.enqueue(task.process_entry, result_ttl=600, job_id=job_id)


@app.route("/kamera", methods=["POST"])
def webhook() -> str:
    log.info("request incoming")
    signature = request.headers.get("X-Dropbox-Signature")
    digest = hmac.new(config.APP_SECRET, request.data, sha256).hexdigest()
    if not hmac.compare_digest(signature, digest):
        abort(403)

    accounts = json.loads(request.data)["list_folder"]["accounts"]
    for account_id in accounts:
        if not time_since_last_request_greater_than_limit(account_id):
            log.info(f"rate limit exceeded: {account_id}")
            continue
        lock = redis_lock.Lock(get_redis_client(), name=account_id, expire=60)
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
    dbx: dropbox.Dropbox, path: Path
) -> Generator[
    Tuple[dropbox.files.FileMetadata, Optional[dropbox.files.PhotoMetadata]], None, None
]:
    result = dbx.files_list_folder(path=path.as_posix(), include_media_info=True)
    if len(result.entries) == 0:
        # Retry - sometimes webhook fires to quickly?
        result = dbx.files_list_folder(path=path.as_posix(), include_media_info=True)
    while True:
        log.info(f"Entries in upload folder: {len(result.entries)}")
        log.debug(result.entries)
        for entry in result.entries:
            # Ignore deleted files, folders
            if not (
                entry.path_lower.endswith(config.media_extensions)
                and isinstance(entry, dropbox.files.FileMetadata)
            ):
                continue

            metadata = entry.media_info.get_metadata() if entry.media_info else None
            yield entry, metadata

        # Repeat only if there's more to do
        if result.has_more:
            result = dbx.files_list_folder_continue(result.cursor)
        else:
            break
