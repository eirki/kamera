#! /usr/bin/env python3.6
# coding: utf-8
from kamera.logger import log

from pathlib import Path
import datetime as dt
from functools import partial

import pytz
from timezonefinderL import TimezoneFinder
import dropbox
import requests
import redis

from kamera import config
from kamera import image_processing
from kamera.mediatypes import KameraEntry

from typing import Callable, Optional, Dict


class Cloud:
    dbx_cache: Dict[str, dropbox.Dropbox] = {}
    settings_cache: Dict[str, Dict] = {}

    redis_client: redis.Redis = None

    def __init__(self, account_id):
        if self.redis_client is None:
            self.redis_client = redis.from_url(config.redis_url)

        self.account_id = account_id
        try:
            self.dbx = self.dbx_cache[account_id]
            self.settings = self.settings_cache[account_id]
        except KeyError:
            self.dbx = dropbox.Dropbox(config.get_dbx_token(self.redis_client, account_id))
            self.dbx_cache[account_id] = self.dbx
            self.settings = config.Settings(self.dbx)
            self.settings_cache[account_id] = self.settings

    def _execute_transfer(self, transfer_func: Callable, destination_folder: Path):
        try:
            transfer_func()
        except requests.exceptions.SSLError:
            log.info("Encountered SSL error during transfer. Trying again")
            transfer_func()
        except dropbox.exceptions.BadInputError:
            log.info(f"Making folder: {destination_folder}")
            self.dbx.files_create_folder(destination_folder.as_posix())
            transfer_func()

    def move_entry(
            self,
            from_path: Path,
            out_dir: Path,
            date: Optional[dt.datetime] = None
    ):
        if date is not None:
            destination = (
                out_dir /
                str(date.year) /
                self.settings.folder_names[date.month] /
                from_path.name
            )
        else:
            destination = out_dir / from_path.name

        transfer_func = partial(
            self.dbx.files_move,
            from_path=from_path.as_posix(),
            to_path=destination.as_posix(),
            autorename=True
        )

        log.info(f"{from_path.stem}: Moving to dest: {destination}")
        self._execute_transfer(transfer_func, destination.parent)

    def copy_entry(
            self,
            from_path: Path,
            out_dir: Path,
            date: dt.datetime
    ):
        destination = (
            out_dir /
            str(date.year) /
            self.settings.folder_names[date.month] /
            from_path.name
        )

        transfer_func = partial(
            self.dbx.files_copy,
            from_path=from_path.as_posix(),
            to_path=destination.as_posix(),
            autorename=True
        )

        log.info(f"{from_path.stem}: Copying to dest: {destination}")
        self._execute_transfer(transfer_func, destination.parent)

    def upload_entry(
            self,
            from_path: Path,
            new_data: bytes,
            out_dir: Path,
            date: dt.datetime
    ):
        new_name = from_path.with_suffix(".jpg").name
        destination = (
            out_dir /
            str(date.year) /
            self.settings.folder_names[date.month] /
            new_name
        )

        transfer_func = partial(
            self.dbx.files_upload,
            f=new_data,
            path=destination.as_posix(),
            autorename=True
        )

        log.info(f"{destination.stem}: Uploading to dest: {destination}")
        self._execute_transfer(transfer_func, destination.parent)

    def download_entry(self, path_str: str):
        try:
            return self.dbx.files_download(path_str)
        except requests.exceptions.SSLError:
            log.info("Encountered SSL error during transfer. Trying again")
            return self.dbx.files_download(path_str)


def parse_date(entry: KameraEntry, settings: config.Settings) -> dt.datetime:
    naive_date = entry.time_taken if entry.time_taken is not None else entry.client_modified
    utc_date = naive_date.replace(tzinfo=dt.timezone.utc)
    if entry.coordinates is not None:
        img_tz = TimezoneFinder().timezone_at(
            lat=entry.coordinates.latitude,
            lng=entry.coordinates.longitude
        )
        if img_tz:
            local_date = utc_date.astimezone(tz=pytz.timezone(img_tz))
            return local_date
    local_date = utc_date.astimezone(tz=pytz.timezone(settings.default_tz))
    return local_date


def process_entry(
        entry: KameraEntry,
        out_dir: Path,
        backup_dir: Path,
        error_dir: Path,
):
    log.info(f"{entry}: Processing")
    start_time = dt.datetime.now()
    cloud = Cloud(entry.account_id)
    try:
        date = parse_date(entry, cloud.settings)
        if entry.path.suffix.lower() in config.video_extensions:
            cloud.copy_entry(entry.path, out_dir, date)
        elif entry.path.suffix.lower() in config.image_extensions:
            _, response = cloud.download_entry(entry.path.as_posix())
            new_data = image_processing.main(
                data=response.raw.data,
                filepath=entry.path,
                date=date,
                settings=cloud.settings,
                coordinates=entry.coordinates,
                dimensions=entry.dimensions,
            )

            if new_data is None:
                cloud.copy_entry(entry.path, out_dir, date)
            else:
                cloud.upload_entry(entry.path, new_data, out_dir, date)
        else:
            return
        cloud.move_entry(entry.path, out_dir=backup_dir, date=date)
    except Exception:
        log.exception(f"Exception occured, moving to Error subfolder: {entry}")
        cloud.move_entry(entry.path, out_dir=error_dir)
    finally:
        end_time = dt.datetime.now()
        duration = end_time - start_time
        log.info(f"{entry}, duration: {duration}")
        log.info("\n")


def run_once(
        in_dir: Path,
        out_dir: Path,
        backup_dir: Path,
        error_dir: Path,
) -> None:
    entries = Cloud.list_entries(in_dir)
    for entry in entries:
        process_entry(
            entry=entry,
            out_dir=out_dir,
            backup_dir=backup_dir,
            error_dir=error_dir,
        )
