#! /usr/bin/env python3.6
# coding: utf-8
import datetime as dt
import json
import subprocess
import sys
import typing as t
from io import BytesIO
from pathlib import Path

import dropbox
import piexif
import pytest
import pytz
from numpy import array as np_array
from PIL import Image

from kamera import config, image_processing

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


def _get_dimensions(data: bytes) -> t.Tuple[int, int]:
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


def run_image_processing_main(
    filename: str,
    settings: config.Settings,
    dimensions: t.Optional[dropbox.files.Dimensions] = None,
    coordinates: t.Optional[dropbox.files.GpsCoordinates] = None,
    date: t.Optional[dt.datetime] = None,
) -> bytes:
    filepath_input = test_images_path / "input" / filename
    with open(filepath_input, "rb") as file:
        input_data = file.read()

    if date is None:
        date = dt.datetime(2000, 1, 1)

    output_data = image_processing.main(
        data=input_data,
        filepath=test_images_path / "input" / filename,
        settings=settings,
        dimensions=dimensions,
        coordinates=coordinates,
        date=date,
    )
    if output_data is None:
        raise Exception("No output from image_processing")
    return output_data


def fetch_desired_output(filename: str) -> bytes:
    filepath_desired_output = test_images_path / "desired_output" / filename
    with open(filepath_desired_output, "rb") as file:
        desired_output = file.read()
    return desired_output


def test_tag_spot(settings) -> None:
    filename = "spot.jpg"
    coordinates = dropbox.files.GpsCoordinates(
        latitude=48.866_269_4, longitude=2.324_258_3
    )
    output = run_image_processing_main(filename, settings, coordinates=coordinates)
    desired_output = fetch_desired_output(filename)
    assert_image_attrs_identical(output, desired_output)


def test_tag_area(settings) -> None:
    filename = "area.jpg"
    coordinates = dropbox.files.GpsCoordinates(
        latitude=48.871_519_4, longitude=2.337_244_4
    )
    output = run_image_processing_main(filename, settings, coordinates=coordinates)
    desired_output = fetch_desired_output(filename)
    assert_image_attrs_identical(output, desired_output)


def test_png(settings) -> None:
    filename = "filetype.png"
    date = (
        dt.datetime.strptime("2018-05-14 16:07:59", "%Y-%m-%d %H:%M:%S")
        .replace(tzinfo=dt.timezone.utc)
        .astimezone(tz=pytz.timezone("Europe/Paris"))
    )
    output = run_image_processing_main(filename, settings, date=date)
    desired_output = fetch_desired_output("filetype.jpg")
    assert_image_attrs_identical(output, desired_output)


def test_tag_swap(settings) -> None:
    filename = "tag_swap.jpg"
    coordinates = dropbox.files.GpsCoordinates(
        latitude=48.869_858_3, longitude=2.352_316_6
    )
    output = run_image_processing_main(filename, settings, coordinates=coordinates)
    desired_output = fetch_desired_output(filename)
    assert_image_attrs_identical(output, desired_output)


def test_resize(settings) -> None:
    filename = "resize.jpg"
    dimensions = dropbox.files.Dimensions(height=3024, width=4032)
    output = run_image_processing_main(filename, settings, dimensions=dimensions)
    desired_output = fetch_desired_output(filename)
    assert_image_attrs_identical(output, desired_output)


def test_resize_tag_coordinates(settings) -> None:
    filename = "resize, spot.jpg"
    dimensions = dropbox.files.Dimensions(height=3024, width=4032)
    coordinates = dropbox.files.GpsCoordinates(
        latitude=48.866_269_4, longitude=2.324_258_3
    )
    output = run_image_processing_main(
        filename, settings, dimensions=dimensions, coordinates=coordinates
    )
    desired_output = fetch_desired_output(filename)
    assert_image_attrs_identical(output, desired_output)


def test_add_date(settings) -> None:
    filename = "date.jpeg"
    date = (
        dt.datetime.strptime("2018-05-14 16:10:09", "%Y-%m-%d %H:%M:%S")
        .replace(tzinfo=dt.timezone.utc)
        .astimezone(tz=pytz.timezone("Europe/Paris"))
    )
    output = run_image_processing_main(filename, settings, date=date)
    desired_output = fetch_desired_output(filename)
    assert_image_attrs_identical(output, desired_output)


def test_scenetype_workaround(settings) -> None:
    filename = "scenetype.jpg"
    dimensions = dropbox.files.Dimensions(height=3456, width=4608)
    run_image_processing_main(filename, settings, dimensions=dimensions)


def test_recognition(settings) -> None:
    filename = "recognition.jpg"
    output = run_image_processing_main(filename, settings)
    desired_output = fetch_desired_output(filename)
    assert_image_attrs_identical(output, desired_output)


@pytest.fixture()
def settings():
    class MockSettings:
        def __init__(self):
            self.default_tz: str = "US/Eastern"
            self.recognition_tolerance: float = 0.4
            self.tag_swaps: t.Dict[str, str] = {
                "Paris/10e arrondissement": "Holiday/France"
            }
            self.locations = [
                config.Area(
                    name="Paris",
                    lat=48.8566,
                    lng=2.3522,
                    spots=[
                        config.Spot(
                            name="Place de la Concorde", lat=48.8662, lng=2.3242
                        ),
                        config.Spot(name="10e arrondissement", lat=48.8698, lng=2.3523),
                    ],
                )
            ]
            with open(test_images_path / "encodings" / "biden.json") as j:
                biden = json.load(j)
            with open(test_images_path / "encodings" / "obama1.json") as j:
                obama1 = json.load(j)
            with open(test_images_path / "encodings" / "obama2.json") as j:
                obama2 = json.load(j)
            self.recognition_data: t.Dict[str, t.List[np_array]] = {
                "Biden": [np_array(biden)],
                "Obama": [np_array(obama1), np_array(obama2)],
            }

    return MockSettings()
