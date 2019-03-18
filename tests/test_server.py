#! /usr/bin/env python3.6
# coding: utf-8
from kamera.logger import log

from types import SimpleNamespace
import json
from pathlib import Path
from unittest.mock import Mock, patch

import dropbox
import pytest
import rq
import fakeredis

from kamera import server
from tests.mock_dropbox import MockDropbox


@pytest.mark.usefixtures(
    "monkeypatch_mock_dropbox", "bypass_dbx_hmac"
)
def test_webhook(client, tmpdir, monkeypatch) -> None:
    account_id = "test_webhook"
    temp_path = Path(tmpdir)
    file_name = "in_file.jpg"
    with open(temp_path / file_name, "w") as file:
        file.write("")
    mock_redis = fakeredis.FakeStrictRedis()
    monkeypatch_redis_into_fakeredis(monkeypatch, mock_redis)
    mock_redis.hset(f"user:{account_id}", "token", "test_token")
    patch("kamera.server.config.uploads_path", temp_path)
    rv = client.post(
        "/webhook", data=json.dumps({"list_folder": {"accounts": [account_id]}})
    )
    assert rv.data == b""
    assert server.queue.job_ids == [f"{account_id}:{file_name}"]


# @pytest.mark.usefixtures(
#     "mock_redis", "monkeypatch_mock_dropbox", "bypass_dbx_hmac"
# )
# def test_rate_limiter(client) -> None:
#     class TestCalled:
#         def __init__(self):
#             self.called_times = 0

#         def __call__(self, *args, **kwargs):
#             self.called_times += 1

#     test_called = TestCalled()
#     account_id = "test_rate_limiter"
#     monkeypatch.setattr("kamera.server.check_enqueue_entries", test_called)

#     request_data = json.dumps({"list_folder": {"accounts": [account_id]}})
#     client.post("/kamera", data=request_data)
#     client.post("/kamera", data=request_data)
#     assert test_called.called_times == 1


@pytest.fixture
def client():
    server.app.config["TESTING"] = True
    client = server.app.test_client()
    yield client


@pytest.fixture()
def bypass_dbx_hmac(monkeypatch) -> None:
    hmac = Mock()
    monkeypatch.setattr("kamera.server.hmac", hmac)


def monkeypatch_redis_into_fakeredis(monkeypatch, mock_redis: fakeredis.FakeStrictRedis) -> None:
    monkeypatch.setattr("redis.Redis", lambda *a, **kw: mock_redis)
    queue = rq.Queue(connection=mock_redis)
    monkeypatch.setattr("kamera.server.queue", queue)
    running_jobs_registry = rq.registry.StartedJobRegistry(connection=mock_redis)
    monkeypatch.setattr("kamera.server.running_jobs_registry", running_jobs_registry)
    monkeypatch.setattr("kamera.server.redis_lock", Mock())


@pytest.fixture()
def monkeypatch_mock_dropbox(monkeypatch):
    mock_module = SimpleNamespace(
        Dropbox=MockDropbox,
        files=SimpleNamespace(
            FileMetadata=dropbox.files.FileMetadata,
            PhotoMetadata=dropbox.files.PhotoMetadata,
        ),
    )
    monkeypatch.setattr("kamera.server.dropbox", mock_module)
