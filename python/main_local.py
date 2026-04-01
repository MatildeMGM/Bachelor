import threading
import time
from datetime import datetime

from prices import fetch_prices_for_today
from ems_state import EMSState


class DummyUI:
    def send_message(self, message_type, payload):
        print("UI MESSAGE:", message_type)
        print(payload)

    def on_message(self, *args, **kwargs):
        pass


class DummyBridge:
    @staticmethod
    def call(function_name, payload, timeout=2):
        print("DEBUG BRIDGE CALL:", function_name, payload)
        return True


ui = DummyUI()
bridge = DummyBridge()
state_lock = threading.Lock()
state = EMSState()


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


def push_price_to_mcu():
    payload = "PRICE,{price:.5f},{hour}".format(
        price=runtime["current_price"],
        hour=runtime["current_hour"],
    )

    try:
        bridge.call("apply_price_frame", payload, timeout=2)
        runtime["bridge_ok"] = True
    except Exception as e:
        runtime["bridge_ok"] = False
        runtime["last_error"] = f"Bridge error: {e}"


def update_current_hour_and_price():
    runtime["current_hour"] = datetime.now().hour

    if runtime["prices"] and len(runtime["prices"]) > runtime["current_hour"]:
        runtime["current_price"] = runtime["prices"][runtime["current_hour"]]
    else:
        runtime["current_price"] = 0.0

    state.current_hour = runtime["current_hour"]
    state.current_price = runtime["current_price"]
    state.prices = runtime["prices"]


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

    ui.send_message("telemetry", payload)


def print_status():
    print("Current hour:", runtime["current_hour"])
    print("Current price:", runtime["current_price"])
    print("Prices loaded:", len(runtime["prices"]))
    print("Bridge OK:", runtime["bridge_ok"])
    print("Last error:", runtime["last_error"])
    print("Last price update:", runtime["last_price_update"])
    print("-----")


def local_loop():
    last_refresh_date = None

    while True:
        try:
            today = datetime.now().date()

            if last_refresh_date != today or not runtime["prices"]:
                refresh_prices()
                last_refresh_date = today

            publish_state(push_bridge=True)
            print_status()

        except Exception as e:
            runtime["last_error"] = str(e)
            print("Error:", e)

        time.sleep(10)


if __name__ == "__main__":
    print("Running in local test mode...")
    local_loop()