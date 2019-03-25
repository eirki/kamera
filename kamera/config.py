#! /usr/bin/env python3.6
# coding: utf-8
import json
import os
import typing as t
from collections import defaultdict
from io import BytesIO
from pathlib import Path

import dropbox
import face_recognition
import numpy as np
import yaml
from dotenv import load_dotenv
from dropbox import Dropbox
from redis import Redis
from requests import Response

env_path = Path(".") / ".env"
load_dotenv(dotenv_path=env_path)

app_id = os.environ["app_id"]

flask_rate_limit = int(os.environ["flask_rate_limit"])

redis_host = os.environ["REDIS_HOST"]
redis_port = os.environ["REDIS_PORT"]
redis_password = os.environ["REDIS_PASSWORD"]

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
        try:
            self.folder_names: t.Dict[int, str] = settings_data["folder_names"]
        except KeyError:
            self.folder_names: t.Dict[int, str] = {
                1: "01",
                2: "02",
                3: "03",
                4: "04",
                5: "05",
                6: "06",
                7: "07",
                8: "08",
                9: "09",
                10: "10",
                11: "11",
                12: "12",
            }
        try:
            self.tag_swaps: t.Dict[str, str] = settings_data.pop("tag_swaps")
        except KeyError:
            self.tag_swaps = {}
        try:
            location_data = _load_location_data(dbx)
            self.locations: t.List[Area] = location_data
        except dropbox.exceptions.ApiError:
            self.locations: t.List[Area] = []
        recognition_data = _load_recognition_data(dbx)
        self.recognition_data: t.Dict[str, t.List[np.array]] = recognition_data


def _load_settings(dbx: Dropbox) -> dict:
    settings_file = config_path / "settings.yaml"
    _, response = dbx.files_download(settings_file.as_posix())
    settings = yaml.safe_load(response.raw.data)
    return settings


class Spot(t.NamedTuple):
    name: str
    lat: float
    lng: float


class Area(t.NamedTuple):
    name: str
    lat: float
    lng: float
    spots: t.List[Spot]


def _load_location_data(dbx: Dropbox) -> t.List[Area]:
    places_file = config_path / "places.yaml"
    _, response = dbx.files_download(places_file.as_posix())
    location_dict = yaml.safe_load(response.raw.data)
    areas = [
        Area(
            name=location["name"],
            lat=location["lat"],
            lng=location["lng"],
            spots=[Spot(**spot) for spot in location["spots"]],
        )
        for location in location_dict
    ]
    return areas


def _load_recognition_data(dbx: Dropbox) -> t.Dict[str, t.List[np.array]]:
    recognition_path = config_path / "people"
    result = dbx.files_list_folder(path=recognition_path.as_posix(), recursive=True)

    people: t.Dict[str, t.List[np.array]] = defaultdict(list)

    paths = {Path(entry.path_display) for entry in result.entries}
    json_files = {path for path in paths if path.suffix == ".json"}
    for file in json_files:
        _load_encoding_json(file, dbx, people)

    unencoded_imgs = {
        path
        for path in paths
        if (
            path.suffix.lower() in image_extensions
            and path.with_suffix(".json") not in json_files
        )
    }
    for file in unencoded_imgs:
        _load_encoding_img(file, dbx, people)
    return people


def _load_encoding_json(file: Path, dbx: Dropbox, people: t.Dict[str, t.List]) -> None:
    name = file.parents[0].name
    _, response = dbx.files_download(file.as_posix())
    encoding = np.array(json.loads(response.raw.data))
    people[name].append(encoding)


def _load_encoding_img(img: Path, dbx: Dropbox, people: t.Dict[str, t.List]) -> None:
    name = img.parents[0].name
    _, response = dbx.files_download(img.as_posix())
    encoding = _get_facial_encoding(response, img)
    if encoding is None:
        return
    json_encoded = json.dumps(encoding.tolist())
    dbx.files_upload(f=json_encoded.encode(), path=img.with_suffix(".json").as_posix())
    people[name].append(encoding)


def _get_facial_encoding(response: Response, img_path: Path) -> np.array:
    loaded_img = face_recognition.load_image_file(BytesIO(response.raw.data))
    encodings = face_recognition.face_encodings(loaded_img)
    if len(encodings) == 0:
        print(f"Warning: No encodings found: {img_path}")
        return None
    elif len(encodings) > 1:
        raise Exception(f"Multiple encodings found: {img_path}")
    encoding = encodings[0]
    return encoding


def get_dbx_token(redis_client: Redis, account_id: str) -> str:
    token = redis_client.hget(f"user:{account_id}", "token").decode()
    return token
