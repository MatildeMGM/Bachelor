import csv
import time
from datetime import datetime
from pathlib import Path

from arduino.app_bricks.web_ui import WebUI

from app.python.bridge import (
    fetch_arduino_status,
    push_price_to_mcu,
    push_scenario_to_mcu,
)
from app.python.config import (
    DEFAULT_PRICE_ZONE,
    DEMO_ENABLED,
    DEMO_SLOT_SECONDS,
    DK_TZ,
    VALID_PRICE_ZONES,
)
from app.python.data.prices import fetch_prices_for_today
from app.python.ems_state import known_clients, state, state_lock
from app.python.scheduler import (
    SchedulerConfig,
    decide_current_scenario,
    load_limits,
    load_scaled_demand_profile,
)


ui = WebUI()
limits = load_limits()
scheduler_config = SchedulerConfig()
LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_FIELDS = [
    "real_time",
    "demo_cycle",
    "sim_slot",
    "sim_time",
    "sim_interval",
    "price_dkk_kwh",
    "price_state",
    "demand_state",
    "pv_state",
    "battery_state",
    "pem_state",
    "demand_w",
    "target_scenario",
    "actual_scenario",
    "scenario_accepted",
    "reject_reason",
    "scheduler_reason",
    "pv_power_w",
    "load_power_w",
    "battery_soc_percent",
    "battery_energy_wh",
    "pem_hydrogen_est_ml",
    "battery_voltage_v",
    "pem_voltage_v",
    "command",
]
logged_slots = set()


def get_now():
    return datetime.now(DK_TZ)


def slot_to_time_label(slot):
    hour = slot // 4
    minute = (slot % 4) * 15
    return f"{hour:02d}:{minute:02d}"


def slot_to_interval_label(slot):
    start_hour = slot // 4
    start_minute = (slot % 4) * 15
    end_hour = start_hour
    end_minute = start_minute + 15

    if end_minute >= 60:
        end_minute = 0
        end_hour = (end_hour + 1) % 24

    return f"{start_hour:02d}:{start_minute:02d}-{end_hour:02d}:{end_minute:02d}"


def update_demo_time():
    if state.demo_started_at == 0.0:
        state.demo_started_at = time.monotonic()

    elapsed = time.monotonic() - state.demo_started_at
    absolute_slot = int(elapsed // state.demo_slot_seconds)

    state.demo_elapsed_seconds = elapsed
    state.demo_cycle = absolute_slot // 96
    state.current_slot = absolute_slot % 96
    state.current_hour = state.current_slot // 4
    state.current_minute = (state.current_slot % 4) * 15
    state.current_time_label = slot_to_time_label(state.current_slot)
    state.current_interval_label = slot_to_interval_label(state.current_slot)


def update_current_inputs():
    update_demo_time()

    if state.prices and len(state.prices) > state.current_slot:
        state.current_price = state.prices[state.current_slot]
    else:
        state.current_price = 0.0

    state.update_current_demand()


def build_payload():
    return {
        "runtime": {
            "clients": state.clients,
            "bridge_ok": state.bridge_ok,
            "last_error": state.last_error,
            "price_zone": state.price_zone,
            "price_source": state.price_source,
            "last_price_update": state.last_price_update,
            "last_demand_update": state.last_demand_update,
        },
        "demo": {
            "enabled": state.demo_enabled,
            "running": state.demo_running,
            "cycle": state.demo_cycle,
            "slot_seconds": state.demo_slot_seconds,
            "elapsed_seconds": state.demo_elapsed_seconds,
        },
        "prices": state.prices,
        "demand_profile": state.demand_profile,
        "current_hour": state.current_hour,
        "current_minute": state.current_minute,
        "current_slot": state.current_slot,
        "current_time_label": state.current_time_label,
        "current_interval_label": state.current_interval_label,
        "current_price": state.current_price,
        "current_demand_w": state.current_demand_w,
        "scheduler": {
            "current_decision": state.current_decision,
            "current_command": state.current_command,
            "target_scenario": state.target_scenario,
            "last_decision_update": state.last_decision_update,
            "log_file": state.log_file,
            "last_log_update": state.last_log_update,
        },
        "arduino_status": state.arduino_status,
    }


def send_telemetry():
    ui.send_message("telemetry", build_payload())


def refresh_prices():
    try:
        prices = fetch_prices_for_today(zone=state.price_zone)

        with state_lock:
            state.prices = prices
            state.last_price_update = get_now().isoformat(timespec="seconds")
            state.last_error = ""
            update_current_inputs()

        print("Loaded 96 price values for", state.price_zone)

    except Exception as e:
        state.last_error = f"Price fetch failed: {e}"
        print(state.last_error)


def refresh_demand_profile():
    try:
        demand_profile = load_scaled_demand_profile()

        with state_lock:
            state.demand_profile = demand_profile
            state.last_demand_update = get_now().isoformat(timespec="seconds")
            state.last_error = ""
            update_current_inputs()

        print("Loaded 96 demand values")

    except Exception as e:
        state.last_error = f"Demand profile load failed: {e}"
        print(state.last_error)


def refresh_inputs():
    refresh_prices()
    refresh_demand_profile()


def run_scheduler_decision():
    if not state.prices or not state.demand_profile:
        return

    decision = decide_current_scenario(
        prices=state.prices,
        demand_profile=state.demand_profile,
        current_slot=state.current_slot,
        component_state=state.to_component_state(),
        limits=limits,
        config=scheduler_config,
    )

    state.apply_scheduler_decision(decision)
    state.last_decision_update = get_now().isoformat(timespec="seconds")


def actual_scenario_from_mode(mode):
    text = str(mode or "")
    for scenario in range(1, 7):
        if f"S{scenario}" in text:
            return scenario
    return 0


def start_demo_log():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    filename = "ems_demo_{}.csv".format(get_now().strftime("%Y%m%d_%H%M%S"))
    path = LOG_DIR / filename

    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=LOG_FIELDS)
        writer.writeheader()

    state.log_file = str(path)
    state.last_log_update = ""
    logged_slots.clear()


