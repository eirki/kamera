#! /usr/bin/env python3.6
# coding: utf-8
from kamera.logger import log

import sys
import argparse

import rq
import dropbox
from gunicorn.app.base import BaseApplication

from kamera.task import Task
from kamera import config
# from kamera.server import app, redis_client, queue, dbx_list_entries
from kamera import server


class StandaloneApplication(BaseApplication):
    def __init__(self, app, options=None):
        self.options = options if options is not None else {}
        self.application = app
        super().__init__()

    def load_config(self):
        for key, value in self.options.items():
            if key in self.cfg.settings and value is not None:
                self.cfg.set(key.lower(), value)

    def load(self):
        return self.application


def main() -> None:
    try:
        log.info("Starting kamera")
        parser = argparse.ArgumentParser()
        parser.add_argument("--mode", "-m")
        parser.add_argument("--debug", "-d", action="store_true")
        parser.add_argument("--bind", "-b", default="0.0.0.0")
        parser.add_argument("--workers", "-w", default=3)
        parser.add_argument("--port", "-p")
        args = parser.parse_args()

        if args.mode == "server":
            if args.debug is False:
                options = {"bind": "%s:%s" % (args.bind, args.port), "workers": args.workers}
                gunicorn_app = StandaloneApplication(server.app, options)
                gunicorn_app.run()
            elif args.debug is True:
                server.app.run()
        elif args.mode == "worker":
            with rq.Connection(server.redis_client):
                worker = rq.SimpleWorker(queues=[server.queue])
                worker.work()
        elif args.mode == "run_once":
            account_id = sys.argv[2]
            dbx = dropbox.Dropbox(config.get_dbx_token(server.redis_client, account_id))
            Task.dbx_cache[account_id] = dbx
            for entry, metadata in server.dbx_list_entries(dbx, config.uploads_path):
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
    main()
