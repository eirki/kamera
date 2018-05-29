#! /usr/bin/env python3.6
# coding: utf-8
from kamera.logger import log

from types import SimpleNamespace
from collections import defaultdict
from pathlib import Path
import datetime as dt
import shutil

import pytest

from kamera import config

from typing import Optional


@pytest.fixture()
def load_settings():
    config.settings = {}
    config.tag_swaps = {}
    mock_dbx = MockDropbox()
    config.load_settings(mock_dbx)


@pytest.fixture()
def load_location_data():
    config.areas = []
    mock_dbx = MockDropbox()
    config.load_location_data(mock_dbx)


@pytest.fixture()
def load_recognition_data():
    config.people = defaultdict(list)
    mock_dbx = MockDropbox()
    config.load_recognition_data(mock_dbx)


@pytest.fixture(autouse=True)
def no_dbx(monkeypatch):
    monkeypatch.setattr('kamera.task.cloud', MockCloud())


@pytest.fixture()
def no_img_processing(monkeypatch):
    monkeypatch.setattr('kamera.task.image_processing.main', no_img_processing_mock)


def no_img_processing_mock(*args, **kwargs):
    new_data = None
    return new_data


@pytest.fixture()
def data_from_img_processing(monkeypatch):
    monkeypatch.setattr('kamera.task.image_processing.main', data_from_img_processing_mock)


def data_from_img_processing_mock(*args, **kwargs):
    new_data = b"new_file_content"
    return new_data


@pytest.fixture()
def error_img_processing(monkeypatch):
    monkeypatch.setattr('kamera.task.image_processing.main', error_img_processing_mock)


def error_img_processing_mock(*args, **kwargs):
    raise Exception("This is an excpetion from mock image processing")


class MockDropbox:
    def files_download(self, path: Path):
        with open(path, "rb") as file:
            data = file.read()
        filemetadata = None
        response = SimpleNamespace(raw=SimpleNamespace(data=data))
        return filemetadata, response

    def files_list_folder(self, path: str, recursive: bool):
        path_obj = Path(path)
        files = path_obj.rglob("*") if recursive else path_obj.iterdir()
        mock_entries = [SimpleNamespace(path_display=file) for file in files]
        mock_result = SimpleNamespace(entries=mock_entries)
        return mock_result

    def files_upload(self, f: bytes, path: str):
        with open(path, "wb") as file:
            file.write(f)

    def users_get_current_account(self):
        pass


class MockCloud:
    def __init__(self):
        self.dbx = MockDropbox()

    def move_entry(
            self,
            from_path: Path,
            out_dir: Path,
            date: Optional[dt.datetime] = None):
        log.info("move_entry")
        to_path = out_dir / from_path.name
        shutil.move(from_path.as_posix(), to_path.as_posix())

    def copy_entry(
            self,
            from_path: Path,
            out_dir: Path,
            date: dt.datetime):
        log.info("copy_entry")
        to_path = out_dir / from_path.name
        shutil.copy2(from_path.as_posix(), to_path.as_posix())

    def upload_entry(
            self,
            from_path: Path,
            new_data: bytes,
            out_dir: Path,
            date: dt.datetime):
        log.info("upload_entry")
        to_path = out_dir / from_path.name
        with open(to_path, "wb") as file:
            file.write(new_data)

    def download_entry(self, path_str: str):
        log.info("download_entry")
        entry = self.dbx.files_download(path_str)
        return entry
