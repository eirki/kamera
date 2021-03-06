#! /usr/bin/env python3
# coding: utf-8
import datetime as dt
import os
import typing as t
from collections import defaultdict
from io import BytesIO
from pathlib import Path

import dropbox
import fakeredis
import pytest
import pytz
from PIL import Image

from kamera import config
from kamera.task import Task
from tests.mock_dropbox import MockDropbox

default_client_modified = dt.datetime(2000, 1, 1, 10, 30)
date_fmt = "%Y-%m-%d %H.%M.%S"


redis_servers: t.Dict[str, fakeredis.FakeServer] = defaultdict(fakeredis.FakeServer)


def make_image(
    changed: bool, dimensions: t.Optional[dropbox.files.Dimensions] = None
) -> bytes:
    dimensions = (
        (dimensions.width, dimensions.height) if dimensions is not None else (100, 100)
    )
    new_data = BytesIO()
    image = Image.new("RGB", size=dimensions, color=1 if changed else 2)
    image.save(new_data, "JPEG")
    data = new_data.getvalue()
    return data


def make_all_temp_folders(root_dir: Path) -> None:
    os.mkdir(root_dir / "Uploads")
    os.mkdir(root_dir / "Review")
    os.mkdir(root_dir / "Backup")
    os.mkdir(root_dir / "Error")


def run_task_process_entry(
    test_name: str,
    ext: str,
    root_dir: Path,
    file_name: t.Optional[str] = None,
    metadata: t.Optional[dropbox.files.PhotoMetadata] = None,
) -> None:
    account_id = test_name
    stem = test_name if file_name is None else file_name
    in_file = root_dir / "Uploads" / f"{stem}{ext}"
    image = make_image(
        changed=False, dimensions=metadata.dimensions if metadata else None
    )
    with open(in_file, "wb") as file:
        file.write(image)
    dbx_entry = dropbox.files.FileMetadata(
        path_display=in_file.as_posix(), client_modified=default_client_modified
    )
    task = Task(
        account_id=account_id,
        entry=dbx_entry,
        review_dir=root_dir / "Review",
        backup_dir=root_dir / "Backup",
        error_dir=root_dir / "Error",
    )
    redis_state = redis_servers[test_name]
    fake_redis_client = fakeredis.FakeStrictRedis(server=redis_state)
    fake_dbx = MockDropbox(in_file=in_file, metadata=metadata)
    fake_settings = MockSettings(account_id)
    task.process_entry(
        redis_client=fake_redis_client, dbx=fake_dbx, settings=fake_settings
    )


def _get_folder_contents(root_dir: Path):
    uploads = list((root_dir / "Uploads").rglob("*"))
    review = list((root_dir / "Review").rglob("*"))
    backup = list((root_dir / "Backup").rglob("*"))
    error = list((root_dir / "Error").rglob("*"))
    return uploads, review, backup, error


def assert_file_not_moved(root_dir: Path) -> None:
    uploads, review, backup, error = _get_folder_contents(root_dir)
    assert error == [], "No error during processing"
    assert len(uploads) == 1
    assert review == []
    assert backup == []


def assert_file_moved_to_review_and_backup(root_dir: Path) -> None:
    uploads, review, backup, error = _get_folder_contents(root_dir)
    assert error == [], "No error during processing"
    assert uploads == []
    assert len(review) == 3
    assert len(backup) == 3


def assert_file_moved_to_error(root_dir: Path) -> None:
    uploads, review, backup, error = _get_folder_contents(root_dir)
    assert len(error) == 1
    assert uploads == []
    assert review == []
    assert backup == []


def assert_contents_changed(root_dir: Path, subfolder: str) -> None:
    out_file = list((root_dir / subfolder).rglob("*"))[-1]
    with open(out_file, "rb") as file:
        image = file.read()
    assert image == make_image(changed=True)


def assert_contents_unchanged(root_dir: Path, subfolder: str) -> None:
    out_file = list((root_dir / subfolder).rglob("*"))[-1]
    with open(out_file, "rb") as file:
        image = file.read()
    assert image == make_image(changed=False)


@pytest.mark.parametrize("extension", config.video_extensions)
@pytest.mark.parametrize("process_img", [True, False])
def test_video(tmpdir, extension, monkeypatch, process_img) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    monkeypatch_img_processing(monkeypatch, return_new_data=process_img)
    run_task_process_entry(
        test_name=f"test_video{extension}{process_img}",
        ext=extension,
        root_dir=root_dir,
    )
    assert_file_moved_to_review_and_backup(root_dir)
    assert_contents_unchanged(root_dir, "Review")
    assert_contents_unchanged(root_dir, "Backup")


