#! /usr/bin/env python3.6
# coding: utf-8
from kamera.logger import log

import sys
import argparse

import rq
import dropbox

from kamera.task import Task
from kamera import config
from kamera.routes import app, redis_client, queue, dbx_list_entries


def main(mode: str) -> None:
    try:
        log.info("Starting gargbot_3000")
        parser = argparse.ArgumentParser()
        parser.add_argument("--mode", "-m")
        parser.add_argument("--debug", "-d", action="store_true")
        parser.add_argument("--bind", "-b", default="0.0.0.0")
        parser.add_argument("--workers", "-w", default=3)
        parser.add_argument("--port", "-p", default=":5000")
        args = parser.parse_args()

        if args.mode == "server":
            app.run()
        elif args.mode == "worker":
            with rq.Connection(redis_client):
                worker = rq.SimpleWorker(queues=[queue])
                worker.work()
        elif args.mode == "run_once":
            account_id = sys.argv[2]
            dbx = dropbox.Dropbox(config.get_dbx_token(redis_client, account_id))
            Task.dbx_cache[account_id] = dbx
            for entry, metadata in dbx_list_entries(dbx, config.uploads_path):
                task = Task(
                    account_id,
                    entry,
                    metadata,
                    config.review_path,
                    config.backup_path,
                    config.errors_path,
                )
                task.process_entry()
    except Exception as exc:
        log.exception(exc)
        raise


if __name__ == "__main__":
    main(sys.argv[1])
