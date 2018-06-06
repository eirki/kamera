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

from typing import Callable, Optional, Dict


class Task:
    dbx_cache: Dict[str, dropbox.Dropbox] = {}
    settings_cache: Dict[str, Dict] = {}
    redis_client: redis.Redis = None

    def __init__(
        self,
        account_id: str,
        entry: dropbox.files.FileMetadata,
        metadata: Optional[dropbox.files.PhotoMetadata],
        out_dir: Path,
        backup_dir: Path,
        error_dir: Path,
    ) -> None:
        self.account_id: str = account_id
        self.path: Path = Path(entry.path_display)
        self.name: str = self.path.name
        self.client_modified: dt.datetime = entry.client_modified
        self.time_taken: Optional[dt.datetime] = None
        self.dimensions: Optional[dropbox.files.Dimensions] = None
        self.coordinates: Optional[dropbox.files.GpsCoordinates] = None
        if metadata is not None:
            self.time_taken = metadata.time_taken
            if metadata.dimensions is not None:
                self.dimensions = metadata.dimensions
            if metadata.location is not None:
                self.coordinates = metadata.location

        self.out_dir: Path = out_dir
        self.backup_dir: Path = backup_dir
        self.error_dir: Path = error_dir

        self.dbx: dropbox.Dropbox = None
        self.settings: config.Settings = None

    def __repr__(self):
        return repr(self.name)

    @classmethod
    def load_from_cache(cls, account_id):
        log.debug(cls.dbx_cache)
        log.debug(cls.settings_cache)
        if cls.redis_client is None:
            cls.redis_client = redis.from_url(config.redis_url)

        try:
            dbx = cls.dbx_cache[account_id]
        except KeyError:
            dbx = dropbox.Dropbox(config.get_dbx_token(cls.redis_client, account_id))
            cls.dbx_cache[account_id] = dbx
        try:
            settings = cls.settings_cache[account_id]
            log.debug("Settings loaded from cache")
        except KeyError:
            settings = config.Settings(dbx)
            cls.settings_cache[account_id] = settings
            log.debug("Settings loaded from dbx")
        log.debug(cls.dbx_cache)
        log.debug(cls.settings_cache)
        return dbx, settings

    def process_entry(self):
        start_time = dt.datetime.now()
        log.info(f"{self.name}: Processing")
        self.dbx, self.settings = self.load_from_cache(self.account_id)
        try:
            date = parse_date(
                self.time_taken,
                self.client_modified,
                self.coordinates,
                self.settings.default_tz
            )
            subfolder = Path(str(date.year), self.settings.folder_names[date.month])

            if self.path.suffix.lower() in config.video_extensions:
                copy_entry(self.dbx, self.path, (self.out_dir / subfolder))
            elif self.path.suffix.lower() in config.image_extensions:
                _, response = download_entry(self.dbx, self.path.as_posix())
                new_data = image_processing.main(
                    data=response.raw.data,
                    filepath=self.path,
                    date=date,
                    settings=self.settings,
                    coordinates=self.coordinates,
                    dimensions=self.dimensions,
                )

                if new_data is None:
                    copy_entry(self.dbx, self.path, (self.out_dir / subfolder))
                else:
                    upload_entry(self.dbx, self.path, new_data, (self.out_dir / subfolder))
            else:
                return
            move_entry(self.dbx, self.path, (self.backup_dir / subfolder))
        except Exception:
            log.exception(f"Exception occured, moving to Error subfolder: {self.name}")
            move_entry(self.dbx, self.path, self.error_dir)
        finally:
            end_time = dt.datetime.now()
            duration = end_time - start_time
            log.info(f"{self.name}, duration: {duration}")
            log.info("\n")


def _execute_transfer(dbx: dropbox.Dropbox, transfer_func: Callable, destination_folder: Path):
    try:
        transfer_func()
    except requests.exceptions.SSLError:
        log.info("Encountered SSL error during transfer. Trying again")
        transfer_func()
    except dropbox.exceptions.BadInputError:
        log.info(f"Making folder: {destination_folder}")
        dbx.files_create_folder(destination_folder.as_posix())
        transfer_func()


def move_entry(
        dbx: dropbox.Dropbox,
        from_path: Path,
        to_dir: Path,
):
    name = from_path.name
    transfer_func = partial(
        dbx.files_move,
        from_path=from_path.as_posix(),
        to_path=(to_dir / name).as_posix(),
        autorename=True
    )

    log.info(f"{name}: Moving to dest: {to_dir}")
    _execute_transfer(dbx, transfer_func, to_dir)


def copy_entry(
        dbx: dropbox.Dropbox,
        from_path: Path,
        to_dir: Path,
):
    name = from_path.name
    transfer_func = partial(
        dbx.files_copy,
        from_path=from_path.as_posix(),
        to_path=(to_dir / name).as_posix(),
        autorename=True
    )

    log.info(f"{name}: Copying to dest: {to_dir}")
    _execute_transfer(dbx, transfer_func, to_dir)


def upload_entry(
        dbx: dropbox.Dropbox,
        from_path: Path,
        new_data: bytes,
        to_dir: Path,
):
    name = from_path.with_suffix(".jpg").name
    transfer_func = partial(
        dbx.files_upload,
        f=new_data,
        path=(to_dir / name).as_posix(),
        autorename=True
    )

    log.info(f"{name}: Uploading to dest: {to_dir}")
    _execute_transfer(dbx, transfer_func, to_dir)


def download_entry(dbx, path_str: str):
    try:
        return dbx.files_download(path_str)
    except requests.exceptions.SSLError:
        log.info("Encountered SSL error during transfer. Trying again")
        return dbx.files_download(path_str)


def parse_date(
    time_taken: dt.datetime,
    client_modified: dt.datetime,
    coordinates: dropbox.files.GpsCoordinates,
    default_tz: str
) -> dt.datetime:
    naive_date = time_taken if time_taken is not None else client_modified
    utc_date = naive_date.replace(tzinfo=dt.timezone.utc)
    if coordinates is not None:
        img_tz = TimezoneFinder().timezone_at(
            lat=coordinates.latitude,
            lng=coordinates.longitude
        )
        if img_tz:
            local_date = utc_date.astimezone(tz=pytz.timezone(img_tz))
            return local_date
    local_date = utc_date.astimezone(tz=pytz.timezone(default_tz))
    return local_date
