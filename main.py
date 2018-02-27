#! /usr/bin/env python3.6
# coding: utf-8
from logger import log

from pathlib import Path
import datetime as dt
import time
import sys

import pytz
from timezonefinderL import TimezoneFinder

import config
import cloud
import image_processing
import recognition
import database_manager

from typing import Optional
import dropbox


def parse_date(
        entry: dropbox.files.Metadata,
        location: Optional[dropbox.files.GpsCoordinates] = None
        ) -> dt.datetime:
    if "burst" in entry.name.lower():
        naive_date = dt.datetime.strptime(entry.name[20:34], "%Y%m%d%H%M%S")
    else:
        try:
            naive_date = dt.datetime.strptime(entry.name[:19], "%Y-%m-%d %H.%M.%S")
        except ValueError:
            naive_date = entry.client_modified

    utc_date = naive_date.replace(tzinfo=dt.timezone.utc)

    if location is not None:
        img_tz = TimezoneFinder().timezone_at(
            lat=location.latitude,
            lng=location.longitude
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
                date = parse_date(entry, location)
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
        cloud.move_entry(filepath, out_dir=error_dir, subfolder="Errors")
    finally:
        end_time = dt.datetime.now()
        duration = end_time - start_time
        log.info(f"{entry.name}, duration: {duration}")
        log.info("\n")


def main():
    recognition.load_encodings(home_path=config.home)
    cloud.dbx.users_get_current_account()
    db_connection = database_manager.connect()
    try:
        while True:
            with db_connection as cursor:
                media_list = database_manager.get_media_list(cursor)
            if not media_list:
                time.sleep(5)
                continue
            entries = cloud.list_entries()
            for entry in entries:
                try:
                    process_entry(
                        entry=entry,
                        out_dir=config.kamera_db_folder,
                        backup_dir=config.backup_db_folder,
                        error_dir=config.errors_db_folder
                    )
                finally:
                    with db_connection as cursor:
                        database_manager.remove_entry_from_media_list(cursor, entry)
    except KeyboardInterrupt:
        sys.exit()
    finally:
        db_connection.close()


if __name__ == '__main__':
    main()
