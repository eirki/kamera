#! /usr/bin/env python3.6
# coding: utf-8
from kamera.logger import log

import os
import datetime as dt
from pathlib import Path

import dropbox
import pytest
import pytz

from kamera import task
from kamera import mediatypes
from kamera import config

from typing import Optional


default_client_modified = dt.datetime(2000, 1, 1)


def make_all_temp_folders(root_dir: Path) -> None:
    os.mkdir(root_dir / "Uploads")
    os.mkdir(root_dir / "Review")
    os.mkdir(root_dir / "Backup")
    os.mkdir(root_dir / "Error")


def run_mocked_image_processing_main(
    ext: str,
    root_dir: Path,
    mock_cloud,
    metadata: Optional[dropbox.files.PhotoMetadata]=None
) -> None:
    in_file = root_dir / "Uploads" / f"in_file{ext}"
    with open(in_file, "w") as file:
        file.write("in_file_content")
    dbx_entry = dropbox.files.FileMetadata(
            path_display=in_file.as_posix(),
            client_modified=default_client_modified,
        )
    entry = mediatypes.KameraEntry(dbx_entry, metadata=metadata)
    task.process_entry(
        entry=entry,
        cloud=mock_cloud,
        out_dir=root_dir / "Review",
        backup_dir=root_dir / "Backup",
        error_dir=root_dir / "Error",
    )


def assert_file_not_moved(ext: str, root_dir: Path) -> None:
    assert (root_dir / "Uploads" / f"in_file{ext}").exists() is True
    assert len(list((root_dir / "Uploads").iterdir())) == 1
    assert len(list((root_dir / "Review").iterdir())) == 0
    assert len(list((root_dir / "Backup").iterdir())) == 0
    assert len(list((root_dir / "Error").iterdir())) == 0


def assert_file_moved_to_review_and_backup(ext: str, root_dir: Path) -> None:
    assert (root_dir / "Uploads" / f"in_file{ext}").exists() is False
    assert len(list((root_dir / "Uploads").iterdir())) == 0
    assert len(list((root_dir / "Review").iterdir())) == 1
    assert len(list((root_dir / "Backup").iterdir())) == 1
    assert len(list((root_dir / "Error").iterdir())) == 0


def assert_file_moved_to_error(ext: str, root_dir: Path) -> None:
    assert (root_dir / "Uploads" / f"in_file{ext}").exists() is False
    assert len(list((root_dir / "Uploads").iterdir())) == 0
    assert len(list((root_dir / "Review").iterdir())) == 0
    assert len(list((root_dir / "Backup").iterdir())) == 0
    assert len(list((root_dir / "Error").iterdir())) == 1


def assert_contents_changed(root_dir: Path, subfolder: str) -> None:
    out_file = list((root_dir / subfolder).iterdir())[0]
    with open(out_file) as file:
        out_contents = file.read()
    assert out_contents.endswith("new_file_content")


def assert_contents_unchanged(root_dir: Path, subfolder: str) -> None:
    out_file = list((root_dir / subfolder).iterdir())[0]
    with open(out_file) as file:
        out_contents = file.read()
    assert out_contents == "in_file_content"


@pytest.mark.usefixtures("load_settings", "data_from_img_processing")
def test_mp4(tmpdir, mock_cloud) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    run_mocked_image_processing_main(".mp4", root_dir, mock_cloud)
    assert_file_moved_to_review_and_backup(".mp4", root_dir)
    assert_contents_unchanged(root_dir, "Review")
    assert_contents_unchanged(root_dir, "Backup")


@pytest.mark.usefixtures("load_settings", "data_from_img_processing")
def test_gif(tmpdir, mock_cloud) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    run_mocked_image_processing_main(".gif", root_dir, mock_cloud)
    assert_file_moved_to_review_and_backup(".gif", root_dir)
    assert_contents_unchanged(root_dir, "Review")
    assert_contents_unchanged(root_dir, "Backup")


@pytest.mark.usefixtures("load_settings", "data_from_img_processing")
def test_mov(tmpdir, mock_cloud) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    run_mocked_image_processing_main(".mov", root_dir, mock_cloud)
    assert_file_moved_to_review_and_backup(".mov", root_dir)
    assert_contents_unchanged(root_dir, "Review")
    assert_contents_unchanged(root_dir, "Backup")


@pytest.mark.usefixtures("load_settings", "data_from_img_processing")
def test_png_changed(tmpdir, mock_cloud) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    run_mocked_image_processing_main(".png", root_dir, mock_cloud)
    assert_file_moved_to_review_and_backup(".png", root_dir)
    assert_contents_changed(root_dir, "Review")
    assert_contents_unchanged(root_dir, "Backup")


@pytest.mark.usefixtures("load_settings", "no_img_processing")
def test_png_unchanged(tmpdir, mock_cloud) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    run_mocked_image_processing_main(".png", root_dir, mock_cloud)
    assert_file_moved_to_review_and_backup(".png", root_dir)
    assert_contents_unchanged(root_dir, "Review")
    assert_contents_unchanged(root_dir, "Backup")


@pytest.mark.usefixtures("load_settings", "no_img_processing")
def test_jpeg_unchanged(tmpdir, mock_cloud) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    run_mocked_image_processing_main(".jpeg", root_dir, mock_cloud)
    assert_file_moved_to_review_and_backup(".jpeg", root_dir)
    assert_contents_unchanged(root_dir, "Review")
    assert_contents_unchanged(root_dir, "Backup")


