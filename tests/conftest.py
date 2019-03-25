#! /usr/bin/env python3
# coding: utf-8
from pathlib import Path

from dotenv import load_dotenv

env_path = Path(".") / ".test.env"
load_dotenv(dotenv_path=env_path)
