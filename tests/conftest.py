#! /usr/bin/env python3.6
# coding: utf-8
from kamera.logger import log

from types import SimpleNamespace
from collections import defaultdict
from pathlib import Path
import datetime as dt
import shutil
import os

import pytest
import dropbox
import rq
import fakeredis

import app
from kamera import config
from kamera.task import Cloud

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


@pytest.fixture()
def no_img_processing(monkeypatch):
    def no_img_processing_mock(*args, **kwargs):
        new_data = None
        return new_data
    monkeypatch.setattr('kamera.task.image_processing.main', no_img_processing_mock)


@pytest.fixture()
def data_from_img_processing(monkeypatch):
    def data_from_img_processing_mock(*args, **kwargs):
        new_data = b"new_file_content"
        return new_data
    monkeypatch.setattr('kamera.task.image_processing.main', data_from_img_processing_mock)


@pytest.fixture()
def error_img_processing(monkeypatch):
    def error_img_processing_mock(*args, **kwargs):
        raise Exception("This is an excpetion from mock image processing")
    monkeypatch.setattr('kamera.task.image_processing.main', error_img_processing_mock)


class MockDropbox:
    def files_download(self, path: Path):
        with open(path, "rb") as file:
            data = file.read()
        filemetadata = None
        response = SimpleNamespace(raw=SimpleNamespace(data=data))
        return filemetadata, response

    def files_upload(self, f: bytes, path: str, autorename: Optional[bool]=False):
        if not Path(path).parent.exists():
            raise dropbox.exceptions.BadInputError(request_id=1, message="message")
        with open(path, "wb") as file:
            file.write(f)

    def files_move(self, from_path: str, to_path: str, autorename: Optional[bool]=False) -> None:
        if not Path(from_path).parent.exists() or not Path(to_path).parent.exists():
            raise dropbox.exceptions.BadInputError(request_id=1, message="message")
        shutil.move(from_path, Path(to_path).parent)

    def files_copy(self, from_path: str, to_path: str, autorename: Optional[bool]=False) -> None:
        if not Path(from_path).parent.exists() or not Path(to_path).parent.exists():
            raise dropbox.exceptions.BadInputError(request_id=1, message="message")
        shutil.copy(from_path, Path(to_path).parent)

    def files_create_folder(self, path, autorename=False) -> None:
        os.makedirs(path)

    def files_list_folder(self, path: str, recursive: bool):
        path_obj = Path(path)
        files = path_obj.rglob("*") if recursive else path_obj.iterdir()
        mock_entries = [SimpleNamespace(path_display=file) for file in files]
        mock_result = SimpleNamespace(entries=mock_entries)
        return mock_result

    def files_list_folder_continue(self, cursor) -> None:
        pass


class MockCloud(Cloud):
    def __init__(self):
        self.dbx = MockDropbox()


@pytest.fixture()
def mock_cloud():
    return MockCloud()

class MockRedisLock:
    def __init__(self, *args, **kwargs):
        pass

    def acquire(self, *args, **kwargs):
        return True

    def release(self):
        pass

    def reset_all(self):
        pass


def return_mocked_redis_lock_module():
    return MockRedisLock


@pytest.fixture(autouse=True)
def use_fake_redis_and_dbx(monkeypatch) -> None:
    conn = fakeredis.FakeStrictRedis()
    conn.flushall()
    monkeypatch.setattr('app.conn', conn)
    queue = rq.Queue(connection=conn)
    monkeypatch.setattr('app.queue', queue)
    running_jobs_registry = rq.registry.StartedJobRegistry(connection=conn)
    monkeypatch.setattr('app.running_jobs_registry', running_jobs_registry)
    redis_lock = SimpleNamespace(Lock=MockRedisLock)
    monkeypatch.setattr('app.redis_lock', redis_lock)
    # monkeypatch.setattr('app.task.Cloud', MockCloud)


@pytest.fixture
def client():
    app.app.config['TESTING'] = True
    client = app.app.test_client()
    yield client


class HMAC:
    def new(self, *args, **kwargs):
        class Response:
            def hexdigest(self):
                pass
        return Response()

    def compare_digest(self, *args, **kwargs):
        return True


@pytest.fixture(autouse=True)
def bypass_dbx_hmac(monkeypatch) -> None:
    hmac = HMAC()
    monkeypatch.setattr('app.hmac', hmac)
