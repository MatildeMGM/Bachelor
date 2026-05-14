from __future__ import annotations

from datetime import datetime

from arduino.app_utils import Bridge

from config import BRIDGE_TIMEOUT, DK_TZ
from ems_state import state


def get_now():
    return datetime.now(DK_TZ)


def parse_status_string(raw):
    result = {}

    if not raw:
        return result

    for part in str(raw).split(","):
        if "=" not in part:
            continue

        key, value = part.split("=", 1)
        key = key.strip()
        value = value.strip()

        if key in {"mode", "lastRejectReason", "lastError", "batteryChargeState", "batterySOCStatus"}:
            result[key] = value
            continue

        if key in {
            "hour",
            "slot",
            "priceReceived",
            "scenarioReceived",
            "scenarioAccepted",
            "requestedScenario",
            "activeScenario",
            "scenario_accepted",
            "requested_scenario",
            "active_scenario",
            "inaBatOk",
            "inaLoadOk",
            "inaPVOk",
            "inaPEMOk",
            "loadTrigger",
            "K1",
            "K2",
            "K3",
            "K4",
            "K5",
            "K6",
            "K7",
            "batterySOCInitialized",
        }:
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
    print(f"[{now_str}] SENDING PRICE TO MCU: {payload}")

    return Bridge.call("apply_price_frame", payload, timeout=BRIDGE_TIMEOUT)


def push_scenario_to_mcu(command):
    if not command:
        return None

    now_str = get_now().strftime("%H:%M:%S")
    print(f"[{now_str}] SENDING SCENARIO TO MCU: {command}")

    return Bridge.call("apply_scenario_frame", command, timeout=BRIDGE_TIMEOUT)


def push_manual_scenario_to_mcu(command):
    if not command:
        return None

    manual_command = command.replace("SCENARIO,", "MANUAL_SCENARIO,", 1)

    now_str = get_now().strftime("%H:%M:%S")
    print(f"[{now_str}] SENDING MANUAL SCENARIO TO MCU: {manual_command}")

    return Bridge.call("apply_scenario_frame", manual_command, timeout=BRIDGE_TIMEOUT)


def push_relay_to_mcu(relay, output_state):
    relay_name = str(relay).upper()
    value = 1 if int(output_state) else 0
    payload = f"RELAY,{relay_name},{value}"

    now_str = get_now().strftime("%H:%M:%S")
    print(f"[{now_str}] SENDING RELAY TO MCU: {payload}")

    return Bridge.call("apply_relay_frame", payload, timeout=BRIDGE_TIMEOUT)


def push_load_trigger_to_mcu(active):
    value = 1 if active else 0
    payload = f"LOAD_TRIGGER,{value}"

    now_str = get_now().strftime("%H:%M:%S")
    print(f"[{now_str}] SENDING LOAD TRIGGER TO MCU: {payload}")

    return Bridge.call("apply_load_trigger_frame", payload, timeout=BRIDGE_TIMEOUT)
