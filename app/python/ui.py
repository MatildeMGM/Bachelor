# This file contains the WebUI setup, telemetry handling, and the main update loop.

import time
from datetime import datetime

from arduino.app_bricks.web_ui import WebUI

from app.python.bridge import fetch_arduino_status, push_price_to_mcu
from app.python.config import DEFAULT_PRICE_ZONE, DK_TZ, LOOP_SLEEP_SECONDS, VALID_PRICE_ZONES
from app.python.data.prices import fetch_prices_for_today
from app.python.data.pv import fetch_pv_forecast_for_today
from app.python.ems_state import known_clients, state, state_lock

ui = WebUI()


def get_now():
    return datetime.now(DK_TZ)


def get_current_slot(now=None):
    if now is None:
        now = get_now()
    return now.hour * 4 + (now.minute // 15)


def get_current_time_label(now=None):
    if now is None:
        now = get_now()
    return "{:02d}:{:02d}".format(now.hour, now.minute)


def get_current_interval_label(now=None):
    if now is None:
        now = get_now()

    start_minute = (now.minute // 15) * 15
    end_hour = now.hour
    end_minute = start_minute + 15

    if end_minute >= 60:
        end_minute = 0
        end_hour = (end_hour + 1) % 24

    return "{:02d}:{:02d}-{:02d}:{:02d}".format(
        now.hour, start_minute, end_hour, end_minute
    )


def update_current_time_price_and_pv():
    now = get_now()

    state.current_hour = now.hour
    state.current_minute = now.minute
    state.current_slot = get_current_slot(now)
    state.current_time_label = get_current_time_label(now)
    state.current_interval_label = get_current_interval_label(now)

    if state.prices and len(state.prices) > state.current_slot:
        state.current_price = state.prices[state.current_slot]
    else:
        state.current_price = 0.0

    if state.pv_forecast and len(state.pv_forecast) > state.current_slot:
        state.current_pv_forecast = state.pv_forecast[state.current_slot]
    else:
        state.current_pv_forecast = 0.0


def build_payload():
    return {
        "runtime": {
            "clients": state.clients,
            "bridge_ok": state.bridge_ok,
            "last_error": state.last_error,
            "price_zone": state.price_zone,
            "price_source": state.price_source,
            "last_price_update": state.last_price_update,
            "last_pv_update": state.last_pv_update,
        },
        "prices": state.prices,
        "pv_forecast": state.pv_forecast,
        "current_hour": state.current_hour,
        "current_minute": state.current_minute,
        "current_slot": state.current_slot,
        "current_time_label": state.current_time_label,
        "current_interval_label": state.current_interval_label,
        "current_price": state.current_price,
        "current_pv_forecast": state.current_pv_forecast,
        "arduino_status": state.arduino_status,
    }


def send_telemetry():
    ui.send_message("telemetry", build_payload())


def refresh_prices():
    try:
        prices = fetch_prices_for_today(zone=state.price_zone)

        print("=== PRICE FETCH ===")
        print("ZONE:", state.price_zone)
        print("NUMBER OF PRICES:", len(prices))
        print("FIRST 8 PRICES:", prices[:8])

        with state_lock:
            state.prices = prices
            state.last_price_update = get_now().isoformat(timespec="seconds")
            state.last_error = ""
            update_current_time_price_and_pv()

        print("CURRENT TIME:", state.current_time_label)
        print("CURRENT INTERVAL:", state.current_interval_label)
        print("CURRENT SLOT:", state.current_slot)
        print("CURRENT PRICE:", state.current_price)
        print("===================")

    except Exception as e:
        state.last_error = f"Price fetch failed: {e}"
        print(state.last_error)


def refresh_pv_forecast():
    try:
        pv_forecast = fetch_pv_forecast_for_today()

        print("=== PV FORECAST FETCH ===")
        print("NUMBER OF PV VALUES:", len(pv_forecast))
        print("FIRST 8 PV VALUES:", pv_forecast[:8])

        with state_lock:
            state.pv_forecast = pv_forecast
            state.last_pv_update = get_now().isoformat(timespec="seconds")
            state.last_error = ""
            update_current_time_price_and_pv()

        print("CURRENT PV FORECAST:", state.current_pv_forecast)
        print("=========================")

    except Exception as e:
        state.last_error = f"PV forecast fetch failed: {e}"
        print(state.last_error)


def refresh_forecasts():
    refresh_prices()
    refresh_pv_forecast()


def publish_state(push_bridge=True):
    with state_lock:
        update_current_time_price_and_pv()

        if push_bridge:
            try:
                push_price_to_mcu()
                state.arduino_status = fetch_arduino_status()
                state.bridge_ok = True
                state.last_error = ""
            except Exception as e:
                state.bridge_ok = False
                state.last_error = f"Bridge error: {e}"

        payload = build_payload()

    ui.send_message("telemetry", payload)


def forecast_loop():
    last_refresh_date = None

    while True:
        try:
            today = get_now().date()

            if last_refresh_date != today or not state.prices or not state.pv_forecast:
                refresh_forecasts()
                last_refresh_date = today

            publish_state(push_bridge=True)

        except Exception as e:
            state.last_error = str(e)
            try:
                send_telemetry()
            except Exception:
                pass

        time.sleep(LOOP_SLEEP_SECONDS)


def on_state_request(client_id, data):
    known_clients.add(client_id)
    state.clients = len(known_clients)
    send_telemetry()


def on_price_control(client_id, data):
    known_clients.add(client_id)
    state.clients = len(known_clients)

    action = (data or {}).get("action", "")

    if action == "refresh":
        refresh_forecasts()
        publish_state(push_bridge=True)

    elif action == "set_zone":
        zone = (data or {}).get("zone", DEFAULT_PRICE_ZONE)
        if zone in VALID_PRICE_ZONES:
            state.price_zone = zone
            refresh_prices()
            publish_state(push_bridge=True)
        else:
            state.last_error = "Invalid price zone"
            send_telemetry()
    else:
        send_telemetry()


def api_status():
    with state_lock:
        return build_payload()


def setup_ui():
    ui.expose_api("GET", "/api/status", api_status)
    ui.on_message("state_request", on_state_request)
    ui.on_message("price_control", on_price_control)