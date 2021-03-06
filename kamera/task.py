#! /usr/bin/env python3
# coding: utf-8
import datetime as dt
import typing as t
from functools import partial
from io import BytesIO
from pathlib import Path

import dropbox
import imagehash
import pytz
import redis
import requests
from PIL import Image
from resizeimage import resizeimage
from timezonefinderL import TimezoneFinder

from kamera import config, image_processing
from kamera.logger import log

seconds_in_fortnight = int(dt.timedelta(weeks=1).total_seconds())


class FoundBetterDuplicateException(Exception):
    pass


class Task:
    dbx_cache: t.Dict[str, dropbox.Dropbox] = {}
    settings_cache: t.Dict[str, config.Settings] = {}
    redis_client: redis.Redis = None

    def __init__(
        self,
        account_id: str,
        entry: dropbox.files.FileMetadata,
        review_dir: Path,
        backup_dir: Path,
        error_dir: Path,
    ) -> None:
        self.account_id: str = account_id
        self.path: Path = Path(entry.path_display)
        self.name: str = self.path.name
        self.client_modified: dt.datetime = entry.client_modified
        self.review_dir: Path = review_dir
        self.backup_dir: Path = backup_dir
        self.error_dir: Path = error_dir

    def __repr__(self):
        return repr(self.name)

    @classmethod
    def connect_redis(cls) -> None:
        if cls.redis_client is None:
            cls.redis_client = redis.Redis(
                host=config.redis_host,
                port=config.redis_port,
                password=config.redis_password,
            )
        return cls.redis_client

    @classmethod
    def load_dbx_from_cache(
        cls, account_id: str, redis_client: redis.Redis
    ) -> dropbox.Dropbox:
        try:
            dbx = cls.dbx_cache[account_id]
        except KeyError:
            dbx = dropbox.Dropbox(config.get_dbx_token(redis_client, account_id))
            cls.dbx_cache[account_id] = dbx
        return dbx

    @classmethod
    def load_settings_from_cache(
        cls, account_id: str, dbx: dropbox.Dropbox
    ) -> config.Settings:
        try:
            settings = cls.settings_cache[account_id]
            log.debug("Settings loaded from cache")
        except KeyError:
            settings = config.Settings(dbx)
            cls.settings_cache[account_id] = settings
            log.debug("Settings loaded from dbx")
        return settings

    def main(self):
        try:
            redis_client = Task.connect_redis()
            dbx = Task.load_dbx_from_cache(self.account_id, redis_client)
            settings = Task.load_settings_from_cache(self.account_id, dbx)
        except Exception:
            log.exception("Exception occured during task setup")
            return
        self.process_entry(redis_client, dbx, settings)

    def process_entry(
        self, redis_client: redis.Redis, dbx: dropbox.Dropbox, settings: config.Settings
    ) -> None:
        start_time = dt.datetime.now()
        log.info(f"{self.name}: Processing")

        try:
            time_taken, dimensions, coordinates = parse_metdata(self.path, dbx)
            date = parse_date(
                time_taken, self.client_modified, coordinates, settings.default_tz
            )
            out_name = get_out_name(self.path.stem, self.path.suffix, date)
            subfolder = Path(str(date.year), settings.folder_names[date.month])
            review_path = self.review_dir / subfolder / out_name
            backup_path = self.backup_dir / subfolder / self.name

            if self.path.suffix.lower() in config.video_extensions:
                copy_entry(dbx, self.path, review_path)
                move_entry(dbx, self.path, backup_path)
                return

            elif self.path.suffix.lower() not in config.image_extensions:
                return

            _, response = download_entry(dbx, self.path.as_posix())
            in_data = response.raw.data
            new_data = image_processing.main(
                data=in_data,
                filepath=self.path,
                date=date,
                settings=settings,
                coordinates=coordinates,
                dimensions=dimensions,
            )

            img_hash = get_hash(data=new_data if new_data is not None else in_data)
            handle_duplication(
                account_id_and_img_hash=f"user:{self.account_id}, hash:{img_hash}",
                file_path=review_path,
                dbx=dbx,
                redis_client=redis_client,
                dimensions=dimensions,
            )

            if new_data is None:
                copy_entry(dbx, self.path, review_path)
            else:
                upload_entry(dbx, new_data, review_path)

            move_entry(dbx, self.path, backup_path)
        except FoundBetterDuplicateException:
            log.info(f"{self.name}: Found better duplicate, finishing")
            move_entry(dbx, self.path, backup_path)
        except Exception:
            log.exception(f"Exception occured, moving to Error subfolder: {self.name}")
            move_entry(dbx, self.path, (self.error_dir / self.name))
        finally:
            end_time = dt.datetime.now()
            duration = end_time - start_time
            log.info(f"{self.name}, duration: {duration}")
            log.info("\n")


def handle_duplication(
    account_id_and_img_hash: str,
    file_path: Path,
    dbx: dropbox.Dropbox,
    redis_client: redis.Redis,
    dimensions: dropbox.files.Dimensions,
) -> None:
    dup_file_path = redis_client.get(account_id_and_img_hash)
    # need to check for duplicate before storing the hash
    store_hash(account_id_and_img_hash, file_path, redis_client)
    if dup_file_path is None:
        return
    dup_file_path = dup_file_path.decode()

    try:
        dup_entry = dbx.files_get_metadata(dup_file_path, include_media_info=True)
    except dropbox.exceptions.ApiError:
        log.info("Duplicate hash found, but image not in dbx")
        delete_hash(account_id_and_img_hash, redis_client)
        return
    dup_metadata = dup_entry.media_info.get_metadata() if dup_entry.media_info else None
    try:
        duplicate_better = (
            dup_metadata.dimensions.height * dup_metadata.dimensions.width
        ) > (dimensions.height * dimensions.width)
    except AttributeError:
        duplicate_better = (
            dup_metadata is not None and dup_metadata.dimensions is not None
        ) and (dimensions is None)
    if duplicate_better:
        raise FoundBetterDuplicateException
    else:
        log.info(f"Found worse duplicate, deleting: {dup_entry.path_display}")
        delete_entry(dup_entry, dbx)
        delete_hash(account_id_and_img_hash, redis_client)


