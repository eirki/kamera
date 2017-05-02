#! /usr/bin/env python3.6
# coding: utf-8

from io import BytesIO
import subprocess
import datetime as dt
import pytz

from timezonefinderL import TimezoneFinder
from PIL import Image
import piexif
from geopy.distance import great_circle

import config


def get_closest_city(lat, lng):
    """Return city if image taken within 50 km from center of city"""
    distance, closest_city = min((great_circle((city.lat, city.lng), (lat, lng)).km, city) for city in config.cities)
    return closest_city if distance < 50 else None


def get_closest_location(lat, lng, city):
    """Return closest location if image taken within 100 m"""
    distance, closest_location = min((great_circle((loc.lat, loc.lng), (lat, lng)).meters, loc) for loc in city.locations)
    return closest_location if distance < 100 else None


def get_geo_tag(lat, lng):
    tagstring = None
    if lat and lng:
        city = get_closest_city(lat, lng)
        if city:
            loc = get_closest_location(lat, lng, city)
            if loc:
                tagstring = "/".join([city.name, loc.name])
            else:
                tagstring = city.name
    return tagstring


def parse_date(entry, db_metadata):
    if "burst" in entry.name.lower():
        naive_date = dt.datetime.strptime(entry.name[20:34], "%Y%m%d%H%M%S")
    else:
        try:
            naive_date = dt.datetime.strptime(entry.name[:19], "%Y-%m-%d %H.%M.%S")
        except ValueError:
            naive_date = entry.client_modified
    utc_date = naive_date.replace(tzinfo=dt.timezone.utc)
    tz = TimezoneFinder().timezone_at(lat=db_metadata.location.latitude,
                                      lng=db_metadata.location.longitude)
    local_date = utc_date.replace(tzinfo=dt.timezone.utc).astimezone(tz=pytz.timezone(tz))
    return local_date


def main(entry, db_metadata, data):
    new_data = None
    if entry.path_lower.endswith("png"):
        print(f"Converting to PNG: {entry.name}")
        new_data = BytesIO()
        Image.open(BytesIO(data)).save(new_data, "JPEG")
        data = new_data.getvalue()

    metadata = piexif.load(data)

    datestring = None
    try:
        orig_datestring = metadata["Exif"][piexif.ExifIFD.DateTimeOriginal].decode()
        date = dt.datetime.strptime(orig_datestring, "%Y:%m:%d %H:%M:%S")
    except KeyError:
        date = parse_date(entry, db_metadata)
        datestring = date.strftime("%Y:%m:%d %H:%M:%S")
        print(f"Inserting date to {entry.name}: {datestring}")
        metadata["Exif"][piexif.ExifIFD.DateTimeOriginal] = datestring

    tagstring = None
    if db_metadata and db_metadata.location:
        tagstring = get_geo_tag(lat=db_metadata.location.latitude,
                                lng=db_metadata.location.longitude)
        if tagstring:
            print(f"Tagging {entry.name}: {tagstring}")
            metadata["0th"][piexif.ImageIFD.XPKeywords] = tagstring.encode("utf-16")

    if not (new_data, tagstring, datestring):
        return None, None

    metadata_bytes = piexif.dump(metadata)
    new_file = BytesIO()
    piexif.insert(metadata_bytes, data, new_file)
    new_data = new_file.getvalue()
    if tagstring:
        print("Converting exif to xmp")
        proc = subprocess.Popen([config.exifpath, "-xmp:Subject<exif:XPKeywords", "-"],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        stdout, stderr = proc.communicate(new_data)
        new_data = stdout

    return new_data, date
