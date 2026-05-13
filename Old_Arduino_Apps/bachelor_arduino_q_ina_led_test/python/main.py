import threading
import time
from datetime import datetime

from arduino.app_utils import App, Bridge
from arduino.app_bricks.web_ui import WebUI

ui = WebUI()
state_lock = threading.Lock()
known_clients = set()

runtime = {
    "bridge_ok": None,
    "last_error": "",
    "clients": 0,
    "last_update": "",
    "arduino_status": {},
}


def parse_status_string(raw: str):
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

        if value in ["AUTO", "MANUAL"]:
            result[key] = value
            continue

        if key in ["modeText", "activeSignalName"]:
            result[key] = value
            continue

        try:
            if "." in value or "e" in value.lower():
                result[key] = float(value)
            else:
                result[key] = int(value)
        except ValueError:
            result[key] = value
    return result


def fetch_arduino_status():
    raw = Bridge.call("get_status", timeout=2)
    return parse_status_string(raw)


def build_payload():
    return {
        "runtime": {
            "bridge_ok": runtime["bridge_ok"],
            "last_error": runtime["last_error"],
            "clients": runtime["clients"],
            "last_update": runtime["last_update"],
        },
        "arduino_status": runtime["arduino_status"],
    }


def send_telemetry():
    ui.send_message("telemetry", build_payload())


def publish_state():
    with state_lock:
        try:
            runtime["arduino_status"] = fetch_arduino_status()
            runtime["bridge_ok"] = True
            runtime["last_error"] = ""
            runtime["last_update"] = datetime.now().isoformat(timespec="seconds")
        except Exception as e:
            runtime["bridge_ok"] = False
            runtime["last_error"] = f"Bridge error: {e}"

    send_telemetry()


def polling_loop():
    while True:
        try:
            publish_state()
        except Exception:
            pass
        time.sleep(1)


def on_state_request(client_id, data):
    known_clients.add(client_id)
    runtime["clients"] = len(known_clients)
    send_telemetry()


def on_led_control(client_id, data):
    known_clients.add(client_id)
    runtime["clients"] = len(known_clients)

    action = (data or {}).get("action", "")

    try:
        if action == "set_mode":
            mode = (data or {}).get("mode", "AUTO")
            Bridge.call("set_led_mode", mode, timeout=2)
        elif action == "set_index":
            index = int((data or {}).get("index", 0))
            Bridge.call("set_led_index", str(index), timeout=2)
        elif action == "set_interval":
            interval_ms = int((data or {}).get("interval_ms", 1500))
            Bridge.call("set_led_interval", str(interval_ms), timeout=2)
        elif action == "refresh":
            pass
        else:
            runtime["last_error"] = f"Unknown action: {action}"
    except Exception as e:
        runtime["last_error"] = f"Control error: {e}"

    publish_state()


# HTTP endpoint for browser UI
def api_status():
    with state_lock:
        return build_payload()


ui.expose_api("GET", "/api/status", api_status)
ui.on_message("state_request", on_state_request)
ui.on_message("led_control", on_led_control)

threading.Thread(target=polling_loop, daemon=True).start()

print("Starting INA226 + LED test app...")
App.run()
