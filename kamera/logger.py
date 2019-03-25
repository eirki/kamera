#! /usr/bin/env python3.6
# coding: utf-8

import logging
import os
from logging import StreamHandler

log = logging.getLogger()
formatter = logging.Formatter("%(filename)s %(levelname)s - %(message)s")

handler = StreamHandler()
handler.setFormatter(formatter)
log.addHandler(handler)
log.setLevel(os.environ.get("loglevel", "INFO"))
