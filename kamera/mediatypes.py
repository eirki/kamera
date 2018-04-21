#! /usr/bin/env python3
# coding: utf-8
from kamera.logger import log

from collections import namedtuple

from pathlib import Path
import datetime as dt

from typing import Optional, Dict
import dropbox


Dimensions = namedtuple("Dimensions", ["height", "width"])
Location = namedtuple("Location", ["latitude", "longitude"])


class KameraEntry:
    def __init__(
            self,
            path: str,
            client_modified: dt.datetime,
            time_taken: dt.datetime,
            height: int,
            width: int,
            latitude: int,
            longitude: int) -> None:
        self.path = Path(path)
        self.name = self.path.name
        self.client_modified = client_modified
        self.time_taken = time_taken
        self.dimensions = (Dimensions(height=height, width=width)
                           if None not in {height, width} else None)
        self.location = (Location(latitude=latitude, longitude=longitude)
                         if None not in {latitude, longitude} else None)

    @classmethod
    def from_dbx_entry(
            cls,
            entry: dropbox.files.Metadata,
            dbx_photo_metadata: Optional[dropbox.files.FileMetadata] = None):
        time_taken = (dbx_photo_metadata.time_taken
                      if dbx_photo_metadata
                      else None)
        height = (dbx_photo_metadata.dimensions.height
                  if dbx_photo_metadata and dbx_photo_metadata.dimensions
                  else None)
        width = (dbx_photo_metadata.dimensions.width
                 if dbx_photo_metadata and dbx_photo_metadata.dimensions
                 else None)
        latitude = (dbx_photo_metadata.location.latitude
                    if dbx_photo_metadata and dbx_photo_metadata.location
                    else None)
        longitude = (dbx_photo_metadata.location.longitude
                     if dbx_photo_metadata and dbx_photo_metadata.location
                     else None)
        return cls(
            path=entry.path_display,
            client_modified=entry.client_modified,
            time_taken=time_taken,
            height=height,
            width=width,
            latitude=latitude,
            longitude=longitude,
        )

    @classmethod
    def from_db_data(cls, db_data: Dict):
        return cls(
            path=db_data["path"],
            client_modified=db_data["client_modified"],
            time_taken=db_data["time_taken"],
            height=db_data["height"],
            width=db_data["width"],
            latitude=db_data["latitude"],
            longitude=db_data["longitude"],
        )

    @property
    def db_data(self):
        return {
            "path": self.path.as_posix(),
            "client_modified": self.client_modified,
            "time_taken": self.time_taken,
            "height": self.dimensions.height if self.dimensions else None,
            "width": self.dimensions.width if self.dimensions else None,
            "latitude": self.location.latitude if self.location else None,
            "longitude": self.location.longitude if self.location else None,
        }

    def __repr__(self):
        return repr(self.name)

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return self.name == other.name

    def __ne__(self, other):
        return not self.__eq__(other)
