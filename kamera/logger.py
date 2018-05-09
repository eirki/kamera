#! /usr/bin/env python3.6
# coding: utf-8
import logging

log = logging.getLogger()
log.setLevel(logging.INFO)

formatter = logging.Formatter(
    "%(filename)s %(levelname)s - %(message)s"
)

ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(formatter)
log.addHandler(ch)
