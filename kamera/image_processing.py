#! /usr/bin/env python3.6
# coding: utf-8
import datetime as dt
import subprocess
import sys
import typing as t
from io import BytesIO
from pathlib import Path

import dropbox
import piexif
from geopy.distance import great_circle
from PIL import Image
from resizeimage import resizeimage

from kamera import config, recognition
from kamera.logger import log


def get_closest_area(
    lat: float, lng: float, locations: t.List[config.Area]
) -> t.Optional[config.Area]:
    """Return area if image taken within 50 km from center of area"""
    distances = [
        (great_circle((area.lat, area.lng), (lat, lng)).km, area) for area in locations
    ]
    distance, closest_area = min(distances)
    return closest_area if distance < 50 else None


def get_closest_spot(
    lat: float, lng: float, area: config.Area
) -> t.Optional[config.Spot]:
    """Return closest spot if image taken within 100 m"""
    if not area.spots:
        return None

    distances = [
        (great_circle((spot.lat, spot.lng), (lat, lng)).meters, spot)
        for spot in area.spots
    ]
    distance, closest_spot = min(distances)
    return closest_spot if distance < 100 else None


def get_geo_tag(
    lat: float, lng: float, locations: t.List[config.Area]
) -> t.Optional[str]:
    tagstring = None
    if lat and lng:
        area = get_closest_area(lat, lng, locations)
        if area:
            spot = get_closest_spot(lat, lng, area)
            if spot:
                tagstring = "/".join([area.name, spot.name])
            else:
                tagstring = area.name
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


def add_tag(data: bytes, tags: t.List[str]) -> bytes:
    # metadata["0th"][piexif.ImageIFD.XPKeywords] = tagstring.encode("utf-16")
    args = ["exiftool"]
    if sys.platform == "win32":
        args.append("-L")
    args.extend([f"-xmp:Subject={tag}" for tag in tags])
    args.append("-")
    proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    stdout, stderr = proc.communicate(data)
    new_data = stdout
    return new_data


def main(
    data: bytes,
    filepath: Path,
    date: dt.datetime,
    settings: config.Settings,
    coordinates: t.Optional[dropbox.files.GpsCoordinates],
    dimensions: t.Optional[dropbox.files.Dimensions],
) -> t.Optional[bytes]:
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
        exif_metadata["Exif"][piexif.ExifIFD.DateTimeOriginal].decode()
    except KeyError:
        log.info(f"{name}: Inserting date {date}")
        add_date(date, exif_metadata)
        data_changed = True
    tags = []
    # Get geotag.
    if coordinates:
        geotag = get_geo_tag(
            lat=coordinates.latitude,
            lng=coordinates.longitude,
            locations=settings.locations,
        )
        if geotag is not None:
            tags.append(geotag)
    # Check if any recognized faces
    peopletags = recognition.recognize_face(data, settings)
    tags.extend(peopletags)
    # Add tags to image data if present
    if tags:
        tags = [settings.tag_swaps.get(tag, tag) for tag in tags]
        log.info(f"{name}: Tagging {tags}")
        data = add_tag(data, tags)
        data_changed = True
    # If no convertion, resizing,date fixing, or tagging, return
    if not data_changed:
        return None

    # Add metadata from metadata object to image data
    try:
        metadata_bytes = piexif.dump(exif_metadata)
    except ValueError:
        # This Element piexif.ExifIFD.SceneType causes error on dump
        # Workaround for unknown reason
        del exif_metadata["Exif"][piexif.ExifIFD.SceneType]
        metadata_bytes = piexif.dump(exif_metadata)
    new_file = BytesIO()
    piexif.insert(metadata_bytes, data, new_file)
    new_data = new_file.getvalue()
    return new_data
