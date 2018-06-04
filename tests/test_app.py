#! /usr/bin/env python3.6
# coding: utf-8
from kamera.logger import log

import json
from pathlib import Path

import app
from kamera import config


def test_empty_db(client):
    """Start with a blank database."""

    rv = client.get('/')
    assert config.app_id.encode() in rv.data


def test_webhook(client, tmpdir, monkeypatch, mock_redis) -> None:
    account_id = "test_account"
    temp_path = Path(tmpdir)
    file_name = "in_file.jpg"
    with open(temp_path / file_name, "w") as file:
        file.write("")
    monkeypatch.setattr('app.config.uploads_path', temp_path)
    mock_redis.hset(f"user:{account_id}", "token", "test_token")
    token = mock_redis.hget(f"user:{account_id}", "token").decode()

    rv = client.post(
        '/kamera',
        data=json.dumps({"list_folder": {"accounts": [account_id]}}),
    )
    assert rv.data == b""
    assert app.queue.job_ids == [f"{account_id}:{file_name}"]


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
