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

from kamera import config
from kamera import image_processing
from kamera.mediatypes import KameraEntry

from typing import Callable, Generator, Optional


class Cloud:
    dbx: dropbox.Dropbox = None

    @classmethod
    def connect(self):
        if self.dbx is None:
            self.dbx = dropbox.Dropbox(config.DBX_TOKEN)
            self.dbx.users_get_current_account()

    @classmethod
    def list_entries(self, path: Path) -> Generator[KameraEntry, None, None]:
        result = self.dbx.files_list_folder(
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
                kamera_entry = KameraEntry(entry, dbx_photo_metadata)
                yield kamera_entry

            # Repeat only if there's more to do
            if result.has_more:
                result = self.dbx.files_list_folder_continue(result.cursor)
            else:
                break

    @classmethod
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

    @classmethod
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
                config.settings["folder_names"][date.month] /
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

    @classmethod
    def copy_entry(
            self,
            from_path: Path,
            out_dir: Path,
            date: dt.datetime
    ):
        destination = (
            out_dir /
            str(date.year) /
            config.settings["folder_names"][date.month] /
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

    @classmethod
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
            config.settings["folder_names"][date.month] /
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

    @classmethod
    def download_entry(self, path_str: str):
        try:
            return self.dbx.files_download(path_str)
        except requests.exceptions.SSLError:
            log.info("Encountered SSL error during transfer. Trying again")
            return self.dbx.files_download(path_str)


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
    local_date = utc_date.astimezone(tz=pytz.timezone(config.settings["default_tz"]))
    return local_date


def process_entry(
        entry: KameraEntry,
        out_dir: Path,
        backup_dir: Path,
        error_dir: Path):
    log.info(f"{entry}: Processing")
    start_time = dt.datetime.now()
    try:
        date = parse_date(entry)
        if entry.path.suffix.lower() in config.video_extensions:
            Cloud.copy_entry(entry.path, out_dir, date)
        elif entry.path.suffix.lower() in config.image_extensions:
            _, response = Cloud.download_entry(entry.path.as_posix())
            new_data = image_processing.main(
                data=response.raw.data,
                filepath=entry.path,
                date=date,
                location=entry.location,
                dimensions=entry.dimensions,
            )

            if new_data is None:
                Cloud.copy_entry(entry.path, out_dir, date)
            else:
                Cloud.upload_entry(entry.path, new_data, out_dir, date)
        else:
            return
        Cloud.move_entry(entry.path, out_dir=backup_dir, date=date)
    except Exception:
        log.exception(f"Exception occured, moving to Error subfolder: {entry}")
        Cloud.move_entry(entry.path, out_dir=error_dir)
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
