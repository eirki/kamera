#! /usr/bin/env python3.6
# coding: utf-8
from logger import log

from pathlib import Path
import datetime as dt
import sys
from hashlib import sha256
import hmac
from threading import Thread

from flask import Flask, request, abort
import contextlib
import uwsgi
import pytz
from timezonefinderL import TimezoneFinder

import config
import cloud
import image_processing
import recognition

from typing import Optional
import dropbox

app = Flask(__name__)


def parse_date(
        entry: dropbox.files.Metadata,
        dbx_photo_metadata: Optional[dropbox.files.FileMetadata] = None
        ) -> dt.datetime:

    if dbx_photo_metadata and dbx_photo_metadata.time_taken:
        naive_date = dbx_photo_metadata.time_taken
    else:
        naive_date = entry.client_modified

    utc_date = naive_date.replace(tzinfo=dt.timezone.utc)

    if dbx_photo_metadata and dbx_photo_metadata.location:
        img_tz = TimezoneFinder().timezone_at(
            lat=dbx_photo_metadata.location.latitude,
            lng=dbx_photo_metadata.location.longitude
        )
        if img_tz:
            local_date = utc_date.astimezone(tz=pytz.timezone(img_tz))
            return local_date

    local_date = utc_date.astimezone(tz=config.default_tz)
    return local_date


def process_entry(
        entry,
        out_dir: Path,
        backup_dir: Path,
        error_dir: Path):
    log.info(f"{entry.name}: Processing")
    start_time = dt.datetime.now()
    log.info(entry)
    try:
        filepath = Path(entry.path_display)
        if filepath.suffix.lower() in (".mp4", ".gif"):
            date = parse_date(entry)
            cloud.copy_entry(filepath, out_dir, date)

        else:
            if entry.media_info:
                dbx_photo_metadata = entry.media_info.get_metadata()
                dimensions = dbx_photo_metadata.dimensions
                location = dbx_photo_metadata.location
                date = parse_date(entry, dbx_photo_metadata)
            else:
                dimensions = None
                location = None
                date = parse_date(entry)

            orig_data, response = cloud.dbx.files_download(filepath.as_posix())
            new_data, exif_date = image_processing.main(
                data=response.raw.data,
                filepath=filepath,
                date=date,
                location=location,
                dimensions=dimensions,
            )
            if exif_date is not None:
                date = exif_date

            if new_data is None:
                cloud.copy_entry(filepath, out_dir, date)
            else:
                cloud.upload_entry(filepath, new_data, out_dir, date)

        cloud.move_entry(filepath, out_dir=backup_dir, date=date)
    except Exception:
        log.exception(f"Exception occured, moving to Error subfolder: {filepath.name}")
        cloud.move_entry(filepath, out_dir=error_dir)
    finally:
        end_time = dt.datetime.now()
        duration = end_time - start_time
        log.info(f"{entry.name}, duration: {duration}")
        log.info("\n")


def run_once():
    entries = cloud.list_entries()
    for entry in entries:
        process_entry(
            entry=entry,
            out_dir=config.kamera_db_folder,
            backup_dir=config.backup_db_folder,
            error_dir=config.errors_db_folder
        )


@contextlib.contextmanager
def lock():
    """wrapper around uwsgi.lock"""
    uwsgi.lock()
    try:
        yield
    finally:
        uwsgi.unlock()


@app.route('/')
def hello_world() -> str:
    return f'Hello'


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

    kwargs = {
        "out_dir": config.kamera_db_folder,
        "backup_dir": config.backup_db_folder,
        "error_dir": config.errors_db_folder,
    }
    with lock():
        entries = cloud.list_entries()
        threads = [
            Thread(target=process_entry, args=(entry,), kwargs=kwargs)
            for entry in entries
        ]
        [thread.start() for thread in threads]
        [thread.join() for thread in threads]
    log.info("request finished")
    return ""


def main(mode=None):
    recognition.load_encodings(home_path=config.home)
    cloud.dbx.users_get_current_account()
    if mode == "test":
        run_once()
    else:
        app.debug = True
        app.run()


if __name__ == '__main__':
    main(*sys.argv[1:])
