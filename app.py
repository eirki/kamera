#!  /usr/bin/env python3
# coding: utf-8

import sys
from os import path
from functools import partial
import os

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


def db_make_cursor(dir):
    dbx = dropbox.Dropbox(config.DBX_TOKEN)
    dbx.users_get_current_account()
    result = dbx.files_list_folder(dir, include_media_info=True)
    with open(path.join(config.home, "cursor"), "w") as txt:
        txt.write(result.cursor)


def db_get_new_media(dbx, dir):
    has_more = True
    with open(path.join(config.home, "cursor")) as txt:
        cursor = txt.read()

    while has_more:
        result = dbx.files_list_folder_continue(cursor)
        print(result)
        for entry in result.entries:
            if (entry.path_lower.endswith(media_extensions) and
                    isinstance(entry, dropbox.files.FileMetadata)):
                yield entry

        # Update cursor
        cursor = result.cursor

        # Repeat only if there's more to do
        has_more = result.has_more

    with open(path.join(config.home, "cursor"), "w") as txt:
        txt.write(cursor)


def execute_upload_copy(move_func, dest, dbx):
    try:
        dest = move_func.keywords["path"]
    except KeyError:
        dest = move_func.keywords["to_path"]

    try:
        print(f"Uploading/copying to dest: {dest}")
        move_func()
    except dropbox.exceptions.BadInputError:
        print(f"Making folder: {dest}")
        dbx.files_create_folder(dest)
        move_func()


def process_entry(entry, dbx):
    print(f"Processing: {entry.name}")
    if entry.name.lower().endswith((".mp4", ".gif")):
        if entry.name.lower().endswith(".mp4"):
            dest = "/".join([config.kamera_db_folder, "Video", entry.name])
        elif entry.name.lower().endswith(".gif"):
            date = image_processing.parse_date(entry)
            dest = "/".join([config.kamera_db_folder, str(date.year), folder_names[date.month], entry.name])
        move_func = partial(dbx.files_copy, from_path=entry.path_lower, to_path=dest)
        execute_upload_copy(move_func, dest, dbx)
        return

    db_metadata = entry.media_info.get_metadata() if entry.media_info else None
    filedata, response = dbx.files_download(entry.path_lower)
    new_data, date = image_processing.main(entry, db_metadata, response.raw.data)
    filename, ext = os.path.splitext(entry.name)
    dest = "/".join([config.kamera_db_folder, str(date.year), folder_names[date.month], filename + ".jpg"])

    if new_data:
        move_func = partial(dbx.files_upload, f=new_data, path=dest)
    else:
        move_func = partial(dbx.files_copy, from_path=entry.path_lower, to_path=dest)
    execute_upload_copy(move_func, dest, dbx)


def main():
    dbx = dropbox.Dropbox(config.DBX_TOKEN)
    dbx.users_get_current_account()
    for entry in db_get_new_media(dbx, dir="/Camera Uploads"):
        process_entry(entry, dbx)


if __name__ == "__main__":
    print(sys.argv)
    if len(sys.argv) == 1:
        main()
    elif sys.argv[1] == "cursor":
        db_make_cursor(dir="/Camera Uploads")