@pytest.mark.parametrize("extension", config.image_extensions)
def test_image_changed(tmpdir, extension, monkeypatch) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    monkeypatch_img_processing(monkeypatch, return_new_data=True)
    run_task_process_entry(
        test_name=f"test_image_changed{extension}", ext=extension, root_dir=root_dir
    )
    assert_file_moved_to_review_and_backup(root_dir)
    assert_contents_changed(root_dir, "Review")
    assert_contents_unchanged(root_dir, "Backup")


@pytest.mark.parametrize("extension", config.image_extensions)
def test_image_unchanged(tmpdir, extension, monkeypatch) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    monkeypatch_img_processing(monkeypatch, return_new_data=False)
    run_task_process_entry(
        test_name=f"test_image_unchanged{extension}", ext=extension, root_dir=root_dir
    )
    assert_file_moved_to_review_and_backup(root_dir)
    assert_contents_unchanged(root_dir, "Review")
    assert_contents_unchanged(root_dir, "Backup")


@pytest.mark.parametrize("extension", config.media_extensions)
@pytest.mark.parametrize("process_img", [True, False])
@pytest.mark.usefixtures("error_parse_date")
def test_error(tmpdir, extension, monkeypatch, process_img) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    monkeypatch_img_processing(monkeypatch, return_new_data=process_img)
    run_task_process_entry(
        test_name=f"test_error{extension}{process_img}",
        ext=extension,
        root_dir=root_dir,
    )
    assert_file_moved_to_error(root_dir)
    assert_contents_unchanged(root_dir, "Error")


@pytest.mark.parametrize("process_img", [True, False])
def test_unsupported_ext(tmpdir, monkeypatch, process_img) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    monkeypatch_img_processing(monkeypatch, return_new_data=process_img)
    run_task_process_entry(
        test_name=f"test_unsupported_ext{process_img}", ext=".ext", root_dir=root_dir
    )
    assert_file_not_moved(root_dir)
    assert_contents_unchanged(root_dir, "Uploads")


@pytest.mark.parametrize("extension", config.media_extensions)
@pytest.mark.parametrize("process_img", [True, False])
def test_client_modified_date_used(
    tmpdir, settings, extension, monkeypatch, process_img
) -> None:
    """datetime sent to image_processing (default_client_modified)
    is timezone-naive 01.01.2000 00:00. this should be assumed to be utc.
    tests default timezone is "US/Eastern" (utc-05:00).
    client_modified_local should be 12.31.1999 19:00,
    folders created should be 1999 and 12
     """
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    monkeypatch_img_processing(monkeypatch, return_new_data=process_img)
    test_name = f"test_client_modified_date_used{extension}{process_img}"
    client_modified_utc = default_client_modified.replace(tzinfo=dt.timezone.utc)
    client_modified_local = client_modified_utc.astimezone(
        tz=pytz.timezone("US/Eastern")
    )
    run_task_process_entry(test_name=test_name, ext=extension, root_dir=root_dir)
    assert_file_moved_to_review_and_backup(root_dir)

    year_folder, month_folder, out_file = (root_dir / "Review").rglob("*")
    assert year_folder.name == str(client_modified_local.year)
    assert month_folder.name == settings.folder_names[client_modified_local.month]
    date_str = client_modified_local.strftime(date_fmt)
    assert out_file.stem.startswith(date_str)
    assert out_file.stem.endswith(test_name)


@pytest.mark.parametrize("extension", config.media_extensions)
@pytest.mark.parametrize("process_img", [True, False])
def test_time_taken_date_used(
    tmpdir, settings, extension, monkeypatch, process_img
) -> None:
    """datetime sent to image_processing (in_date_naive) is
    timezone-naive 01.01.2010 00:00. this should be assumed to be utc.
    tests default timezone is "US/Eastern" (utc-05:00).
    client_modified_local should be 12.31.2009 19:00,
    folders created should be 2009 and 12
     """
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    monkeypatch_img_processing(monkeypatch, return_new_data=process_img)
    test_name = f"test_time_taken_date_used{extension}{process_img}"
    in_date_naive = dt.datetime(2010, 1, 1, 0, 0)
    in_date_utc = in_date_naive.replace(tzinfo=dt.timezone.utc)
    in_date_local = in_date_utc.astimezone(tz=pytz.timezone("US/Eastern"))
    metadata = dropbox.files.PhotoMetadata(
        dimensions=None, location=None, time_taken=in_date_naive
    )
    run_task_process_entry(
        test_name=test_name, ext=extension, root_dir=root_dir, metadata=metadata
    )
    assert_file_moved_to_review_and_backup(root_dir)

    year_folder, month_folder, out_file = (root_dir / "Review").rglob("*")
    assert year_folder.name == str(in_date_local.year)
    assert month_folder.name == settings.folder_names[in_date_local.month]
    date_str = in_date_local.strftime(date_fmt)
    assert out_file.stem.startswith(date_str)
    assert out_file.stem.endswith(test_name)


