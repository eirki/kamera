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
    temp_path = Path(tmpdir)
    with open(temp_path / "in_file.jpg", "w") as file:
        file.write("")
    monkeypatch.setattr('app.config.uploads_path', temp_path)
    rv = client.post(
        '/kamera',
        data=json.dumps({"delta": {"users": ["userid1"]}}),
    )
    assert rv.data == b""
    assert app.queue.job_ids == ["in_file.jpg"]