def log_current_slot():
    if not state.log_file or not state.current_decision:
        return

    key = (state.demo_cycle, state.current_slot)
    if key in logged_slots:
        return

    decision = state.current_decision
    status = state.arduino_status

    row = {
        "real_time": get_now().isoformat(timespec="seconds"),
        "demo_cycle": state.demo_cycle,
        "sim_slot": state.current_slot,
        "sim_time": state.current_time_label,
        "sim_interval": state.current_interval_label,
        "price_dkk_kwh": state.current_price,
        "price_state": decision.get("price_state", ""),
        "demand_state": decision.get("demand_state", ""),
        "pv_state": decision.get("pv_state", ""),
        "battery_state": decision.get("battery_state", ""),
        "pem_state": decision.get("pem_state", ""),
        "demand_w": state.current_demand_w,
        "target_scenario": state.target_scenario,
        "actual_scenario": actual_scenario_from_mode(status.get("mode", "")),
        "scenario_accepted": status.get("scenarioAccepted", ""),
        "reject_reason": status.get("lastRejectReason", ""),
        "scheduler_reason": decision.get("reason", ""),
        "pv_power_w": status.get("PVpower", ""),
        "load_power_w": status.get("Loadpower", ""),
        "battery_soc_percent": status.get("batterySOC", ""),
        "battery_energy_wh": status.get("batteryEnergyWh", ""),
        "pem_hydrogen_est_ml": state.pem_hydrogen_ml,
        "battery_voltage_v": status.get("batteryVoltage", ""),
        "pem_voltage_v": status.get("pemrfcVoltage", ""),
        "command": state.current_command,
    }

    with Path(state.log_file).open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=LOG_FIELDS)
        writer.writerow(row)

    logged_slots.add(key)
    state.last_log_update = get_now().isoformat(timespec="seconds")


def publish_state(push_bridge=True):
    with state_lock:
        update_current_inputs()

        if push_bridge:
            try:
                state.apply_arduino_status(fetch_arduino_status())
                run_scheduler_decision()
                push_price_to_mcu()
                push_scenario_to_mcu(state.current_command)
                state.apply_arduino_status(fetch_arduino_status())
                log_current_slot()
                state.bridge_ok = True
                state.last_error = ""
            except Exception as e:
                state.bridge_ok = False
                state.last_error = f"Bridge error: {e}"

        payload = build_payload()

    ui.send_message("telemetry", payload)


def ems_loop():
    state.demo_enabled = DEMO_ENABLED
    state.demo_running = True
    state.demo_slot_seconds = DEMO_SLOT_SECONDS
    state.demo_started_at = time.monotonic()

    refresh_inputs()
    start_demo_log()

    last_slot = None

    while True:
        try:
            with state_lock:
                update_current_inputs()
                current_slot = state.current_slot

            # The EMS decision is updated once per simulated 15 minute slot.
            if current_slot != last_slot:
                publish_state(push_bridge=True)
                last_slot = current_slot
            else:
                publish_state(push_bridge=False)

        except Exception as e:
            state.last_error = str(e)
            try:
                send_telemetry()
            except Exception:
                pass

        time.sleep(0.5)


def on_state_request(client_id, data):
    known_clients.add(client_id)
    state.clients = len(known_clients)
    send_telemetry()


def on_price_control(client_id, data):
    known_clients.add(client_id)
    state.clients = len(known_clients)

    action = (data or {}).get("action", "")

    if action == "refresh":
        refresh_inputs()
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

    elif action == "restart_demo":
        with state_lock:
            state.demo_started_at = time.monotonic()
            state.demo_cycle = 0
            update_current_inputs()
            start_demo_log()
        publish_state(push_bridge=True)

    else:
        send_telemetry()


def api_status():
    with state_lock:
        return build_payload()


def setup_ui():
    ui.expose_api("GET", "/api/status", api_status)
    ui.on_message("state_request", on_state_request)
    ui.on_message("price_control", on_price_control)
