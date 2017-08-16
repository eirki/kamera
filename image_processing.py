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
from resizeimage import resizeimage

import config


def get_closest_city(lat, lng):
    """Return city if image taken within 50 km from center of city"""
    distance, closest_city = min((
        great_circle((city.lat, city.lng), (lat, lng)).km, city)
        for city in config.cities
    )
    return closest_city if distance < 50 else None


def get_closest_location(lat, lng, city):
    """Return closest location if image taken within 100 m"""
    if not city.locations:
        return None
    distance, closest_location = min((
        great_circle((loc.lat, loc.lng), (lat, lng)).meters, loc)
        for loc in city.locations
    )
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

    if db_metadata and db_metadata.location:
        img_tz = TimezoneFinder().timezone_at(lat=db_metadata.location.latitude,
                                              lng=db_metadata.location.longitude)
        if img_tz:
            local_date = utc_date.astimezone(tz=pytz.timezone(img_tz))
            return local_date

    local_date = utc_date.astimezone(tz=config.default_tz)
    return local_date


def convert_png_to_jpg(entry, data):
    print(f"Converting to PNG: {entry.name}")
    old_data = BytesIO(data)
    new_data = BytesIO()
    Image.open(old_data).save(new_data, "JPEG")
    data = new_data.getvalue()
    return data


def resize(entry, data):
    print(f"Resizing {entry.name}")
    img = Image.open(BytesIO(data))
    landscape = True if img.width > img.height else False
    if landscape:
        img = resizeimage.resize_height(img, size=1440)
    else:
        img = resizeimage.resize_width(img, size=1440)

    new_data = BytesIO()
    img.save(new_data, "JPEG")
    data = new_data.getvalue()
    return data


def add_date(entry, date, metadata):
    datestring = date.strftime("%Y:%m:%d %H:%M:%S")
    print(f"Inserting date to {entry.name}: {datestring}")
    metadata["Exif"][piexif.ExifIFD.DateTimeOriginal] = datestring


def add_tag(entry, metadata, tagstring):
    print(f"Tagging {entry.name}: {tagstring}")
    metadata["0th"][piexif.ImageIFD.XPKeywords] = tagstring.encode("utf-16")


def main(entry, data, db_metadata):
    data_changed = None

    # Convert image from PNG to JPG, put data into BytesIO obj
    if entry.path_lower.endswith("png"):
        data = convert_png_to_jpg(entry, data)
        data_changed = True

    # Make metadata object from image data
    exif_metadata = piexif.load(data)

    # Convert image to smaller resolution if needed
    if db_metadata and db_metadata.dimensions.width > 1440 and db_metadata.dimensions.height > 1440:
        data = resize(entry, data)
        data_changed = True

    # Parse image date. Add date to metadata object if missing
    try:
        orig_datestring = exif_metadata["Exif"][piexif.ExifIFD.DateTimeOriginal].decode()
        date = dt.datetime.strptime(orig_datestring, "%Y:%m:%d %H:%M:%S")
    except KeyError:
        date = parse_date(entry, db_metadata)
        add_date(entry, date, exif_metadata)
        data_changed = True

    # Get image tag. Add tag to metadata object if present
    tagstring = None
    if db_metadata and db_metadata.location:
        tagstring = get_geo_tag(lat=db_metadata.location.latitude,
                                lng=db_metadata.location.longitude)
        if tagstring:
            add_tag(entry, exif_metadata, tagstring)
            data_changed = True

    # If no convertion, date fixing, or tagging, return only the parsed image date
    if not data_changed:
        return None, date

    # Add metadata from metadata object to image data, run through exiftool if tagged
    metadata_bytes = piexif.dump(exif_metadata)
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
