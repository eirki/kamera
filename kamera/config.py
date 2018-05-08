#! /usr/bin/env python3.6
# coding: utf-8

import os
from collections import defaultdict
from pathlib import Path
from io import BytesIO
import numpy as np
import json
import yaml

import face_recognition

from typing import List, Dict

app_id = os.environ["app_id"]

flask_rate_limit = os.environ["flask_rate_limit"]

APP_SECRET = os.environ["APP_SECRET"].encode()
DBX_TOKEN = os.environ["DBX_TOKEN"]

dbx_path = Path("/Apps/fotokamera")
uploads_path = dbx_path / "Uploads"
review_path = dbx_path / "Review"
backup_path = dbx_path / "Backup"
errors_path = dbx_path / "Error"
config_path = dbx_path / "config"


settings: List[str] = []
tag_swaps: Dict[str, str] = {}

places_file = dbx_path / "config" / "places.yaml"


class City:
    def __init__(self, name, lat, lng, locations):
        self.name: str = name
        self.lat: float = lat
        self.lng: float = lng
        self.locations: List[Location] = [Location(**loc) for loc in locations]


class Location:
    def __init__(self, name, lat, lng):
        self.name: str = name
        self.lat: float = lat
        self.lng: float = lng


cities: List[City] = []

people: Dict[str, List[np.array]] = defaultdict(list)


def load_settings(dbx):
    settings_file = config_path / "settings.yaml"
    _, response = dbx.files_download(settings_file.as_posix())
    settings = yaml.load(response.raw.data)
    tag_swaps.update(settings.pop("tag_swaps"))


def load_location_data(dbx):
    _, response = dbx.files_download(places_file.as_posix())
    data = yaml.load(response.raw.data)
    cities.extend([City(**place) for place in data])


def load_recognition_data(dbx):
    root_path = config_path / "people"
    result = dbx.files_list_folder(
        path=root_path.as_posix(),
        recursive=True
    )
    media_extensions = (".jpg", ".jpeg", ".png")

    paths = {Path(entry.path_display) for entry in result.entries}
    jsons = {path for path in paths if path.suffix == ".json"}
    for file in jsons:
        name = file.parents[0].name
        _, response = dbx.files_download(file.as_posix())
        encoding = np.array(json.loads(response.raw.data))
        people[name].append(encoding)

    unencoded_imgs = {
        path for path in paths if (
            path.suffix in media_extensions and
            path.with_suffix(".json") not in jsons)
    }
    for img in unencoded_imgs:
        name = img.parents[0].name
        encoding = _get_facial_encoding(img)
        json_encoded = json.dumps(encoding.tolist())
        dbx.files_upload(
            f=json_encoded.encode(),
            path=img.with_suffix(".json").as_posix()
        )
        people[name].append(encoding)


def _get_facial_encoding(dbx, img_path):
    _, response = dbx.files_download(img_path.as_posix())
    loaded_img = face_recognition.load_image_file(BytesIO(response.raw.data))
    encodings = face_recognition.face_encodings(loaded_img)
    if len(encodings) == 0:
        print(f"Warning: No encodings found: {img_path}")
        return
    elif len(encodings) > 1:
        raise Exception(f"Multiple encodings found: {img_path}")
    encoding = encodings[0]
    return encoding
