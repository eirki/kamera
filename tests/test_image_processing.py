#! /usr/bin/env python3.6
# coding: utf-8
from pathlib import Path
import sys
import subprocess
import datetime as dt

import pytest
import dropbox
from PIL import Image
import pytz
import piexif
from io import BytesIO

from kamera import image_processing

from typing import Tuple, Optional

try:
    import face_recognition
except ImportError:
    face_recognition = None

test_images_path = Path.cwd() / "tests" / "test_images"


def _get_tag(data: bytes) -> str:
    args = ["exiftool"]
    if sys.platform == "win32":
        args.append("-L")
    args.append("-xmp:Subject")
    args.append("-")
    proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    stdout, stderr = proc.communicate(data)
    tags = stdout.decode().split(":")[-1].strip()
    return tags


def _get_dimensions(data: bytes) -> Tuple[int, int]:
    img = Image.open(BytesIO(data))
    width, height = img.size
    return width, height


def _get_date(data: bytes) -> dt.datetime:
    exif_metadata = piexif.load(data)
    date_string = exif_metadata["Exif"][piexif.ExifIFD.DateTimeOriginal].decode()
    date_obj = dt.datetime.strptime(date_string, "%Y:%m:%d %H:%M:%S")
    return date_obj


def assert_image_attrs_identical(output_data: bytes, desired_data: bytes):
    output_tag = _get_tag(output_data)
    output_dimensions = _get_dimensions(output_data)
    output_date = _get_date(output_data)
    desired_tag = _get_tag(desired_data)
    desired_dimensions = _get_dimensions(desired_data)
    desired_date = _get_date(desired_data)
    assert output_tag == desired_tag
    assert output_dimensions == desired_dimensions
    assert output_date == desired_date


def fetch_processing_output(
        filename: str,
        dimensions: Optional[dropbox.files.Dimensions]=None,
        location: Optional[dropbox.files.GpsCoordinates]=None,
        date: Optional[dt.datetime]=None
        ) -> bytes:
    filepath_input = test_images_path / "input" / filename
    with open(filepath_input, "rb") as file:
        input_data = file.read()

    output_data = image_processing.main(
        data=input_data,
        filepath=test_images_path / "input" / filename,
        dimensions=dimensions,
        location=location,
        date=date,
        )
    return output_data


def fetch_desired_output(filename: str) -> bytes:
    filepath_desired_output = test_images_path / "desired_output" / filename
    with open(filepath_desired_output, "rb") as file:
        desired_output = file.read()
    return desired_output


@pytest.mark.usefixtures("load_settings", "load_location_data")
def test_tag_spot() -> None:
    filename = "spot.jpg"
    loc = dropbox.files.GpsCoordinates(latitude=48.8662694, longitude=2.3242583)
    output = fetch_processing_output(filename, location=loc)
    desired_output = fetch_desired_output(filename)
    assert_image_attrs_identical(output, desired_output)


@pytest.mark.usefixtures("load_settings", "load_location_data")
def test_tag_area() -> None:
    filename = "area.jpg"
    loc = dropbox.files.GpsCoordinates(latitude=48.8715194, longitude=2.3372444)
    output = fetch_processing_output(filename, location=loc)
    desired_output = fetch_desired_output(filename)
    assert_image_attrs_identical(output, desired_output)


@pytest.mark.usefixtures("load_settings")
def test_png() -> None:
    filename = "filetype.png"
    date = (
        dt.datetime.strptime("2018-05-14 16:07:59", "%Y-%m-%d %H:%M:%S")
        .replace(tzinfo=dt.timezone.utc)
        .astimezone(tz=pytz.timezone("Europe/Paris"))
    )
    output = fetch_processing_output(filename, date=date)
    desired_output = fetch_desired_output("filetype.jpg")
    assert_image_attrs_identical(output, desired_output)


@pytest.mark.usefixtures("load_settings", "load_location_data")
def test_tag_swap() -> None:
    filename = "tag_swap.jpg"
    loc = dropbox.files.GpsCoordinates(latitude=48.8698583, longitude=2.3523166)
    output = fetch_processing_output(filename, location=loc)
    desired_output = fetch_desired_output(filename)
    assert_image_attrs_identical(output, desired_output)


@pytest.mark.usefixtures("load_settings")
def test_resize() -> None:
    filename = "resize.jpg"
    dimensions = dropbox.files.Dimensions(height=3024, width=4032)
    output = fetch_processing_output(filename, dimensions=dimensions)
    desired_output = fetch_desired_output(filename)
    assert_image_attrs_identical(output, desired_output)


@pytest.mark.usefixtures("load_settings", "load_location_data")
def test_resize_tag_location() -> None:
    filename = "resize, spot.jpg"
    dimensions = dropbox.files.Dimensions(height=3024, width=4032)
    loc = dropbox.files.GpsCoordinates(latitude=48.8662694, longitude=2.3242583)
    output = fetch_processing_output(filename, dimensions=dimensions, location=loc)
    desired_output = fetch_desired_output(filename)
    assert_image_attrs_identical(output, desired_output)


@pytest.mark.usefixtures("load_settings")
def test_add_date() -> None:
    filename = "date.jpeg"
    date = (
        dt.datetime.strptime("2018-05-14 16:10:09", "%Y-%m-%d %H:%M:%S")
        .replace(tzinfo=dt.timezone.utc)
        .astimezone(tz=pytz.timezone("Europe/Paris"))
    )
    output = fetch_processing_output(filename, date=date)
    desired_output = fetch_desired_output(filename)
    assert_image_attrs_identical(output, desired_output)


if face_recognition is not None:
    @pytest.mark.usefixtures("load_settings", "load_recognition_data")
    def test_recognition() -> None:
        filename = "recognition.jpg"
        output = fetch_processing_output(filename)
        desired_output = fetch_desired_output(filename)
        assert_image_attrs_identical(output, desired_output)
