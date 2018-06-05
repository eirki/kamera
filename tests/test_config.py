#! /usr/bin/env python3.6
# coding: utf-8
from kamera.logger import log

from pathlib import Path
from types import SimpleNamespace
import dropbox
import numpy as np
import pytest

from kamera import config

from typing import Optional

try:
    import face_recognition
except ImportError:
    face_recognition = None


def test_settings_default_tz(settings):
    assert settings.default_tz == "US/Eastern"


def test_settings_recognition_tolerance(settings):
    assert settings.recognition_tolerance == 0.4


def test_settings_tag_swaps(settings):
    assert settings.tag_swaps == {
        "Paris/10e arrondissement": "Holiday/France"
    }


def test_settings_folder_names(settings):
    assert settings.folder_names == {
        1: "January",
        2: "February",
        3: "March",
        4: "April",
        5: "May",
        6: "June",
        7: "July",
        8: "August",
        9: "September",
        10: "October",
        11: "November",
        12: "December"
      }


def test_settings_locations(settings):
    assert len(settings.locations) == 1
    location = settings.locations[0]
    assert location.name == "Paris"
    assert location.lat == 48.8566
    assert location.lng == 2.3522
    assert len(location.spots) == 2
    spot1, spot2 = location.spots
    assert spot1.name == "Place de la Concorde"
    assert spot1.lat == 48.8662
    assert spot1.lng == 2.3242
    assert spot2.name == "10e arrondissement"
    assert spot2.lat == 48.8698
    assert spot2.lng == 2.3523


if face_recognition is not None:
    def test_settings_recognition(settings):
        assert len(settings.recognition_data) == 2
        assert len(settings.recognition_data["Biden"]) == 1
        assert isinstance(settings.recognition_data["Biden"][0], np.ndarray)
        assert len(settings.recognition_data["Obama"]) == 2
        assert isinstance(settings.recognition_data["Obama"][0], np.ndarray)
        assert isinstance(settings.recognition_data["Obama"][1], np.ndarray)


@pytest.fixture()
def settings():
    dbx = MockDropbox()
    loaded_settings = config.Settings(dbx)
    return loaded_settings


class MockDropbox:
    def files_download(self, path: Path):
        with open(path, "rb") as file:
            data = file.read()
        filemetadata = None
        response = SimpleNamespace(raw=SimpleNamespace(data=data))
        return filemetadata, response

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
            )
            for file in files]
        mock_result = SimpleNamespace(entries=mock_entries, has_more=False)
        return mock_result

    def files_upload(self, f: bytes, path: str, autorename: Optional[bool]=False):
        with open(path, "wb") as file:
            file.write(f)
