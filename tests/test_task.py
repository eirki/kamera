#! /usr/bin/env python3.6
# coding: utf-8
from kamera.logger import log

import os
import datetime as dt
from pathlib import Path

import dropbox
import pytest

from kamera import task
from kamera import mediatypes

from typing import Tuple


def make_all_temp_folders(root_dir: Path) -> None:
    os.mkdir(root_dir / "Uploads")  # in_dir
    os.mkdir(root_dir / "Review")  # out_dir
    os.mkdir(root_dir / "Backup")  # backup_dir
    os.mkdir(root_dir / "Error")  # error_dir


def run_mocked_image_processing_main(ext: str, root_dir: Path) -> None:
    in_file = root_dir / "Uploads" / f"in_file{ext}"
    with open(in_file, "w") as file:
        file.write("in_file_content")
    dbx_entry = dropbox.files.FileMetadata(
            path_display=in_file.as_posix(),
            client_modified=dt.datetime.utcnow(),
        )
    entry = mediatypes.KameraEntry(dbx_entry, metadata=None)
    task.process_entry(
        entry=entry,
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
    assert out_contents == "new_file_content"


def assert_contents_unchanged(root_dir: Path, subfolder: str) -> None:
    out_file = list((root_dir / subfolder).iterdir())[0]
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
