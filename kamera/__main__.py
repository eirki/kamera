#! /usr/bin/env python3.6
# coding: utf-8
import argparse
import sys
import typing as t

import dropbox
import rq
from gunicorn.app.base import BaseApplication

from kamera import config, server
from kamera.logger import log
from kamera.task import Task


class StandaloneApplication(BaseApplication):
    def __init__(self, app, options: t.Dict[str, t.Any] = None) -> None:
        self.options = options if options is not None else {}
        self.application = app
        super().__init__()

    def load_config(self) -> None:
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
                options = {
                    "bind": "%s:%s" % (args.bind, args.port),
                    "workers": args.workers,
                }
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
            settings = config.Settings(dbx)
            for entry in server.dbx_list_entries(dbx, config.uploads_path):
                task = Task(
                    account_id,
                    entry,
                    config.review_path,
                    config.backup_path,
                    config.errors_path,
                )
                task.process_entry(server.redis_client, dbx, settings)
    except Exception:
        log.exception("Exception in main loop")
        raise


if __name__ == "__main__":
    main()
