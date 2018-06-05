#! /usr/bin/env python3.6
# coding: utf-8
import os
from collections import defaultdict
from pathlib import Path
from io import BytesIO
import json

import yaml
from dotenv import load_dotenv
import numpy as np
try:
    import face_recognition
except ImportError:
    face_recognition = None

from typing import List, Dict
from dropbox import Dropbox

env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path)

app_id = os.environ["app_id"]

flask_rate_limit = int(os.environ["flask_rate_limit"])

redis_url = os.environ['REDISTOGO_URL']

APP_SECRET = os.environ["APP_SECRET"].encode()

dbx_path = Path(os.environ["dbx_path"])
uploads_path = dbx_path / "Uploads"
review_path = dbx_path / "Review"
backup_path = dbx_path / "Backup"
errors_path = dbx_path / "Error"
config_path = dbx_path / "config"

rq_dashboard_username = os.environ["rq_dashboard_username"]
rq_dashboard_password = os.environ["rq_dashboard_password"]

image_extensions = {".jpg", ".jpeg", ".png"}
video_extensions = {".mp4", ".mov", ".gif"}
media_extensions = tuple(image_extensions | video_extensions)


class Settings:
    def __init__(self, dbx: Dropbox) -> None:
        settings_data = _load_settings(dbx)
        self.default_tz: str = settings_data["default_tz"]
        self.recognition_tolerance: float = settings_data["recognition_tolerance"]
        self.folder_names: Dict[str, str] = settings_data["folder_names"]
        self.tag_swaps: Dict[str, str] = settings_data.pop("tag_swaps")
        location_data = _load_location_data(dbx)
        self.locations: List[Area] = location_data
        if face_recognition is not None:
            recognition_data = _load_recognition_data(dbx)
            self.recognition_data: Dict[str, List[np.array]] = recognition_data


def _load_settings(dbx: Dropbox):
    settings_file = config_path / "settings.yaml"
    _, response = dbx.files_download(settings_file.as_posix())
    settings = yaml.load(response.raw.data)
    return settings


class Area:
    def __init__(self, name, lat: float, lng: float, spots: List[dict]) -> None:
        self.name: str = name
        self.lat: float = lat
        self.lng: float = lng
        self.spots: List[Spot] = [Spot(**spot) for spot in spots]

    def __repr__(self):
        return self.name


class Spot:
    def __init__(self, name: str, lat: float, lng: float) -> None:
        self.name: str = name
        self.lat: float = lat
        self.lng: float = lng

    def __repr__(self):
        return self.name


def _load_location_data(dbx: Dropbox):
    places_file = config_path / "places.yaml"
    _, response = dbx.files_download(places_file.as_posix())
    location_dict = yaml.load(response.raw.data)
    areas = [Area(**location) for location in location_dict]
    return areas


def _load_recognition_data(dbx: Dropbox):
    recognition_path = config_path / "people"
    result = dbx.files_list_folder(
        path=recognition_path.as_posix(),
        recursive=True
    )

    people: Dict[str, List[np.array]] = defaultdict(list)

    paths = {Path(entry.path_display) for entry in result.entries}
    jsons = {path for path in paths if path.suffix == ".json"}
    for file in jsons:
        name = file.parents[0].name
        _, response = dbx.files_download(file.as_posix())
        encoding = np.array(json.loads(response.raw.data))
        people[name].append(encoding)

    unencoded_imgs = {
        path for path in paths if (
            path.suffix in image_extensions and
            path.with_suffix(".json") not in jsons)
    }
    for img in unencoded_imgs:
        name = img.parents[0].name
        encoding = _get_facial_encoding(dbx, img)
        if encoding is not None:
            json_encoded = json.dumps(encoding.tolist())
            dbx.files_upload(
                f=json_encoded.encode(),
                path=img.with_suffix(".json").as_posix()
            )
            people[name].append(encoding)
    return people


def _get_facial_encoding(dbx: Dropbox, img_path: Path) -> np.array:
    _, response = dbx.files_download(img_path.as_posix())
    loaded_img = face_recognition.load_image_file(BytesIO(response.raw.data))
    encodings = face_recognition.face_encodings(loaded_img)
    if len(encodings) == 0:
        print(f"Warning: No encodings found: {img_path}")
        return None
    elif len(encodings) > 1:
        raise Exception(f"Multiple encodings found: {img_path}")
    encoding = encodings[0]
    return encoding


def get_dbx_token(redis_client, account_id):
    token = redis_client.hget(f"user:{account_id}", "token").decode()
    return token
