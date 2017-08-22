#! /usr/bin/env python3.6
# coding: utf-8

from collections import namedtuple

import pytz

app_id = ""

DBX_TOKEN = ""

home = ""

exifpath = ""

uploads_db_folder = "/Camera Uploads"

kamera_db_folder = "/kamera"

backup_db_folder = "/backup"

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

Person = namedtuple("Person", ["name, encoding"])
people = [
    Person(name="Person1 name", encodings=[]),
    Person(name="Person2 name", encodings=[]),
]
