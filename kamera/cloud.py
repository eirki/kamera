#! /usr/bin/env python3.6
# coding: utf-8
from kamera.logger import log

from functools import partial
import datetime as dt

import dropbox

from kamera import config
from kamera.mediatypes import KameraEntry

from typing import Callable
from pathlib import Path


media_extensions = (".jpg", ".jpeg", ".png", ".mp4", ".gif")

folder_names = {
    1: "01 (Januar)",
    2: "02 (Februar)",
    3: "03 (Mars)",
    4: "04 (April)",
    5: "05 (Mai)",
    6: "06 (Juni)",
    7: "07 (Juli)",
    8: "08 (August)",
    9: "09 (September)",
    10: "10 (Oktober)",
    11: "11 (November)",
    12: "12 (Desember)",
}

dbx = dropbox.Dropbox(config.DBX_TOKEN)


def list_entries() -> KameraEntry:
    path = config.uploads_db_folder
    result = dbx.files_list_folder(
        path=path.as_posix(),
        include_media_info=True
    )
    while True:
        log.info(f"Entries in upload folder: {len(result.entries)}")
        log.info(result)
        for entry in result.entries:
            # Ignore deleted files, folders
            if not (entry.path_lower.endswith(media_extensions) and
                    isinstance(entry, dropbox.files.FileMetadata)):
                continue

            dbx_photo_metadata = entry.media_info.get_metadata() if entry.media_info else None
            kamera_entry = KameraEntry.from_dbx_entry(entry, dbx_photo_metadata)
            yield kamera_entry

        # Repeat only if there's more to do
        if result.has_more:
            result = dbx.files_list_folder_continue(result.cursor)
        else:
            break


def execute_transfer(transfer_func: Callable, destination: Path):
    try:
        transfer_func()
    except dropbox.exceptions.BadInputError:
        log.info(f"Making folder: {destination}")
        dbx.files_create_folder(destination.as_posix())
        transfer_func()


def move_entry(
        from_path: Path,
        out_dir: Path,
        date: dt.datetime = None):
    if date is not None:
        destination = out_dir / str(date.year) / folder_names[date.month] / from_path.name
    else:
        destination = out_dir / from_path.name

    transfer_func = partial(
        dbx.files_move,
        from_path=from_path.as_posix(),
        to_path=destination.as_posix(),
        autorename=True
    )

    log.info(f"{from_path.stem}: Moving to dest: {destination}")
    execute_transfer(transfer_func, destination)


def copy_entry(
        from_path: Path,
        out_dir: Path,
        date: dt.datetime):
    destination = out_dir / str(date.year) / folder_names[date.month] / from_path.name

    transfer_func = partial(
        dbx.files_copy,
        from_path=from_path.as_posix(),
        to_path=destination.as_posix(),
        autorename=True
    )

    log.info(f"{from_path.stem}: Copying to dest: {destination}")
    execute_transfer(transfer_func, destination)


def upload_entry(
        from_path: Path,
        new_data: bytes,
        out_dir: Path,
        date: dt.datetime):
    new_name = from_path.with_suffix(".jpg").name
    destination = out_dir / str(date.year) / folder_names[date.month] / new_name

    transfer_func = partial(
        dbx.files_upload,
        f=new_data,
        path=destination.as_posix(),
        autorename=True
    )

    log.info(f"{destination.stem}: Uploading to dest: {destination}")
    execute_transfer(transfer_func, destination)
