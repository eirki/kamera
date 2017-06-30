#!  /usr/bin/env python3
# coding: utf-8

import sys
from os import path
from functools import partial
import os
from pprint import pprint
import traceback

import dropbox

import config
import image_processing


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


def execute_transfer(dbx, out_dir, func, data, relative_dest):
    absolute_dest = "/".join([out_dir, relative_dest])

    if func == dbx.files_upload:
        transfer_func = partial(func, f=data, path=absolute_dest)
    elif func in (dbx.files_copy, dbx.files_move):
        transfer_func = partial(func, from_path=data, to_path=absolute_dest)

    try:
        print(f"Uploading/copying to dest: {absolute_dest}")
        transfer_func()
    except dropbox.exceptions.BadInputError:
        print(f"Making folder: {absolute_dest}")
        dbx.files_create_folder(absolute_dest)
        transfer_func()
    except dropbox.exceptions.ApiError as Exception:
            if (isinstance(Exception.error, dropbox.files.RelocationError) and
               isinstance(Exception.error.get_to().get_conflict(), dropbox.files.WriteConflictError)):
                print(f"Skipping copy, file already present: {absolute_dest}")

            elif (isinstance(Exception.error, dropbox.files.UploadError) and
                  isinstance(Exception.error.get_path().reason.get_conflict(), dropbox.files.WriteConflictError)):
                print(f"Skipping move, file already present: {absolute_dest}")
            else:
                raise


def get_backup_info(dbx, entry, db_metadata):
    date = image_processing.parse_date(entry, db_metadata)
    relative_dest = "/".join([str(date.year), folder_names[date.month], entry.name])
    backup_info = {"func": dbx.files_move, "data": entry.path_lower, "relative_dest": relative_dest}
    return backup_info


def process_non_image(dbx, entry, db_metadata):
    date = image_processing.parse_date(entry, db_metadata)
    if entry.name.lower().endswith(".mp4"):
        relative_dest = "/".join(["Video", str(date.year), entry.name])
    elif entry.name.lower().endswith(".gif"):
        relative_dest = "/".join([str(date.year), folder_names[date.month], entry.name])
    transfer_info = {"func": dbx.files_copy, "data": entry.path_lower, "relative_dest": relative_dest}
    return transfer_info


def process_image(dbx, entry, db_metadata):
    filedata, response = dbx.files_download(entry.path_lower)
    new_data, date = image_processing.main(entry, response.raw.data, db_metadata)
    filename, ext = os.path.splitext(entry.name)
    relative_dest = "/".join([str(date.year), folder_names[date.month], filename + ".jpg"])

    if new_data:
        transfer_info = {"func": dbx.files_upload, "data": new_data, "relative_dest": relative_dest}
    else:
        transfer_info = {"func": dbx.files_copy, "data": entry.path_lower, "relative_dest": relative_dest}
    return transfer_info


def main(in_dir=config.uploads_db_folder, out_dir=config.kamera_db_folder, backup_dir=config.backup_db_folder):
    dbx = dropbox.Dropbox(config.DBX_TOKEN)
    dbx.users_get_current_account()

    entries = db_list_new_media(dbx, in_dir)

    for entry in entries:
        try:
            print(f"Processing: {entry.name}. {entry}")
            db_metadata = entry.media_info.get_metadata() if entry.media_info else None

            if entry.name.lower().endswith((".mp4", ".gif")):
                transfer_info = process_non_image(dbx, entry, db_metadata)
            else:
                transfer_info = process_image(dbx, entry, db_metadata)
            execute_transfer(dbx, out_dir, **transfer_info)

            print(f"Moving to bakcup: {entry.name}")
            backup_info = get_backup_info(dbx, entry, db_metadata)
            execute_transfer(dbx, out_dir=backup_dir, **backup_info)
            print()
        except Exception as exc:
            print(traceback.format_exc().decode(sys.getfilesystemencoding()))


if __name__ == "__main__":
    main()
