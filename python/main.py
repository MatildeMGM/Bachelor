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
    "current_price": 0.0,
    "price_source": "elprisenligenu.dk",
    "last_price_update": "",
    "bridge_ok": None,
    "last_error": "",
    "clients": 0,
}

known_clients = set()


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
        "current_price": runtime["current_price"],
    }


def send_telemetry():
    ui.send_message("telemetry", build_payload())

'''
def push_price_to_mcu():
    payload = "PRICE,{price:.5f},{hour}".format(
        price=runtime["current_price"],
        hour=runtime["current_hour"],
    )

    try:
        Bridge.call("apply_price_frame", payload, timeout=2)
        runtime["bridge_ok"] = True
    except Exception as e:
        runtime["bridge_ok"] = False
        runtime["last_error"] = f"Bridge error: {e}"
'''

def push_price_to_mcu():
    payload = "PRICE,{price:.5f},{hour}".format(
        price=runtime["current_price"],
        hour=runtime["current_hour"],
    )

    print("DEBUG SEND:", payload)
    runtime["bridge_ok"] = True

def update_current_hour_and_price():
    runtime["current_hour"] = datetime.now().hour

    if runtime["prices"] and len(runtime["prices"]) > runtime["current_hour"]:
        runtime["current_price"] = runtime["prices"][runtime["current_hour"]]
    else:
        runtime["current_price"] = 0.0


def refresh_prices():
    try:
        prices = fetch_prices_for_today(zone=runtime["price_zone"])

        with state_lock:
            runtime["prices"] = prices
            runtime["last_price_update"] = datetime.now().isoformat(timespec="seconds")
            runtime["last_error"] = ""

            update_current_hour_and_price()

    except Exception as e:
        runtime["last_error"] = f"Price fetch failed: {e}"


def publish_state(push_bridge=True):
    with state_lock:
        update_current_hour_and_price()

        if push_bridge:
            push_price_to_mcu()

        payload = build_payload()
        
        print("Current hour:", runtime["current_hour"])
        print("Current price:", runtime["current_price"])
        print("Prices loaded:", len(runtime["prices"]))

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

        time.sleep(10)


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


ui.on_message("state_request", on_state_request)
ui.on_message("price_control", on_price_control)

threading.Thread(target=price_loop, daemon=True).start()
App.run()