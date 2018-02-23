#! /usr/bin/env python3.6
# coding: utf-8
from functools import partial
from pathlib import Path
import traceback
import datetime as dt
import time
import sys

import pytz
from timezonefinderL import TimezoneFinder
import dropbox

from typing import Callable, Optional

import config
import image_processing
import recognition
import database_manager

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

def dbx_list_entries() -> dropbox.files.Metadata:
    path = config.uploads_db_folder
    result = dbx.files_list_folder(path.as_posix())
    while True:
        print(f"Entries in upload folder: {len(result.entries)}")
        print(result)
        for entry in result.entries:
            # Ignore deleted files, folders
            if (entry.path_lower.endswith(media_extensions) and
                    isinstance(entry, dropbox.files.FileMetadata)):
                yield entry

        # Repeat only if there's more to do
        if result.has_more:
            result = dbx.files_list_folder_continue(result.cursor)
        else:
            break


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


def execute_transfer(transfer_func: Callable, destination: Path):
    try:
        transfer_func()
    except dropbox.exceptions.BadInputError:
        print(f"Making folder: {destination}")
        dbx.files_create_folder(destination.as_posix())
        transfer_func()
    except dropbox.exceptions.ApiError as Exception:
            if (
                isinstance(Exception.error, dropbox.files.RelocationError) and
                isinstance(
                    Exception.error.get_to().get_conflict(),
                    dropbox.files.WriteConflictError)
            ):
                print(f"Skipping copy, file already present: {destination}")

            elif (
                isinstance(Exception.error, dropbox.files.UploadError) and
                isinstance(
                    Exception.error.get_path().reason.get_conflict(),
                    dropbox.files.WriteConflictError)
            ):
                print(f"Skipping move, file already present: {destination}")
            else:
                raise


def move_entry(
        from_path: Path,
        out_dir: Path,
        date: dt.datetime = None,
        subfolder: str = None):
    if date is not None:
        destination = out_dir / str(date.year) / folder_names[date.month] / from_path.name
    elif subfolder is not None:
        destination = out_dir / subfolder / from_path.name

    transfer_func = partial(
        dbx.files_move,
        from_path=from_path.as_posix(),
        to_path=destination.as_posix()
    )

    print(f"{from_path.stem}: Moving to dest: {destination}")
    execute_transfer(transfer_func, destination)


def copy_entry(
        from_path: Path,
        out_dir: Path,
        date: dt.datetime):
    destination = out_dir / str(date.year) / folder_names[date.month] / from_path.name

    transfer_func = partial(
        dbx.files_copy,
        from_path=from_path.as_posix(),
        to_path=destination.as_posix()
    )

    print(f"{from_path.stem}: Copying to dest: {destination}")
    execute_transfer(transfer_func, destination)


def upload_entry(
        from_path: Path,
        new_data: bytes,
        out_dir: Path,
        date: dt.datetime):
    new_name = from_path.with_suffix(".jpg").name
    destination = out_dir / str(date.year) / folder_names[date.month] / new_name

    transfer_func = partial(dbx.files_upload, f=new_data, path=destination.as_posix())

    print(f"{destination.stem}: Uploading to dest: {destination}")
    execute_transfer(transfer_func, destination)


def process_entry(
        entry,
        out_dir: Path,
        backup_dir: Path,
        error_dir: Path):
    print(f"{entry.name}: Processing")
    start_time = dt.datetime.now()
    print(entry)
    try:
        filepath = Path(entry.path_display)
        if filepath.suffix.lower() in (".mp4", ".gif"):
            date = parse_date(entry)
            copy_entry(filepath, out_dir, date)

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

            orig_data, response = dbx.files_download(filepath.as_posix())
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
                copy_entry(filepath, out_dir, date)
            else:
                upload_entry(filepath, new_data, out_dir, date)

        move_entry(filepath, out_dir=backup_dir, date=date)
    except Exception as exc:
        print(f"Exception occured, moving to Error subfolder: {filepath.name}")
        traceback.print_exc()
        move_entry(filepath, out_dir=error_dir, subfolder="Errors")
    finally:
        end_time = dt.datetime.now()
        duration = end_time - start_time
        print(f"{entry.name}, duration: {duration}")
        print()


def main():
    recognition.load_encodings(home_path=config.home)
    dbx.users_get_current_account()
    db_connection = database_manager.connect()
    cursor = db_connection.cursor()
    try:
        while True:
            media_list = database_manager.get_media_list(cursor)
            if not media_list:
                time.sleep(5)
                continue
            entries = dbx_list_entries()
            for entry in entries:
                try:
                    process_entry(
                        entry=entry,
                        out_dir=config.kamera_db_folder,
                        backup_dir=config.backup_db_folder,
                        error_dir=config.errors_db_folder
                    )
                finally:
                    database_manager.remove_entry_from_processing_list(cursor, entry)
                    db_connection.commit()
    except KeyboardInterrupt:
        sys.exit()
    finally:
        db_connection.close()


if __name__ == '__main__':
    main()