@pytest.mark.parametrize("extension", config.media_extensions)
@pytest.mark.parametrize("process_img", [True, False])
def test_time_taken_date_used_with_location(
    tmpdir, settings, extension, monkeypatch, process_img
) -> None:
    """datetime sent to image_processing (in_date_naive) is
    timezone-naive 12.31.2014 23:00, with gps location in timezone "Europe/Paris"
    time_taken should be assumed to be utc. tests default timezone
    is "US/Eastern" (utc-05:00).
    in_date_local should be 01.01.2015 00:00, folders created should be 2015 and 01
     """
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    monkeypatch_img_processing(monkeypatch, return_new_data=process_img)
    test_name = f"test_time_taken_date_used_with_location{extension}{process_img}"
    in_date_naive = dt.datetime(2014, 12, 31, 23, 0)
    in_date_utc = in_date_naive.replace(tzinfo=dt.timezone.utc)
    in_date_local = in_date_utc.astimezone(tz=pytz.timezone("Europe/Paris"))
    metadata = dropbox.files.PhotoMetadata(
        dimensions=None,
        location=dropbox.files.GpsCoordinates(
            latitude=48.866_269_4, longitude=2.324_258_3
        ),
        time_taken=in_date_naive,
    )
    run_task_process_entry(
        test_name=test_name, ext=extension, root_dir=root_dir, metadata=metadata
    )
    assert_file_moved_to_review_and_backup(root_dir)

    year_folder, month_folder, out_file = (root_dir / "Review").rglob("*")
    assert year_folder.name == str(in_date_local.year)
    assert month_folder.name == settings.folder_names[in_date_local.month]
    date_str = in_date_local.strftime(date_fmt)
    assert out_file.stem.startswith(date_str)
    assert out_file.stem.endswith(test_name)


@pytest.mark.parametrize("process_img", [True, False])
@pytest.mark.parametrize("prefix", ["IMG", "VID"])
def test_date_moved_to_filename_start(
    tmpdir, settings, monkeypatch, process_img, prefix
) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    monkeypatch_img_processing(monkeypatch, return_new_data=process_img)
    client_modified_utc = default_client_modified.replace(tzinfo=dt.timezone.utc)
    client_modified_local = client_modified_utc.astimezone(
        tz=pytz.timezone("US/Eastern")
    )
    date_str_in = client_modified_local.strftime("%Y%m%d_%H%M%S")
    date_str_out = client_modified_local.strftime(date_fmt)
    run_task_process_entry(
        test_name=f"test_date_moved_to_filename_start{process_img}{prefix}",
        ext=".jpg",
        root_dir=root_dir,
        file_name=f"{prefix}_{date_str_in}",
    )
    assert_file_moved_to_review_and_backup(root_dir)

    _, _, out_file = (root_dir / "Review").rglob("*")
    assert out_file.stem == f"{date_str_out} {prefix}"


def test_settings_caching(tmpdir, settings, monkeypatch) -> None:
    monkeypatch.setattr("kamera.task.config.Settings", MockSettings)
    account_id = "test_settings_caching"
    fake_redis_client = fakeredis.FakeStrictRedis()
    fake_redis_client.hset(f"user:{account_id}", "token", "token")
    root_dir = Path(tmpdir)
    in_file1 = root_dir / "Uploads" / "in_file1.jpg"
    dbx_entry1 = dropbox.files.FileMetadata(
        path_display=in_file1.as_posix(), client_modified=default_client_modified
    )
    task1 = Task(
        account_id=account_id,
        entry=dbx_entry1,
        review_dir=root_dir / "Review",
        backup_dir=root_dir / "Backup",
        error_dir=root_dir / "Error",
    )

    assert account_id not in Task.dbx_cache
    assert account_id not in Task.settings_cache

    dbx1 = Task.load_dbx_from_cache(task1.account_id, fake_redis_client)
    settings1 = task1.load_settings_from_cache(task1.account_id, dbx1)

    assert account_id in Task.dbx_cache
    assert account_id in Task.settings_cache

    in_file2 = root_dir / "Uploads" / "in_file2.jpg"
    dbx_entry2 = dropbox.files.FileMetadata(
        path_display=in_file2.as_posix(), client_modified=default_client_modified
    )
    task2 = Task(
        account_id=account_id,
        entry=dbx_entry2,
        review_dir=root_dir / "Review",
        backup_dir=root_dir / "Backup",
        error_dir=root_dir / "Error",
    )
    dbx2 = Task.load_dbx_from_cache(task2.account_id, fake_redis_client)
    settings2 = task2.load_settings_from_cache(task2.account_id, dbx2)
    assert id(dbx1) == id(dbx2)
    assert id(settings1) == id(settings2)


