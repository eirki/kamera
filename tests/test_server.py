#! /usr/bin/env python3.6
# coding: utf-8
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock, patch

import fakeredis
import pytest
import rq
from PIL import Image

from kamera import server
from tests.mock_dropbox import MockDropbox


@patch("kamera.server.hmac", Mock())
@patch("kamera.server.dropbox.Dropbox", MockDropbox)
def test_webhook(client, tmpdir, monkeypatch) -> None:
    account_id = "test_webhook"
    temp_path = Path(tmpdir)
    file_name = "in_file.jpg"
    img = Image.new("RGB", (1, 1))
    img.save(temp_path / file_name, "PNG")

    with patch_redis() as mock_redis:
        mock_redis.hset(f"user:{account_id}", "token", "test_token")
        monkeypatch.setattr("kamera.server.config.uploads_path", temp_path)
        rv = client.post("/webhook", json={"list_folder": {"accounts": [account_id]}})
        assert rv.data == b""
        assert server.queue.job_ids == [f"{account_id}:{file_name}"]


@patch("kamera.server.hmac", Mock())
def test_rate_limiter(client) -> None:
    account_id = "test_rate_limiter"
    request_data = {"list_folder": {"accounts": [account_id]}}
    with patch("kamera.server.enqueue_new_entries") as test_called, patch_redis():
        client.post("/webhook", json=request_data)
        client.post("/webhook", json=request_data)
    assert test_called.call_count == 1


@contextmanager
def patch_redis() -> fakeredis.FakeStrictRedis:
    mock_redis = fakeredis.FakeStrictRedis()
    mock_queue = rq.Queue(connection=mock_redis)
    mock_running_jobs_registry = rq.registry.StartedJobRegistry(connection=mock_redis)
    with patch.multiple(
        "kamera.server",
        redis_client=mock_redis,
        queue=mock_queue,
        running_jobs_registry=mock_running_jobs_registry,
        redis_lock=Mock(),
    ):
        yield mock_redis


@pytest.fixture
def client():
    server.app.config["TESTING"] = True
    client = server.app.test_client()
    yield client
