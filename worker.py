#! /usr/bin/env python3.6
# coding: utf-8

import sys
import os

import redis
import rq

from kamera import task
from kamera import config
from kamera import recognition
from kamera import cloud

listen = ['default']

redis_url = os.getenv('REDISTOGO_URL', 'redis://localhost:6379')

conn = redis.from_url(redis_url)

if sys.argv[1] == "loop":
    task.main()

elif sys.argv[1] == "run_once":
    from kamera import task
    task.main(mode="test")


def main():
    recognition.load_encodings(home_path=config.home)
    cloud.dbx.users_get_current_account()
    with rq.Connection(conn):
        worker = rq.Worker(list(map(rq.Queue, listen)))
        worker.work()


if __name__ == '__main__':
    main()
