#! /usr/bin/env python3.6
# coding: utf-8
import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import config

log = logging.getLogger()
log.setLevel(logging.INFO)

formatter = logging.Formatter(
    "[%(asctime)s] %(filename)s %(levelname)s - %(message)s"
)

log_name = Path(sys.argv[0]).stem
log_path = config.home / "logs" / f"{log_name}.log"

fh = RotatingFileHandler(
    filename=log_path.as_posix(),
    maxBytes=20000,
    backupCount=5
)

fh.setLevel(logging.INFO)
fh.setFormatter(formatter)
log.addHandler(fh)

ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(formatter)
log.addHandler(ch)
