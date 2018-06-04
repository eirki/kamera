#! /usr/bin/env python3.6
# coding: utf-8
from kamera.logger import log

from types import SimpleNamespace
from pathlib import Path
import shutil
import os
import datetime as dt

import pytest
import dropbox
import rq
import fakeredis

import app
from kamera import task

from typing import Optional


@pytest.fixture()
def settings():
    return task.Cloud("test_account").settings


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


class BadInputError(dropbox.exceptions.BadInputError):
    pass


class MockDropbox:

    def __init__(*args, **kwargs):
        pass

    def users_get_current_account(self):
        pass

    def files_download(self, path: Path):
        with open(path, "rb") as file:
            data = file.read()
        filemetadata = None
        response = SimpleNamespace(raw=SimpleNamespace(data=data))
        return filemetadata, response

    def files_upload(self, f: bytes, path: str, autorename: Optional[bool]=False):
        if not Path(path).parent.exists():
            raise BadInputError(request_id=1, message="message")
        with open(path, "wb") as file:
            file.write(f)

    def files_move(self, from_path: str, to_path: str, autorename: Optional[bool]=False) -> None:
        if not Path(from_path).parent.exists() or not Path(to_path).parent.exists():
            raise BadInputError(request_id=1, message="message")
        shutil.move(from_path, Path(to_path).parent)

    def files_copy(self, from_path: str, to_path: str, autorename: Optional[bool]=False) -> None:
        if not Path(from_path).parent.exists() or not Path(to_path).parent.exists():
            raise BadInputError(request_id=1, message="message")
        shutil.copy(from_path, Path(to_path).parent)

    def files_create_folder(self, path, autorename=False) -> None:
        os.makedirs(path)

    def files_list_folder(
        self,
        path: str,
        recursive: Optional[bool]=False,
        include_media_info: Optional[bool]=False
    ):
        path_obj = Path(path)
        files = path_obj.rglob("*") if recursive else path_obj.iterdir()
        mock_entries = [
            dropbox.files.FileMetadata(
                path_display=file.as_posix(),
                path_lower=file.as_posix().lower(),
                client_modified=dt.datetime(2000, 1, 1)
            )
            for file in files]
        mock_result = SimpleNamespace(entries=mock_entries, has_more=False)
        return mock_result

    def files_list_folder_continue(self, cursor) -> None:
        pass


@pytest.fixture(autouse=True)
def mock_cloud(monkeypatch):
    mock_module = SimpleNamespace(
        Dropbox=MockDropbox,
        exceptions=SimpleNamespace(BadInputError=BadInputError),
        files=SimpleNamespace(
            FileMetadata=dropbox.files.FileMetadata,
            PhotoMetadata=dropbox.files.PhotoMetadata,

        )
    )
    monkeypatch.setattr('kamera.task.dropbox', mock_module)
    monkeypatch.setattr('app.dropbox', mock_module)


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
    fake_redis_client = fakeredis.FakeStrictRedis()
    fake_redis_client.flushall()
    monkeypatch.setattr('app.redis_client', fake_redis_client)
    queue = rq.Queue(connection=fake_redis_client)
    monkeypatch.setattr('app.queue', queue)
    running_jobs_registry = rq.registry.StartedJobRegistry(connection=fake_redis_client)
    monkeypatch.setattr('app.running_jobs_registry', running_jobs_registry)
    redis_lock = SimpleNamespace(Lock=MockRedisLock)
    monkeypatch.setattr('app.redis_lock', redis_lock)
    return fake_redis_client


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
