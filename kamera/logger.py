#! /usr/bin/env python3.6
# coding: utf-8
import logging
import os

log = logging.getLogger()
log.setLevel(os.environ.get("LOGLEVEL", "INFO"))

formatter = logging.Formatter("%(filename)s %(levelname)s - %(message)s")
ch = logging.StreamHandler()
ch.setLevel(os.environ.get("LOGLEVEL", "INFO"))
ch.setFormatter(formatter)
log.addHandler(ch)
