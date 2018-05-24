#! /usr/bin/env python3.6
# coding: utf-8
from types import SimpleNamespace
from collections import defaultdict

from kamera import config

import pytest


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


class MockDropbox:
    def files_download(self, path):
        with open(path) as file:
            data = file.read()
        filemetadata = None
        response = SimpleNamespace(raw=SimpleNamespace(data=data))
        return filemetadata, response

    def files_list_folder(self):
        pass

    def files_upload(self):
        pass

    def users_get_current_account(self):
        pass


class MockCloud:
    def __init__(self):
        self.dbx = MockDropbox()

    def list_entries(self):
        pass

    def execute_transfer(self):
        pass

    def move_entry(self):
        pass

    def copy_entry(self):
        pass

    def upload_entry(self):
        pass

    def download_entry(self):
        pass
