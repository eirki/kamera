#!  /usr/bin/env python3
# coding: utf-8

import sys
from os import path
from functools import partial
import os
from pprint import pprint

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


def db_make_cursor(in_dir):
    dbx = dropbox.Dropbox(config.DBX_TOKEN)
    dbx.users_get_current_account()
    result = dbx.files_list_folder(dir, include_media_info=True)
    with open(path.join(config.home, "cursor"), "w") as txt:
        txt.write(result.cursor)


def db_list_media_in_dir(dbx, in_dir):
    result = dbx.files_list_folder(in_dir, include_media_info=True)
    for entry in result.entries:
        if (entry.path_lower.endswith(media_extensions) and
                isinstance(entry, dropbox.files.FileMetadata)):
            yield entry


def db_list_new_media(dbx):
    has_more = True
    with open(path.join(config.home, "cursor")) as txt:
        cursor = txt.read()

    while has_more:
        result = dbx.files_list_folder_continue(cursor)
        pprint(result)
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


def execute_transfer(dbx, out_dir, func, data, relative_dest):
    absolute_dest = "/".join([out_dir, relative_dest])

    if func == dbx.files_upload:
        transfer_func = partial(dbx.files_upload, f=data, path=absolute_dest)
    elif func == dbx.files_copy:
        transfer_func = partial(dbx.files_copy, from_path=data, to_path=absolute_dest)

    try:
        print(f"Uploading/copying to dest: {absolute_dest}")
        transfer_func()
    except dropbox.exceptions.BadInputError:
        print(f"Making folder: {absolute_dest}")
        dbx.files_create_folder(absolute_dest)
        transfer_func()


def process_non_image(dbx, entry):
    date = image_processing.parse_date(entry)
    if entry.name.lower().endswith(".mp4"):
        relative_dest = "/".join(["Video", str(date.year), entry.name])
    elif entry.name.lower().endswith(".gif"):
        relative_dest = "/".join([str(date.year), folder_names[date.month], entry.name])
    transfer_info = (dbx.files_copy, entry.path_lower, relative_dest)
    return transfer_info


def process_image(dbx, entry):
    filedata, response = dbx.files_download(entry.path_lower)
    new_data, date = image_processing.main(entry, response.raw.data)
    filename, ext = os.path.splitext(entry.name)
    relative_dest = "/".join([str(date.year), folder_names[date.month], filename + ".jpg"])

    if new_data:
        transfer_info = (dbx.files_upload, new_data, relative_dest)
    else:
        transfer_info = (dbx.files_copy, entry.path_lower, relative_dest)
    return transfer_info


def main(use_cursor=True, out_dir=config.kamera_db_folder, in_dir=None):
    dbx = dropbox.Dropbox(config.DBX_TOKEN)
    dbx.users_get_current_account()
    if use_cursor:
        entries = db_list_new_media(dbx)
    else:
        entries = db_list_media_in_dir(dbx, in_dir)
    for entry in entries:
        print(f"Processing: {entry.name}")
        if entry.name.lower().endswith((".mp4", ".gif")):
            transfer_info = process_non_image(dbx, entry)
        else:
            transfer_info = process_image(dbx, entry)
        execute_transfer(dbx, out_dir, *transfer_info)


if __name__ == "__main__":
    print(sys.argv)
    if len(sys.argv) == 1:
        main()
    elif sys.argv[1] == "cursor":
        db_make_cursor(dir="/Camera Uploads")
    elif sys.argv[1] == "process_dir":
        main(in_dir=sys.argv[2], out_dir=sys.argv[3], use_cursor=False)
