#! /usr/bin/env python3.6
# coding: utf-8
from kamera.logger import log

from types import SimpleNamespace
import datetime as dt
import json
from pathlib import Path

import dropbox
import pytest
import rq
import fakeredis

import app
from kamera import config

from typing import Optional


@pytest.mark.usefixtures("monkeypatch_redis_into_fakeredis", "monkeypatch_mock_dropbox", "bypass_dbx_hmac")
def test_webhook(client, tmpdir, monkeypatch, mock_redis) -> None:
    account_id = "test_account"
    temp_path = Path(tmpdir)
    file_name = "in_file.jpg"
    with open(temp_path / file_name, "w") as file:
        file.write("")
    monkeypatch.setattr('app.config.uploads_path', temp_path)
    mock_redis.hset(f"user:{account_id}", "token", "test_token")

    rv = client.post(
        '/kamera',
        data=json.dumps({"list_folder": {"accounts": [account_id]}}),
    )
    assert rv.data == b""
    assert app.queue.job_ids == [f"{account_id}:{file_name}"]


@pytest.mark.usefixtures("monkeypatch_redis_into_fakeredis", "monkeypatch_mock_dropbox", "bypass_dbx_hmac")
def test_rate_limiter(client, monkeypatch) -> None:
    class TestCalled:
        def __init__(self):
            self.called_times = 0

        def __call__(self, *args, **kwargs):
            self.called_times += 1

    test_called = TestCalled()
    account_id = "test_account2"
    monkeypatch.setattr('app.check_enqueue_entries', test_called)

    request_data = json.dumps({"list_folder": {"accounts": [account_id]}})
    client.post('/kamera', data=request_data)
    client.post('/kamera', data=request_data)
    assert test_called.called_times == 1


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


@pytest.fixture()
def bypass_dbx_hmac(monkeypatch) -> None:
    hmac = HMAC()
    monkeypatch.setattr('app.hmac', hmac)


class MockRedisLock:
    def __init__(self, *args, **kwargs):
        pass

    def acquire(self, *args, **kwargs):
        return True

    def release(self):
        pass

    def reset_all(self):
        pass


@pytest.fixture()
def mock_redis(*args, **kwargs) -> fakeredis.FakeStrictRedis:
    fake_redis_client = fakeredis.FakeStrictRedis()
    return fake_redis_client


@pytest.fixture()
def monkeypatch_redis_into_fakeredis(monkeypatch) -> None:
    fake_redis_client = mock_redis()
    fake_redis_client.flushall()
    monkeypatch.setattr('redis.from_url', mock_redis)
    queue = rq.Queue(connection=fake_redis_client)
    monkeypatch.setattr('app.queue', queue)
    running_jobs_registry = rq.registry.StartedJobRegistry(connection=fake_redis_client)
    monkeypatch.setattr('app.running_jobs_registry', running_jobs_registry)
    redis_lock = SimpleNamespace(Lock=MockRedisLock)
    monkeypatch.setattr('app.redis_lock', redis_lock)


class MockDropbox:
    def __init__(*args, **kwargs):
        pass

    def users_get_current_account(self):
        pass

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


@pytest.fixture()
def monkeypatch_mock_dropbox(monkeypatch):
    mock_module = SimpleNamespace(
        Dropbox=MockDropbox,
        files=SimpleNamespace(
            FileMetadata=dropbox.files.FileMetadata,
            PhotoMetadata=dropbox.files.PhotoMetadata,

        )
    )
    monkeypatch.setattr('app.dropbox', mock_module)
