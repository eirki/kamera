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
        out_dir=root_dir / "Review",
        backup_dir=root_dir / "Backup",
        error_dir=root_dir / "Error",
    )


def _get_folder_contents(root_dir: Path):
    uploads_contents = list((root_dir / "Uploads").rglob("*"))
    review_contents = list((root_dir / "Review").rglob("*"))
    backup_contents = list((root_dir / "Backup").rglob("*"))
    error_contents = list((root_dir / "Error").rglob("*"))
    return uploads_contents, review_contents, backup_contents, error_contents


def assert_file_not_moved(ext: str, root_dir: Path) -> None:
    assert (root_dir / "Uploads").glob(f"*in_file{ext}") != []
    uploads_contents, review_contents, backup_contents, error_contents = _get_folder_contents(root_dir)
    assert len(uploads_contents) == 1
    assert review_contents == []
    assert backup_contents == []
    assert error_contents == []


def assert_file_moved_to_review_and_backup(ext: str, root_dir: Path) -> None:
    assert (root_dir / "Uploads").glob(f"*in_file{ext}") != []
    uploads_contents, review_contents, backup_contents, error_contents = _get_folder_contents(root_dir)
    assert uploads_contents == []
    assert len(review_contents) == 3
    assert len(backup_contents) == 3
    assert error_contents == []


def assert_file_moved_to_error(ext: str, root_dir: Path) -> None:
    assert (root_dir / "Uploads").glob(f"*in_file{ext}") != []
    uploads_contents, review_contents, backup_contents, error_contents = _get_folder_contents(root_dir)
    assert uploads_contents == []
    assert review_contents == []
    assert backup_contents == []
    assert len(error_contents) == 1


def assert_contents_changed(root_dir: Path, subfolder: str) -> None:
    out_file = list((root_dir / subfolder).rglob("*"))[-1]
    with open(out_file) as file:
        out_contents = file.read()
    assert out_contents.endswith("new_file_content")


def assert_contents_unchanged(root_dir: Path, subfolder: str) -> None:
    out_file = list((root_dir / subfolder).rglob("*"))[-1]
    with open(out_file) as file:
        out_contents = file.read()
    assert out_contents == "in_file_content"


@pytest.mark.usefixtures("load_settings", "data_from_img_processing")
def test_mp4(tmpdir) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    run_mocked_image_processing_main(".mp4", root_dir)
    assert_file_moved_to_review_and_backup(".mp4", root_dir)
    assert_contents_unchanged(root_dir, "Review")
    assert_contents_unchanged(root_dir, "Backup")


@pytest.mark.usefixtures("load_settings", "data_from_img_processing")
def test_gif(tmpdir) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    run_mocked_image_processing_main(".gif", root_dir)
    assert_file_moved_to_review_and_backup(".gif", root_dir)
    assert_contents_unchanged(root_dir, "Review")
    assert_contents_unchanged(root_dir, "Backup")


@pytest.mark.usefixtures("load_settings", "data_from_img_processing")
def test_mov(tmpdir) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    run_mocked_image_processing_main(".mov", root_dir)
    assert_file_moved_to_review_and_backup(".mov", root_dir)
    assert_contents_unchanged(root_dir, "Review")
    assert_contents_unchanged(root_dir, "Backup")


@pytest.mark.usefixtures("load_settings", "data_from_img_processing")
def test_png_changed(tmpdir) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    run_mocked_image_processing_main(".png", root_dir)
    assert_file_moved_to_review_and_backup(".png", root_dir)
    assert_contents_changed(root_dir, "Review")
    assert_contents_unchanged(root_dir, "Backup")


@pytest.mark.usefixtures("load_settings", "no_img_processing")
def test_png_unchanged(tmpdir) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    run_mocked_image_processing_main(".png", root_dir)
    assert_file_moved_to_review_and_backup(".png", root_dir)
    assert_contents_unchanged(root_dir, "Review")
    assert_contents_unchanged(root_dir, "Backup")


@pytest.mark.usefixtures("load_settings", "no_img_processing")
def test_jpeg_unchanged(tmpdir) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    run_mocked_image_processing_main(".jpeg", root_dir)
    assert_file_moved_to_review_and_backup(".jpeg", root_dir)
    assert_contents_unchanged(root_dir, "Review")
    assert_contents_unchanged(root_dir, "Backup")


@pytest.mark.usefixtures("load_settings", "no_img_processing")
def test_jpg_unchanged(tmpdir) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    run_mocked_image_processing_main(".jpg", root_dir)
    assert_file_moved_to_review_and_backup(".jpg", root_dir)
    assert_contents_unchanged(root_dir, "Review")
    assert_contents_unchanged(root_dir, "Backup")


