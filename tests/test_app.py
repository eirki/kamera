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


def test_webhook(client, tmpdir, monkeypatch) -> None:
    account_id = "account_id1"
    temp_path = Path(tmpdir)
    file_name = "in_file.jpg"
    with open(temp_path / file_name, "w") as file:
        file.write("")
    monkeypatch.setattr('app.config.uploads_path', temp_path)
    rv = client.post(
        '/kamera',
        data=json.dumps({"list_folder": {"accounts": [account_id]}}),
    )
    assert rv.data == b""
    assert app.queue.job_ids == [f"{account_id}:{file_name}"]
