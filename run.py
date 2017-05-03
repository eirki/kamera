#! /usr/bin/env python3.6
# coding: utf-8

# From https://help.pythonanywhere.com/pages/LongRunningTasks/
import socket
import sys

import config


lock_socket = None  # we want to keep the socket open until the very end of
                    # our script so we use a global variable to avoid going
                    # out of scope and being garbage-collected

def is_lock_free():
    global lock_socket
    lock_socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        lock_id = config.app_id
        lock_socket.bind(f"\0{lock_id}")
        print(f"Acquired lock {lock_id}")
        return True
    except socket.error:
        # socket already locked, task must already be running
        print(f"Failed to acquire lock {lock_id}")
        return False


if not is_lock_free():
    sys.exit()


import app
app.main()
