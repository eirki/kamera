#! /usr/bin/env python3.6
# coding: utf-8
import datetime as dt
import os
import shutil
import typing as t
from pathlib import Path
from types import SimpleNamespace

import dropbox


class MockDropbox:
    metadatas: t.Dict[str, t.Optional[dropbox.files.PhotoMetadata]] = {}

    def __init__(
        self,
        *args,
        in_file: Path = None,
        metadata: t.Optional[dropbox.files.PhotoMetadata] = None,
        **kwargs
    ):
        if in_file is not None:
            self.metadatas[in_file.as_posix()] = metadata
            self.metadata_cache = metadata

    def users_get_current_account(self):
        pass

    def files_list_folder(self, path: str, recursive: t.Optional[bool] = False):
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
        if not Path(path).parent.exists():
            raise dropbox.exceptions.BadInputError(request_id=1, message="message")
        with open(path, "wb") as file:
            file.write(f)
        self.metadatas[path] = self.metadata_cache

    def files_move(
        self, from_path: str, to_path: str, autorename: t.Optional[bool] = False
    ) -> None:
        if not Path(from_path).parent.exists() or not Path(to_path).parent.exists():
            raise dropbox.exceptions.BadInputError(request_id=1, message="message")
        shutil.move(from_path, Path(to_path).parent)
        self.metadatas[to_path] = self.metadatas[from_path]

    def files_copy(
        self, from_path: str, to_path: str, autorename: t.Optional[bool] = False
    ) -> None:
        if not Path(from_path).parent.exists() or not Path(to_path).parent.exists():
            raise dropbox.exceptions.BadInputError(request_id=1, message="message")
        shutil.copy(from_path, to_path)
        self.metadatas[to_path] = self.metadatas[from_path]

    def files_create_folder(self, path, autorename=False) -> None:
        os.makedirs(path)

    def files_get_metadata(self, path: str, include_media_info=False):
        try:
            metadata = self.metadatas[path]
        except KeyError:
            raise dropbox.exceptions.ApiError(
                "request_id", "error", "user_message_text", "user_message_locale"
            )
        if include_media_info:
            if metadata is None:
                metadata = dropbox.files.PhotoMetadata(
                    dimensions=None, location=None, time_taken=None
                )
            media_info = dropbox.files.MediaInfo.metadata(metadata)
        else:
            media_info = None

        mock_entry = dropbox.files.FileMetadata(
            name=Path(path).name,
            path_display=path,
            path_lower=path.lower(),
            media_info=media_info,
        )
        return mock_entry

    def files_delete(self, path):
        os.remove(path)
