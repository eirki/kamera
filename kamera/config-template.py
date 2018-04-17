#! /usr/bin/env python3.6
# coding: utf-8

from collections import namedtuple
from pathlib import Path

import pytz

app_id = ""

DBX_TOKEN = ""

db_host = ""
db_user = ""
db_passwd = ""
db_name = ""

home = Path()

exifpath = Path()

uploads_db_folder = Path("/Apps") / "fotokamera" / "Uploads"

kamera_db_folder = Path("/Apps") / "fotokamera"

backup_db_folder = Path("/Apps") / "fotokamera" / "Backup"

errors_db_folder = Path("/Apps") / "fotokamera" / "Error"


City = namedtuple("City", ["name", "lat", "lng", "locations"])
Location = namedtuple("Location", ["name", "lat", "lng"])

cities = [
    City(name="City1", lat=0.0, lng=0.0, locations=[
        Location(name="Location1", lat=0, lng=0),
        Location(name="Location2", lat=0, lng=0),
        ]),
    City(name="City2", lat=0.0, lng=0.0, locations=[
        Location(name="Location1", lat=0, lng=0),
        ]),
    City(name="City3", lat=0.0, lng=0.0, locations=[])
]

default_tz = pytz.timezone("Europe/Oslo")

Person = namedtuple("Person", ["name", "encodings"])
people = [
    Person(name="Person1 name", encodings=[]),
    Person(name="Person2 name", encodings=[]),
]

recognition_tolerance = 0.4

blur_tolerance = 100.00


def edit_tags(tags):
    for i, tag in enumerate(tags):
        pass