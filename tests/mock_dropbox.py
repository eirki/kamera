#! /usr/bin/env python3.6
# coding: utf-8
from kamera.logger import log

from pathlib import Path
import datetime as dt
import typing as t
import dropbox
from types import SimpleNamespace


class MockDropbox:
    def __init__(*args, **kwargs):
        pass

    def users_get_current_account(self):
        pass

    def files_list_folder(
        self,
        path: str,
        recursive: t.Optional[bool] = False,
        include_media_info: t.Optional[bool] = False,
    ):
        path_obj = Path(path)
        files = path_obj.rglob("*") if recursive else path_obj.iterdir()
        mock_entries = [
            dropbox.files.FileMetadata(
                name=file.name,
                path_display=file.as_posix(),
                path_lower=file.as_posix().lower(),
                client_modified=dt.datetime(2000, 1, 1),
            )
            for file in files
        ]
        mock_result = SimpleNamespace(entries=mock_entries, has_more=False)
        return mock_result

    def files_list_folder_continue(self, cursor) -> None:
        pass

    def files_download(self, path: Path):
        with open(path, "rb") as file:
            data = file.read()
        filemetadata = None
        response = SimpleNamespace(raw=SimpleNamespace(data=data))
        return filemetadata, response

    def files_upload(self, f: bytes, path: str, autorename: t.Optional[bool] = False):
        with open(path, "wb") as file:
            file.write(f)
