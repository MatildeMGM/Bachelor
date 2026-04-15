import threading
import time
from datetime import datetime

from arduino.app_utils import App, Bridge
from arduino.app_bricks.web_ui import WebUI

from prices import fetch_prices_for_today

ui = WebUI()
state_lock = threading.Lock()

runtime = {
    "prices": [],
    "price_zone": "DK2",
    "current_hour": 0,
    "current_minute": 0,
    "current_slot": 0,          # 0..95
    "current_price": 0.0,
    "price_source": "api.energidataservice.dk",
    "last_price_update": "",
    "bridge_ok": None,
    "last_error": "",
    "clients": 0,
    "arduino_status": {},
}

known_clients = set()


def get_current_slot(now=None):
    if now is None:
        now = datetime.now()

    return now.hour * 4 + (now.minute // 15)


def update_current_time_and_price():
    now = datetime.now()

    runtime["current_hour"] = now.hour
    runtime["current_minute"] = now.minute
    runtime["current_slot"] = get_current_slot(now)

    if runtime["prices"] and len(runtime["prices"]) > runtime["current_slot"]:
        runtime["current_price"] = runtime["prices"][runtime["current_slot"]]
    else:
        runtime["current_price"] = 0.0


def refresh_prices():
    try:
        prices = fetch_prices_for_today(zone=runtime["price_zone"])

        print("=== PRICE FETCH ===")
        print("ZONE:", runtime["price_zone"])
        print("NUMBER OF PRICES:", len(prices))
        print("FIRST 8 PRICES:", prices[:8])

        with state_lock:
            runtime["prices"] = prices
            runtime["last_price_update"] = datetime.now().isoformat(timespec="seconds")
            runtime["last_error"] = ""
            update_current_time_and_price()

        print("CURRENT HOUR:", runtime["current_hour"])
        print("CURRENT MINUTE:", runtime["current_minute"])
        print("CURRENT SLOT:", runtime["current_slot"])
        print("CURRENT PRICE:", runtime["current_price"])
        print("===================")

    except Exception as e:
        runtime["last_error"] = f"Price fetch failed: {e}"
        print(runtime["last_error"])


def push_price_to_mcu():
    payload = "PRICE,{price:.5f},{slot}".format(
        price=runtime["current_price"],
        slot=runtime["current_slot"],
    )

    now = datetime.now().strftime("%H:%M:%S")
    print("[{}] SENDING PRICE TO MCU: {}".format(now, payload))

    Bridge.call("apply_price_frame", payload, timeout=2)


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
    raw = Bridge.call("get_status", timeout=2)
    return parse_status_string(raw)


def build_payload():
    return {
        "runtime": {
            "clients": runtime["clients"],
            "bridge_ok": runtime["bridge_ok"],
            "last_error": runtime["last_error"],
            "price_zone": runtime["price_zone"],
            "price_source": runtime["price_source"],
            "last_price_update": runtime["last_price_update"],
        },
        "prices": runtime["prices"],
        "current_hour": runtime["current_hour"],
        "current_minute": runtime["current_minute"],
        "current_slot": runtime["current_slot"],
        "current_price": runtime["current_price"],
        "arduino_status": runtime["arduino_status"],
    }


def send_telemetry():
    ui.send_message("telemetry", build_payload())


def publish_state(push_bridge=True):
    with state_lock:
        update_current_time_and_price()

        if push_bridge:
            try:
                push_price_to_mcu()
                runtime["arduino_status"] = fetch_arduino_status()
                runtime["bridge_ok"] = True
                runtime["last_error"] = ""
            except Exception as e:
                runtime["bridge_ok"] = False
                runtime["last_error"] = f"Bridge error: {e}"

        payload = build_payload()

    ui.send_message("telemetry", payload)


def price_loop():
    last_refresh_date = None

    while True:
        try:
            today = datetime.now().date()

            if last_refresh_date != today or not runtime["prices"]:
                refresh_prices()
                last_refresh_date = today

            publish_state(push_bridge=True)

        except Exception as e:
            runtime["last_error"] = str(e)
            try:
                send_telemetry()
            except Exception:
                pass

        time.sleep(2)


def on_state_request(client_id, data):
    known_clients.add(client_id)
    runtime["clients"] = len(known_clients)
    send_telemetry()


def on_price_control(client_id, data):
    known_clients.add(client_id)
    runtime["clients"] = len(known_clients)

    action = (data or {}).get("action", "")

    if action == "refresh":
        refresh_prices()
        publish_state(push_bridge=True)

    elif action == "set_zone":
        zone = (data or {}).get("zone", "DK2")
        if zone in ["DK1", "DK2"]:
            runtime["price_zone"] = zone
            refresh_prices()
            publish_state(push_bridge=True)
        else:
            runtime["last_error"] = "Invalid price zone"
            send_telemetry()
    else:
        send_telemetry()


def api_status():
    with state_lock:
        return build_payload()


ui.expose_api("GET", "/api/status", api_status)

ui.on_message("state_request", on_state_request)
ui.on_message("price_control", on_price_control)

threading.Thread(target=price_loop, daemon=True).start()

print("Starting EMS App...")

App.run()