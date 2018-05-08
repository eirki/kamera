#! /usr/bin/env python3.6
# coding: utf-8
from kamera.logger import log

from io import BytesIO
import subprocess
import datetime as dt
import sys

from PIL import Image
import piexif
from geopy.distance import great_circle
from resizeimage import resizeimage

from pathlib import Path
from typing import List, Union, Optional, Tuple
import dropbox

from kamera import config
from kamera import recognition


def get_closest_city(lat: float, lng: float) -> Optional[config.City]:
    """Return city if image taken within 50 km from center of city"""
    distances = [
        (great_circle((city.lat, city.lng), (lat, lng)).km, city)
        for city in config.cities
    ]
    distance, closest_city = min(distances)
    return closest_city if distance < 50 else None


def get_closest_location(lat: float, lng: float, city: config.City) -> Optional[config.Location]:
    """Return closest location if image taken within 100 m"""
    if not city.locations:
        return None
    distances = [
        (great_circle((loc.lat, loc.lng), (lat, lng)).meters, loc)
        for loc in city.locations
    ]
    distance, closest_location = min(distances)
    return closest_location if distance < 100 else None


def get_geo_tag(lat: float, lng: float) -> str:
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


def convert_png_to_jpg(data: bytes) -> bytes:
    old_data = BytesIO(data)
    new_data = BytesIO()
    Image.open(old_data).save(new_data, "JPEG")
    data = new_data.getvalue()
    return data


def resize(data: bytes) -> bytes:
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


def add_date(date: dt.datetime, metadata: dict):
    datestring = date.strftime("%Y:%m:%d %H:%M:%S")
    metadata["Exif"][piexif.ExifIFD.DateTimeOriginal] = datestring


def add_tag(data: bytes, tags: List[str]) -> bytes:
    # metadata["0th"][piexif.ImageIFD.XPKeywords] = tagstring.encode("utf-16")
    args = [str(config.exifpath)]
    if sys.platform == "win32":
        args.append("-L")
    args.extend([f"-xmp:Subject={tag}" for tag in tags])
    args.append("-")
    proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    stdout, stderr = proc.communicate(data)
    new_data = stdout
    return new_data


def main(data: bytes,
         filepath: Path,
         date: dt.datetime,
         location: Union[dropbox.files.GpsCoordinates, None],
         dimensions: Union[dropbox.files.Dimensions, None]
         ) -> Tuple[bytes, Union[dt.datetime, None]]:
    data_changed = False
    name = filepath.stem

    # Convert image from PNG to JPG, put data into BytesIO obj
    if filepath.suffix.lower() == ".png":
        log.info(f"{name}: Converting to JPG")
        data = convert_png_to_jpg(data)
        data_changed = True

    # Make metadata object from image data
    exif_metadata = piexif.load(data)

    # Convert image to smaller resolution if needed
    if dimensions and dimensions.width > 1440 and dimensions.height > 1440:
        log.info(f"{name}: Resizing")
        data = resize(data)
        data_changed = True

    # Add date to metadata object if missing
    try:
        orig_datestring = exif_metadata["Exif"][piexif.ExifIFD.DateTimeOriginal].decode()
        exif_date = dt.datetime.strptime(orig_datestring, "%Y:%m:%d %H:%M:%S")
    except KeyError:
        log.info(f"{name}: Inserting date {date}")
        add_date(date, exif_metadata)
        exif_date = None
        data_changed = True

    tags = []
    # Get geotag.
    if location:
        geotag = get_geo_tag(
            lat=location.latitude,
            lng=location.longitude,
        )
        if geotag is not None:
            tags.append(geotag)

    # Check if any recognized faces
    if recognition.face_recognition is not None:
        peopletags = recognition.recognize_face(data)
        tags.extend(peopletags)

    # Add tags to image data if present
    if tags:
        tags = [config.tag_switches.get(tag, tag) for tag in tags]
        log.info(f"{name}: Tagging {tags}")
        data = add_tag(data, tags)
        data_changed = True

    # If no convertion, resizing,date fixing, or tagging, return only the parsed image date
    if not data_changed:
        return None, exif_date

    # Add metadata from metadata object to image data
    metadata_bytes = piexif.dump(exif_metadata)
    new_file = BytesIO()
    piexif.insert(metadata_bytes, data, new_file)
    new_data = new_file.getvalue()

    return new_data, exif_date
