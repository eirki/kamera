#! /usr/bin/env python3.6
# coding: utf-8
import logging
import datetime as dt
import sys
from pathlib import Path

import config

log = logging.getLogger()
log.setLevel(logging.DEBUG)

formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

log_name = Path(sys.argv[0]).stem
log_path = config.home / "logs" / f"{log_name}.log"
if log_path.exists():
    now = dt.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    log_path.rename(log_path.with_name(f"{now}{log_name}.log"))

fh = logging.FileHandler(log_path.as_posix())
fh.setLevel(logging.DEBUG)
fh.setFormatter(formatter)
log.addHandler(fh)

ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
ch.setFormatter(formatter)
log.addHandler(ch)
