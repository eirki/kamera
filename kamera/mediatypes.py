#! /usr/bin/env python3
# coding: utf-8
from kamera.logger import log


from pathlib import Path

from typing import Optional
import dropbox


class KameraEntry:
    def __init__(
            self,
            entry: dropbox.files.Metadata,
            metadata: Optional[dropbox.files.FileMetadata] = None) -> None:
        self.path = Path(entry.path_display)
        self.client_modified = entry.client_modified

        if metadata is not None:
            self.time_taken = metadata.time_taken
            self.dimensions = metadata.dimensions if metadata.dimensions else None
            self.location = metadata.location if metadata.location else None
        else:
            self.time_taken = None
            self.dimensions = None
            self.location = None

    def __repr__(self):
        return repr(self.name)