def get_hash(data: bytes) -> str:
    img = Image.open(BytesIO(data))
    if img.height > 500:
        small_img = resizeimage.resize_height(img, size=500)
    else:
        small_img = img
    img_hash = imagehash.whash(small_img)
    return img_hash


def store_hash(
    account_id_and_img_hash: str, file_path: Path, redis_client: redis.Redis
) -> None:
    redis_client.set(account_id_and_img_hash, file_path.as_posix())
    redis_client.expire(account_id_and_img_hash, seconds_in_fortnight)


def delete_hash(account_id_and_img_hash: str, redis_client: redis.Redis) -> None:
    redis_client.delete(account_id_and_img_hash)


def delete_entry(entry: dropbox.files.FileMetadata, dbx: dropbox.Dropbox) -> None:
    dbx.files_delete(entry.path_display)


def _execute_transfer(
    dbx: dropbox.Dropbox, transfer_func: t.Callable, destination_folder: Path
) -> None:
    try:
        transfer_func()
    except requests.exceptions.SSLError:
        log.info("Encountered SSL error during transfer. Trying again")
        transfer_func()
    except dropbox.exceptions.BadInputError:
        log.info(f"Making folder: {destination_folder}")
        dbx.files_create_folder(destination_folder.as_posix())
        transfer_func()


def move_entry(dbx: dropbox.Dropbox, from_path: Path, to_path: Path) -> None:
    transfer_func = partial(
        dbx.files_move,
        from_path=from_path.as_posix(),
        to_path=to_path.as_posix(),
        autorename=True,
    )
    log.info(f"{from_path.name}: Moving to dest: {to_path.as_posix()}")
    _execute_transfer(dbx, transfer_func, to_path.parent)


def copy_entry(dbx: dropbox.Dropbox, from_path: Path, to_path: Path) -> None:
    transfer_func = partial(
        dbx.files_copy,
        from_path=from_path.as_posix(),
        to_path=to_path.as_posix(),
        autorename=True,
    )
    log.info(f"{from_path.name}: Copying to dest: {to_path.as_posix()}")
    _execute_transfer(dbx, transfer_func, to_path.parent)


def upload_entry(dbx: dropbox.Dropbox, new_data: bytes, to_path: Path) -> None:
    transfer_func = partial(
        dbx.files_upload, f=new_data, path=to_path.as_posix(), autorename=True
    )
    log.info(f"{to_path.name}: Uploading to dest: {to_path.as_posix()}")
    _execute_transfer(dbx, transfer_func, to_path.parent)


def download_entry(dbx, path_str: str):
    try:
        return dbx.files_download(path_str)
    except requests.exceptions.SSLError:
        log.info("Encountered SSL error during transfer. Trying again")
        return dbx.files_download(path_str)


def parse_metdata(
    path: Path, dbx: dropbox.Dropbox
) -> t.Tuple[
    t.Optional[dt.datetime],
    t.Optional[dropbox.files.Dimensions],
    t.Optional[dropbox.files.GpsCoordinates],
]:
    metadata_obj = dbx.files_get_metadata(path=path.as_posix(), include_media_info=True)
    metadata = metadata_obj.media_info.get_metadata() if metadata_obj else None
    time_taken: t.Optional[dt.datetime] = None
    dimensions: t.Optional[dropbox.files.Dimensions] = None
    coordinates: t.Optional[dropbox.files.GpsCoordinates] = None
    if metadata is not None:
        time_taken = metadata.time_taken
        if metadata.dimensions is not None:
            dimensions = metadata.dimensions
        if metadata.location is not None:
            coordinates = metadata.location
    return time_taken, dimensions, coordinates


def parse_date(
    time_taken: t.Optional[dt.datetime],
    client_modified: dt.datetime,
    coordinates: t.Optional[dropbox.files.GpsCoordinates],
    default_tz: str,
) -> dt.datetime:
    naive_date = time_taken if time_taken is not None else client_modified
    utc_date = naive_date.replace(tzinfo=dt.timezone.utc)
    if coordinates is not None:
        img_tz = TimezoneFinder().timezone_at(
            lat=coordinates.latitude, lng=coordinates.longitude
        )
        if img_tz:
            local_date = utc_date.astimezone(tz=pytz.timezone(img_tz))
            return local_date
    local_date = utc_date.astimezone(tz=pytz.timezone(default_tz))
    return local_date


def get_out_name(stem: str, suffix: str, date: dt.datetime) -> str:
    date_format_in1 = date.strftime("_%Y%m%d_%H%M%S")
    date_format_in2 = date.strftime(" %Y-%m-%d %H_%M_%S")
    date_format_out = date.strftime("%Y-%m-%d %H.%M.%S")
    if date_format_in1 in stem:
        stem = stem.replace(date_format_in1, "")
    elif date_format_in2 in stem:
        stem = stem.replace(date_format_in2, "")
    out_name = date_format_out + " " + stem
    out_suffix = ".jpg" if suffix == ".png" else suffix
    return out_name + out_suffix
