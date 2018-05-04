#! /usr/bin/env python3.6
# coding: utf-8
from kamera.logger import log

from pathlib import Path
import datetime as dt
import time
import sys

import pytz
from timezonefinderL import TimezoneFinder

from kamera import config
from kamera import cloud
from kamera import image_processing
from kamera import recognition

from kamera.mediatypes import KameraEntry


def parse_date(entry: KameraEntry) -> dt.datetime:

    naive_date = entry.time_taken if entry.time_taken is not None else entry.client_modified

    utc_date = naive_date.replace(tzinfo=dt.timezone.utc)

    if entry.location is not None:
        img_tz = TimezoneFinder().timezone_at(
            lat=entry.location.latitude,
            lng=entry.location.longitude
        )
        if img_tz:
            local_date = utc_date.astimezone(tz=pytz.timezone(img_tz))
            return local_date

    local_date = utc_date.astimezone(tz=pytz.timezone(config.default_tz))
    return local_date


def process_entry(
        entry: KameraEntry,
        out_dir: Path,
        backup_dir: Path,
        error_dir: Path):
    log.info(f"{entry}: Processing")
    start_time = dt.datetime.now()
    log.info(entry)
    try:
        if entry.path.suffix.lower() in {".mp4", ".gif"}:
            date = parse_date(entry)
            cloud.copy_entry(entry.path, out_dir, date)
        else:
            date = parse_date(entry)

            orig_data, response = cloud.dbx.files_download(entry.path.as_posix())
            new_data, exif_date = image_processing.main(
                data=response.raw.data,
                filepath=entry.path,
                date=date,
                location=entry.location,
                dimensions=entry.dimensions,
            )
            if exif_date is not None:
                date = exif_date

            if new_data is None:
                cloud.copy_entry(entry.path, out_dir, date)
            else:
                cloud.upload_entry(entry.path, new_data, out_dir, date)

        cloud.move_entry(entry.path, out_dir=backup_dir, date=date)
    except Exception:
        log.exception(f"Exception occured, moving to Error subfolder: {entry}")
        cloud.move_entry(entry.path, out_dir=error_dir)
    finally:
        end_time = dt.datetime.now()
        duration = end_time - start_time
        log.info(f"{entry}, duration: {duration}")
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


if __name__ == '__main__':
    main(*sys.argv[1:])
