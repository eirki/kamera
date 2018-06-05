#! /usr/bin/env python3.6
# coding: utf-8
from kamera.logger import log

import os
import datetime as dt
from pathlib import Path
from types import SimpleNamespace
import shutil

import dropbox
import pytest
import pytz

from kamera import config
from kamera import mediatypes
from kamera import task
import app

from typing import Optional, Dict


default_client_modified = dt.datetime(2000, 1, 1)


def make_all_temp_folders(root_dir: Path) -> None:
    os.mkdir(root_dir / "Uploads")
    os.mkdir(root_dir / "Review")
    os.mkdir(root_dir / "Backup")
    os.mkdir(root_dir / "Error")


def run_task_process_entry(
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
    entry = mediatypes.KameraEntry("test_account", dbx_entry, metadata=metadata)
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


@pytest.mark.parametrize('extension', config.video_extensions)
@pytest.mark.usefixtures("monkeypatch_mock_dropbox", "monkeypatch_redis_do_nothing", "data_from_img_processing")
def test_video(tmpdir, extension) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    run_task_process_entry(extension, root_dir)
    assert_file_moved_to_review_and_backup(extension, root_dir)
    assert_contents_unchanged(root_dir, "Review")
    assert_contents_unchanged(root_dir, "Backup")



@pytest.mark.parametrize('extension', config.image_extensions)
@pytest.mark.usefixtures("monkeypatch_mock_dropbox", "monkeypatch_redis_do_nothing", "data_from_img_processing")
def test_image_changed(tmpdir, extension) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    run_task_process_entry(extension, root_dir)
    assert_file_moved_to_review_and_backup(extension, root_dir)
    assert_contents_changed(root_dir, "Review")
    assert_contents_unchanged(root_dir, "Backup")


@pytest.mark.parametrize('extension', config.image_extensions)
@pytest.mark.usefixtures("monkeypatch_mock_dropbox", "monkeypatch_redis_do_nothing", "no_img_processing")
def test_image_unchanged(tmpdir, extension) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    run_task_process_entry(extension, root_dir)
    assert_file_moved_to_review_and_backup(extension, root_dir)
    assert_contents_unchanged(root_dir, "Review")
    assert_contents_unchanged(root_dir, "Backup")


@pytest.mark.parametrize('extension', config.media_extensions)
@pytest.mark.usefixtures("monkeypatch_mock_dropbox", "monkeypatch_redis_do_nothing", "data_from_img_processing", "error_parse_date")
def test_error(tmpdir, extension) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    run_task_process_entry(extension, root_dir)
    assert_file_moved_to_error(extension, root_dir)
    assert_contents_unchanged(root_dir, "Error")


@pytest.mark.usefixtures("monkeypatch_mock_dropbox", "monkeypatch_redis_do_nothing")
def test_unsupported_ext(tmpdir) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    run_task_process_entry(".ext", root_dir)
    assert_file_not_moved(".ext", root_dir)
    assert_contents_unchanged(root_dir, "Uploads")


@pytest.mark.usefixtures("monkeypatch_mock_dropbox", "monkeypatch_redis_do_nothing", "data_from_img_processing")
def test_client_modified_date_used(tmpdir, settings) -> None:
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
    run_task_process_entry(".jpg", root_dir)
    assert_file_moved_to_review_and_backup(".jpg", root_dir)
    assert_contents_changed(root_dir, "Review")
    assert_contents_unchanged(root_dir, "Backup")

    year_folder, month_folder, out_file = (root_dir / "Review").rglob("*")
    assert year_folder.name == str(client_modified_local.year)
    assert month_folder.name == settings.folder_names[client_modified_local.month]


@pytest.mark.usefixtures("monkeypatch_mock_dropbox", "monkeypatch_redis_do_nothing", "data_from_img_processing")
def test_time_taken_date_used(tmpdir, settings) -> None:
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
    run_task_process_entry(".jpg", root_dir, metadata)
    assert_file_moved_to_review_and_backup(".jpg", root_dir)
    assert_contents_changed(root_dir, "Review")
    assert_contents_unchanged(root_dir, "Backup")

    year_folder, month_folder, out_file = (root_dir / "Review").rglob("*")
    assert year_folder.name == str(in_date_local.year)
    assert month_folder.name == settings.folder_names[in_date_local.month]


@pytest.mark.usefixtures("monkeypatch_mock_dropbox", "monkeypatch_redis_do_nothing", "data_from_img_processing")
def test_time_taken_date_used_with_location(tmpdir, settings) -> None:
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
    run_task_process_entry(".jpg", root_dir, metadata)
    assert_file_moved_to_review_and_backup(".jpg", root_dir)
    assert_contents_changed(root_dir, "Review")
    assert_contents_unchanged(root_dir, "Backup")

    year_folder, month_folder, out_file = (root_dir / "Review").rglob("*")
    assert year_folder.name == str(in_date_local.year)
    assert month_folder.name == settings.folder_names[in_date_local.month]


@pytest.fixture()
def no_img_processing(monkeypatch):
    def no_img_processing_mock(*args, **kwargs):
        new_data = None
        return new_data
    monkeypatch.setattr('kamera.task.image_processing.main', no_img_processing_mock)


@pytest.fixture()
def data_from_img_processing(monkeypatch):
    def data_from_img_processing_mock(*args, **kwargs):
        new_data = b"new_file_content"
        return new_data
    monkeypatch.setattr('kamera.task.image_processing.main', data_from_img_processing_mock)


@pytest.fixture()
def error_parse_date(monkeypatch):
    def error_parse_date_mock(*args, **kwargs):
        raise Exception("This is an excpetion from mock parse_date")
    monkeypatch.setattr('kamera.task.parse_date', error_parse_date_mock)


class BadInputError(dropbox.exceptions.BadInputError):
    pass


class MockDropbox:
    def __init__(*args, **kwargs):
        pass

    def users_get_current_account(self):
        pass

    def files_download(self, path: Path):
        with open(path, "rb") as file:
            data = file.read()
        filemetadata = None
        response = SimpleNamespace(raw=SimpleNamespace(data=data))
        return filemetadata, response

    def files_upload(self, f: bytes, path: str, autorename: Optional[bool]=False):
        if not Path(path).parent.exists():
            raise BadInputError(request_id=1, message="message")
        with open(path, "wb") as file:
            file.write(f)

    def files_move(self, from_path: str, to_path: str, autorename: Optional[bool]=False) -> None:
        if not Path(from_path).parent.exists() or not Path(to_path).parent.exists():
            raise BadInputError(request_id=1, message="message")
        shutil.move(from_path, Path(to_path).parent)

    def files_copy(self, from_path: str, to_path: str, autorename: Optional[bool]=False) -> None:
        if not Path(from_path).parent.exists() or not Path(to_path).parent.exists():
            raise BadInputError(request_id=1, message="message")
        shutil.copy(from_path, Path(to_path).parent)

    def files_create_folder(self, path, autorename=False) -> None:
        os.makedirs(path)


@pytest.fixture()
def monkeypatch_mock_dropbox(monkeypatch):
    mock_module = SimpleNamespace(
        Dropbox=MockDropbox,
        exceptions=SimpleNamespace(BadInputError=BadInputError),
        files=SimpleNamespace(
            FileMetadata=dropbox.files.FileMetadata,
            PhotoMetadata=dropbox.files.PhotoMetadata,

        )
    )
    monkeypatch.setattr('kamera.task.dropbox', mock_module)


@pytest.fixture()
def settings():
    class MockSettings:
        def __init__(self):
            self.default_tz: str = "US/Eastern"
            self.folder_names: Dict[str, str] = {
                1: "January",
                2: "February",
                3: "March",
                4: "April",
                5: "May",
                6: "June",
                7: "July",
                8: "August",
                9: "September",
                10: "October",
                11: "November",
                12: "December"
              }
    return MockSettings()


@pytest.fixture()
def monkeypatch_redis_do_nothing(monkeypatch) -> None:
    class MockRedis:
        def hget(self, *args, **kwargs):
            return b""

        def hset(self, *args, **kwargs):
            pass

    def get_mocked_redis(*args, **kwargs):
        return MockRedis()
    monkeypatch.setattr('kamera.task.redis.from_url', get_mocked_redis)
