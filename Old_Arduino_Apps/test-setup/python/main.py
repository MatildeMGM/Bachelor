# main.py
# Runs on the Linux/Python side (Arduino App Lab / UNO Q Bridge)

import random
from arduino.app_utils import Bridge, App


def linux_started() -> bool:
    # Simple handshake endpoint so the MCU sketch can wait until Python is ready
    return True


def get_crystal_reply_index() -> int:
    # Return an integer 0..7
    # Put any “Python functionality” here (weighted choices, web calls, logging, etc.)
    return random.randint(0, 7)


Bridge.provide("linux_started", linux_started)
Bridge.provide("get_crystal_reply_index", get_crystal_reply_index)

App.run()