@pytest.mark.parametrize("extension", config.image_extensions)
@pytest.mark.parametrize("process_img", [True, False])
def test_duplicate_worse(tmpdir, extension, monkeypatch, process_img) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    monkeypatch_img_processing(monkeypatch, return_new_data=process_img)
    metadata = dropbox.files.PhotoMetadata(
        dimensions=dropbox.files.Dimensions(100, 100)
    )
    run_task_process_entry(
        test_name=f"test_duplicate_worse{extension}{process_img}",
        ext=extension,
        root_dir=root_dir,
        file_name="worse",
        metadata=metadata,
    )
    metadata = dropbox.files.PhotoMetadata(
        dimensions=dropbox.files.Dimensions(150, 150)
    )
    run_task_process_entry(
        test_name=f"test_duplicate_worse{extension}{process_img}",
        ext=extension,
        root_dir=root_dir,
        file_name="better",
        metadata=metadata,
    )
    uploads, review, backup, error = _get_folder_contents(root_dir)
    assert error == [], "No error during processing"
    assert uploads == []
    assert len(review) == 3
    assert len(backup) == 4
    assert len(list((root_dir / "Review").rglob("*worse*"))) == 0
    assert len(list((root_dir / "Review").rglob("*better*"))) == 1
    assert len(list((root_dir / "Backup").rglob("*worse*"))) == 1
    assert len(list((root_dir / "Backup").rglob("*better*"))) == 1


@pytest.mark.parametrize("extension", config.image_extensions)
@pytest.mark.parametrize("process_img", [True, False])
def test_duplicate_better(tmpdir, extension, monkeypatch, process_img) -> None:
    root_dir = Path(tmpdir)
    make_all_temp_folders(root_dir)
    monkeypatch_img_processing(monkeypatch, return_new_data=process_img)
    metadata = dropbox.files.PhotoMetadata(
        dimensions=dropbox.files.Dimensions(150, 150)
    )
    run_task_process_entry(
        test_name=f"test_duplicate_better{extension}{process_img}",
        ext=extension,
        root_dir=root_dir,
        file_name="better",
        metadata=metadata,
    )
    metadata = dropbox.files.PhotoMetadata(
        dimensions=dropbox.files.Dimensions(100, 100)
    )
    run_task_process_entry(
        test_name=f"test_duplicate_better{extension}{process_img}",
        ext=extension,
        root_dir=root_dir,
        file_name="worse",
        metadata=metadata,
    )
    uploads, review, backup, error = _get_folder_contents(root_dir)
    assert error == [], "No error during processing"
    assert uploads == []
    assert len(list((root_dir / "Review").rglob("*worse*"))) == 0
    assert len(list((root_dir / "Review").rglob("*better*"))) == 1
    assert len(list((root_dir / "Backup").rglob("*worse*"))) == 1
    assert len(list((root_dir / "Backup").rglob("*better*"))) == 1
    assert len(review) == 3
    assert len(backup) == 4


def monkeypatch_img_processing(monkeypatch, return_new_data: bool) -> None:
    def no_img_processing_mock(*args, **kwargs):
        new_data = None
        return new_data

    def process_img_mock(dimensions, *args, **kwargs):
        new_data = make_image(dimensions=dimensions, changed=True)
        return new_data

    if return_new_data is True:
        monkeypatch.setattr("kamera.task.image_processing.main", process_img_mock)
    else:
        monkeypatch.setattr("kamera.task.image_processing.main", no_img_processing_mock)


@pytest.fixture()
def error_parse_date(monkeypatch):
    def error_parse_date_mock(*args, **kwargs):
        raise Exception("This is an excpetion from mock parse_date")

    monkeypatch.setattr("kamera.task.parse_date", error_parse_date_mock)


class MockSettings(config.Settings):
    "Subclasses settings but overrides only method, to satisfy mypy"

    def __init__(self, account_id):
        self.default_tz: str = "US/Eastern"
        self.folder_names: t.Dict[str, str] = {
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
            12: "December",
        }


@pytest.fixture()
def settings():
    return MockSettings("")
