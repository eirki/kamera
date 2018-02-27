#! /usr/bin/env python3.6
# coding: utf-8
import logging
import datetime as dt

import config

log = logging.getLogger()
log.setLevel(logging.DEBUG)

formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

log_path = config.home / "logs" / "gargbot.log"
if log_path.exists():
    now = dt.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    log_path.rename(config.home / "logs" / f"gargbot{now}.log")

fh = logging.FileHandler(log_path.as_posix())
fh.setLevel(logging.DEBUG)
fh.setFormatter(formatter)
log.addHandler(fh)

ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
ch.setFormatter(formatter)
log.addHandler(ch)
