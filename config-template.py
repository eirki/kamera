#! /usr/bin/env python3.6
# coding: utf-8

from collections import namedtuple

app_id = ""

home = ""

DBX_TOKEN = ""

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

kamera_db_folder = "/kamera"
