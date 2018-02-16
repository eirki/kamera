#! /usr/bin/env python3.6
# coding: utf-8

from functools import partial
from pathlib import Path
from pprint import pprint
import traceback
import datetime as dt
import pytz
import asyncio

from timezonefinderL import TimezoneFinder
import dropbox

from typing import Callable, Optional

import config
import image_processing
import recognition

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
times = []

media_extensions = (".jpg", ".jpeg", ".png", ".mp4", ".gif")

dbx = dropbox.Dropbox(config.DBX_TOKEN)


def db_list_new_media(dir_path: Path):
    result = dbx.files_list_folder(dir_path.as_posix(), include_media_info=True)

    while True:
        pprint(result)
        print()
        for entry in result.entries:
            if (entry.path_lower.endswith(media_extensions) and
                    isinstance(entry, dropbox.files.FileMetadata)):
                yield entry

        # Update cursor
        cursor = result.cursor

        # Repeat only if there's more to do
        if result.has_more:
            result = dbx.files_list_folder_continue(cursor)
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


async def execute_transfer(transfer_func: Callable, destination: Path, loop):
    try:
        await loop.run_in_executor(None, transfer_func)
    except dropbox.exceptions.BadInputError:
        print(f"Making folder: {destination}")
        dbx.files_create_folder(destination.as_posix())
        await loop.run_in_executor(None, transfer_func)
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


async def move_entry(
        from_path: Path,
        out_dir: Path,
        date: dt.datetime = None,
        subfolder: str = None,
        loop=None):
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
    await execute_transfer(transfer_func, destination, loop)


async def copy_entry(
        from_path: Path,
        out_dir: Path,
        date: dt.datetime,
        loop):
    destination = out_dir / str(date.year) / folder_names[date.month] / from_path.name

    transfer_func = partial(
        dbx.files_copy,
        from_path=from_path.as_posix(),
        to_path=destination.as_posix()
    )

    print(f"{from_path.stem}: Copying to dest: {destination}")
    await execute_transfer(transfer_func, destination, loop)


async def upload_entry(
        from_path: Path,
        new_data: bytes,
        out_dir: Path,
        date: dt.datetime,
        loop):
    new_name = from_path.with_suffix(".jpg").name
    destination = out_dir / str(date.year) / folder_names[date.month] / new_name

    transfer_func = partial(dbx.files_upload, f=new_data, path=destination.as_posix())

    print(f"{destination.stem}: Uploading to dest: {destination}")
    await execute_transfer(transfer_func, destination, loop)


async def process_entry(
        entry,
        out_dir: Path,
        backup_dir: Path,
        error_dir: Path,
        loop):
    start_time = dt.datetime.now()
    print(f"{start_time} | {entry.name}: Processing")
    print(entry)
    try:
        filepath = Path(entry.path_display)
        if filepath.suffix.lower() in (".mp4", ".gif"):
            date = parse_date(entry)
            await copy_entry(filepath, out_dir, date, loop=loop)

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

            orig_data, response = await loop.run_in_executor(
                None, dbx.files_download, filepath.as_posix()
            )

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
                await copy_entry(filepath, out_dir, date, loop=loop)
            else:
                await upload_entry(filepath, new_data, out_dir, date, loop=loop)

        await move_entry(filepath, out_dir=backup_dir, date=date, loop=loop)
    except Exception as exc:
        print(f"Exception occured, moving to Error subfolder: {filepath.name}")
        traceback.print_exc()
        await move_entry(filepath, out_dir=error_dir, subfolder="Errors", loop=loop)
    finally:
        end_time = dt.datetime.now()
        duration = end_time - start_time
        print(f"{end_time} | {entry.name}, duration: {duration}")
        times.append(duration.seconds)
        print()


def main(
        in_dir: Path = config.uploads_db_folder,
        out_dir: Path = config.kamera_db_folder,
        backup_dir: Path = config.backup_db_folder):
    start_time = dt.datetime.now()

    dbx.users_get_current_account()
    recognition.load_encodings(home_path=config.home)

    entries = db_list_new_media(in_dir)

    loop = asyncio.get_event_loop()
    tasks = [
        loop.create_task(
            process_entry(entry=entry,
                          out_dir=out_dir,
                          backup_dir=backup_dir,
                          error_dir=in_dir,
                          loop=loop)
        )
        for entry in entries
     ]

    loop.run_until_complete(asyncio.wait(tasks))
    loop.close()
    print(sorted(times))
    end_time = dt.datetime.now()
    duration = end_time - start_time
    print(f"{end_time} | Total duration: {duration}")


if __name__ == "__main__":
    main()
