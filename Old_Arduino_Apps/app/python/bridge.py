# This file contains the functions used for communication with the Arduino side.

from datetime import datetime

from arduino.app_utils import Bridge

from Bachelor.Old_Arduino_Apps.app.python.config import BRIDGE_TIMEOUT, DK_TZ
from Bachelor.Old_Arduino_Apps.app.python.ems_state import state


def get_now():
    return datetime.now(DK_TZ)


def parse_status_string(raw):
    result = {}

    if not raw:
        return result

    parts = raw.split(",")

    for part in parts:
        if "=" not in part:
            continue

        key, value = part.split("=", 1)
        key = key.strip()
        value = value.strip()

        if key == "mode":
            result[key] = value
            continue

        if key in ["hour", "slot", "priceReceived"]:
            try:
                result[key] = int(value)
            except ValueError:
                result[key] = value
            continue

        try:
            result[key] = float(value)
        except ValueError:
            result[key] = value

    return result


def fetch_arduino_status():
    raw = Bridge.call("get_status", timeout=BRIDGE_TIMEOUT)
    return parse_status_string(raw)


def push_price_to_mcu():
    payload = "PRICE,{price:.5f},{slot}".format(
        price=state.current_price,
        slot=state.current_slot,
    )

    now_str = get_now().strftime("%H:%M:%S")
    print("[{}] SENDING PRICE TO MCU: {}".format(now_str, payload))

    Bridge.call("apply_price_frame", payload, timeout=BRIDGE_TIMEOUT)