#! /usr/bin/env python3.6
# coding: utf-8

from functools import partial
import os
from pprint import pprint
import traceback
import datetime as dt
import pytz

from timezonefinderL import TimezoneFinder
import dropbox

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


media_extensions = (".jpg", ".jpeg", ".png", ".mp4", ".gif")


def db_list_new_media(dbx, dir_path):
    result = dbx.files_list_folder(dir_path, include_media_info=True)

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


def parse_date(entry, location=None):
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


def execute_transfer(dbx, transfer_func, destination):
    try:
        transfer_func()
    except dropbox.exceptions.BadInputError:
        print(f"Making folder: {destination}")
        dbx.files_create_folder(destination)
        transfer_func()
    except dropbox.exceptions.ApiError as Exception:
            if (isinstance(Exception.error, dropbox.files.RelocationError) and
               isinstance(Exception.error.get_to().get_conflict(), dropbox.files.WriteConflictError)):
                print(f"Skipping copy, file already present: {destination}")

            elif (isinstance(Exception.error, dropbox.files.UploadError) and
                  isinstance(Exception.error.get_path().reason.get_conflict(), dropbox.files.WriteConflictError)):
                print(f"Skipping move, file already present: {destination}")
            else:
                raise


def move_entry(dbx, path_lower, out_dir, date=None, subfolder=None):
    path, name = os.path.split(path_lower)
    if date is not None:
        destination = "/".join([out_dir, str(date.year), folder_names[date.month], name])
    elif subfolder is not None:
        destination = "/".join([out_dir, subfolder, name])

    transfer_func = partial(dbx.files_move, from_path=path_lower, to_path=destination)

    print(f"{name}: Moving to dest: {destination}")
    execute_transfer(dbx, transfer_func, destination)


def copy_entry(dbx, path_lower, out_dir, date):
    path, name = os.path.split(path_lower)
    if name.lower().endswith(".mp4"):
        destination = "/".join([out_dir, "Video", str(date.year), name])
    else:
        destination = "/".join([out_dir, str(date.year), folder_names[date.month], name])

    transfer_func = partial(dbx.files_copy, from_path=path_lower, to_path=destination)

    print(f"{name}: Copying to dest: {destination}")
    execute_transfer(dbx, transfer_func, destination)


def upload_entry(dbx, path_lower, new_data, out_dir, date):
    path, old_name = os.path.split(path_lower)
    filename, ext = os.path.splitext(old_name)
    new_name = filename + ".jpg"
    destination = "/".join([out_dir, str(date.year), folder_names[date.month], new_name])

    transfer_func = partial(dbx.files_upload, f=new_data, path=destination)

    print(f"{new_name}: Uploading to dest: {destination}")
    execute_transfer(dbx, transfer_func, destination)


def process_entry(dbx, entry, out_dir, backup_dir, error_dir):
    print(f"{entry.name}: Processing")
    print(entry)
    try:
        root, filetype = os.path.splitext(entry.name)
        if filetype in (".mp4", ".gif"):
            date = parse_date(entry)
            copy_entry(dbx, entry.path_lower, out_dir, date)

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

            orig_data, response = dbx.files_download(entry.path_lower)
            new_data, exif_date = image_processing.main(
                data=response.raw.data,
                name=entry.name,
                date=date,
                filetype=filetype,
                location=location,
                dimensions=dimensions,
            )
            date = exif_date if exif_date is not None else date
            if new_data is None:
                copy_entry(dbx, entry.path_lower, out_dir, date)
            else:
                upload_entry(dbx, entry.path_lower, new_data, out_dir, date)

        move_entry(dbx, entry.path_lower, backup_dir, date=date)
    except Exception as exc:
        print(f"Exception occured, moving to Error subfolder: {entry.name}")
        traceback.print_exc()
        move_entry(dbx, entry.path_lower, error_dir, subfolder="Errors")
    finally:
        print()


def main(in_dir=config.uploads_db_folder,
         out_dir=config.kamera_db_folder,
         backup_dir=config.backup_db_folder):
    dbx = dropbox.Dropbox(config.DBX_TOKEN)
    dbx.users_get_current_account()

    recognition.load_encodings()

    entries = db_list_new_media(dbx, in_dir)

    for entry in entries:
        process_entry(
            dbx=dbx,
            entry=entry,
            out_dir=out_dir,
            backup_dir=backup_dir,
            error_dir=in_dir
        )


if __name__ == "__main__":
    main()