@pytest.mark.usefixtures("load_settings", "data_from_img_processing")
def test_jpg_changed(tmpdir) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    run_mocked_image_processing_main(".jpg", root_dir)
    assert_file_moved_to_review_and_backup(".jpg", root_dir)
    assert_contents_changed(root_dir, "Review")
    assert_contents_unchanged(root_dir, "Backup")


@pytest.mark.usefixtures("load_settings", "error_img_processing")
def test_jpg_error(tmpdir) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    run_mocked_image_processing_main(".jpg", root_dir)
    assert_file_moved_to_error(".jpg", root_dir)
    assert_contents_unchanged(root_dir, "Error")


@pytest.mark.usefixtures("load_settings")
def test_unsupported_ext(tmpdir) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    run_mocked_image_processing_main(".ext", root_dir)
    assert_file_not_moved(".ext", root_dir)
    assert_contents_unchanged(root_dir, "Uploads")


@pytest.mark.usefixtures("load_settings", "data_from_img_processing")
def test_client_modified_date_used(tmpdir) -> None:
    """datetime sent to image_processing (default_client_modified) is timezone-naive 01.01.2000 00:00
    this should be assumed to be utc. tests default timezone is "US/Eastern" (utc-05:00).
    client_modified_local should be 12.31.1999 19:00, folders created should be 1999 and 12
     """
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    client_modified_utc = default_client_modified.replace(tzinfo=dt.timezone.utc)
    client_modified_local = (
        client_modified_utc.astimezone(
            tz=pytz.timezone("US/Eastern")
        )
    )
    run_mocked_image_processing_main(".jpg", root_dir)
    assert_file_moved_to_review_and_backup(".jpg", root_dir)
    assert_contents_changed(root_dir, "Review")
    assert_contents_unchanged(root_dir, "Backup")

    year_folder, month_folder, out_file = (root_dir / "Review").rglob("*")
    assert year_folder.name == str(client_modified_local.year)
    assert month_folder.name == config.settings["folder_names"][client_modified_local.month]


@pytest.mark.usefixtures("load_settings", "data_from_img_processing")
def test_time_taken_date_used(tmpdir) -> None:
    """datetime sent to image_processing (in_date_naive) is timezone-naive 01.01.2010 00:00
    this should be assumed to be utc. tests default timezone is "US/Eastern" (utc-05:00).
    client_modified_local should be 12.31.2009 19:00, folders created should be 2009 and 12
     """
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    in_date_naive = dt.datetime(2010, 1, 1, 0, 0)
    in_date_utc = in_date_naive.replace(tzinfo=dt.timezone.utc)
    in_date_local = in_date_utc.astimezone(tz=pytz.timezone("US/Eastern"))
    metadata = dropbox.files.PhotoMetadata(
        dimensions=None,
        location=None,
        time_taken=in_date_naive
    )
    run_mocked_image_processing_main(".jpg", root_dir, metadata)
    assert_file_moved_to_review_and_backup(".jpg", root_dir)
    assert_contents_changed(root_dir, "Review")
    assert_contents_unchanged(root_dir, "Backup")

    year_folder, month_folder, out_file = (root_dir / "Review").rglob("*")
    assert year_folder.name == str(in_date_local.year)
    assert month_folder.name == config.settings["folder_names"][in_date_local.month]


@pytest.mark.usefixtures("load_settings", "data_from_img_processing")
def test_time_taken_date_used_with_location(tmpdir) -> None:
    """datetime sent to image_processing (in_date_naive) is timezone-naive 12.31.2014 23:00,
    with gps location in timezone "Europe/Paris"
    time_taken should be assumed to be utc. tests default timezone is "US/Eastern" (utc-05:00).
    in_date_local should be 01.01.2015 00:00, folders created should be 2015 and 01
     """

    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    in_date_naive = dt.datetime(2014, 12, 31, 23, 0)
    in_date_utc = in_date_naive.replace(tzinfo=dt.timezone.utc)
    in_date_local = in_date_utc.astimezone(tz=pytz.timezone("Europe/Paris"))
    metadata = dropbox.files.PhotoMetadata(
        dimensions=None,
        location=dropbox.files.GpsCoordinates(latitude=48.8662694, longitude=2.3242583),
        time_taken=in_date_naive
    )
    run_mocked_image_processing_main(".jpg", root_dir, metadata)
    assert_file_moved_to_review_and_backup(".jpg", root_dir)
    assert_contents_changed(root_dir, "Review")
    assert_contents_unchanged(root_dir, "Backup")

    year_folder, month_folder, out_file = (root_dir / "Review").rglob("*")
    assert year_folder.name == str(in_date_local.year)
    assert month_folder.name == config.settings["folder_names"][in_date_local.month]