@pytest.mark.usefixtures("load_settings", "no_img_processing")
def test_jpg_unchanged(tmpdir, mock_cloud) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    run_mocked_image_processing_main(".jpg", root_dir, mock_cloud)
    assert_file_moved_to_review_and_backup(".jpg", root_dir)
    assert_contents_unchanged(root_dir, "Review")
    assert_contents_unchanged(root_dir, "Backup")


@pytest.mark.usefixtures("load_settings", "data_from_img_processing")
def test_jpg_changed(tmpdir, mock_cloud) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    run_mocked_image_processing_main(".jpg", root_dir, mock_cloud)
    assert_file_moved_to_review_and_backup(".jpg", root_dir)
    assert_contents_changed(root_dir, "Review")
    assert_contents_unchanged(root_dir, "Backup")


@pytest.mark.usefixtures("load_settings", "error_img_processing")
def test_jpg_error(tmpdir, mock_cloud) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    run_mocked_image_processing_main(".jpg", root_dir, mock_cloud)
    assert_file_moved_to_error(".jpg", root_dir)
    assert_contents_unchanged(root_dir, "Error")


@pytest.mark.usefixtures("load_settings")
def test_unsupported_ext(tmpdir, mock_cloud) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    run_mocked_image_processing_main(".ext", root_dir, mock_cloud)
    assert_file_not_moved(".ext", root_dir)
    assert_contents_unchanged(root_dir, "Uploads")


@pytest.mark.usefixtures("load_settings", "data_from_img_processing")
def test_client_modified_date_used(tmpdir, mock_cloud) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    client_modified_utc = default_client_modified.replace(tzinfo=dt.timezone.utc)
    client_modified_local = (
        client_modified_utc.astimezone(
            tz=pytz.timezone(config.settings["default_tz"])
        )
    )
    run_mocked_image_processing_main(".jpg", root_dir, mock_cloud)
    assert_file_moved_to_review_and_backup(".jpg", root_dir)
    assert_contents_changed(root_dir, "Review")
    assert_contents_unchanged(root_dir, "Backup")
    out_file = root_dir / "Review" / "in_file.jpg"
    with open(out_file) as file:
        out_contents = file.read()
    date_str, timezone, contents_str = out_contents.split()
    out_date = (
        dt.datetime
        .strptime(date_str, "%Y-%m-%d_%H:%M:%S")
        .replace(tzinfo=pytz.timezone(timezone))
    )
    assert client_modified_local == out_date


@pytest.mark.usefixtures("load_settings", "data_from_img_processing")
def test_time_taken_date_used(tmpdir, mock_cloud) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    in_date_naive = dt.datetime(2010, 1, 1, 12, 0)
    in_date_utc = in_date_naive.replace(tzinfo=dt.timezone.utc)
    in_date_local = in_date_utc.astimezone(tz=pytz.timezone(config.settings["default_tz"]))
    metadata = dropbox.files.PhotoMetadata(
        dimensions=None,
        location=None,
        time_taken=in_date_naive
    )
    run_mocked_image_processing_main(".jpg", root_dir, mock_cloud, metadata)
    assert_file_moved_to_review_and_backup(".jpg", root_dir)
    assert_contents_changed(root_dir, "Review")
    assert_contents_unchanged(root_dir, "Backup")
    out_file = root_dir / "Review" / "in_file.jpg"
    with open(out_file) as file:
        out_contents = file.read()
    date_str, timezone, contents_str = out_contents.split()
    out_date = (
        dt.datetime
        .strptime(date_str, "%Y-%m-%d_%H:%M:%S")
        .replace(tzinfo=pytz.timezone(timezone))
    )
    assert in_date_local == out_date


@pytest.mark.usefixtures("load_settings", "data_from_img_processing")
def test_time_taken_date_used_with_location(tmpdir, mock_cloud) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    in_date_naive = dt.datetime(2010, 1, 1, 12, 00)
    in_date_utc = in_date_naive.replace(tzinfo=dt.timezone.utc)
    in_date_local = in_date_utc.astimezone(tz=pytz.timezone(config.settings["default_tz"]))
    in_date_local_str = in_date_local.strftime("%Y-%m-%d_%H:%M:%S")
    metadata = dropbox.files.PhotoMetadata(
        dimensions=None,
        location=dropbox.files.GpsCoordinates(latitude=48.8662694, longitude=2.3242583),
        time_taken=in_date_naive
    )
    run_mocked_image_processing_main(".jpg", root_dir, mock_cloud, metadata)
    assert_file_moved_to_review_and_backup(".jpg", root_dir)
    assert_contents_changed(root_dir, "Review")
    assert_contents_unchanged(root_dir, "Backup")
    out_file = root_dir / "Review" / "in_file.jpg"
    with open(out_file) as file:
        out_contents = file.read()
    out_date_str, timezone, contents_str = out_contents.split()
    out_date = (
        dt.datetime
        .strptime(out_date_str, "%Y-%m-%d_%H:%M:%S")
        .replace(tzinfo=pytz.timezone(timezone))
    )
    assert in_date_local == out_date
    assert in_date_local.tzinfo != out_date.tzinfo
    assert in_date_local_str != out_date_str
