from __future__ import annotations

from arduino.app_bricks.web_ui import WebUI

from config import DEFAULT_PRICE_ZONE, VALID_PRICE_ZONES
from ems_state import known_clients, state, state_lock


ui = WebUI()


def _ensure_optional_state_attributes():
    if not hasattr(state, "ems_enabled"):
        state.ems_enabled = False

    if not hasattr(state, "ems_start_requested"):
        state.ems_start_requested = False

    if not hasattr(state, "ems_stop_requested"):
        state.ems_stop_requested = False

    if not hasattr(state, "ems_status"):
        state.ems_status = "standby"

    if not hasattr(state, "live_history"):
        state.live_history = {}

    if not hasattr(state, "raw_log_running"):
        state.raw_log_running = False

    if not hasattr(state, "raw_log_start_requested"):
        state.raw_log_start_requested = False

    if not hasattr(state, "raw_log_stop_requested"):
        state.raw_log_stop_requested = False

    if not hasattr(state, "raw_log_file"):
        state.raw_log_file = ""

    if not hasattr(state, "last_raw_log_update"):
        state.last_raw_log_update = ""

    if not hasattr(state, "raw_log_sample_count"):
        state.raw_log_sample_count = 0

    if not hasattr(state, "reset_requested"):
        state.reset_requested = False

    if not hasattr(state, "demo_cycle_complete_requested"):
        state.demo_cycle_complete_requested = False


def build_payload():
    _ensure_optional_state_attributes()

    status = dict(state.arduino_status or {})

    # Remove legacy/raw battery keys from the UI payload to avoid accidental
    # frontend fallback between old Arduino names and the new realBattery* names.
    # The real battery values are re-added below with explicit names.
    for key in (
        "batterySOC",
        "batteryCharge_mAh",
        "batteryCapacity_mAh",
        "batteryChargeState",
        "batterySOCInitialized",
        "batterySOCStatus",
        "batteryInitialLookupVoltage",
        "batteryLookupEstimatedSOC",
        "batteryLookupVoltageMin",
        "batteryLookupVoltageMax",
    ):
        status.pop(key, None)

    # Add EMS-standardised measurement fields. The Arduino may still expose
    # original A/W fields, but the EMS/UI uses mA, mW and V.
    status["PVcurrent_mA"] = state.pv_current
    status["Batcurrent_mA"] = state.battery_current
    status["PEMcurrent_mA"] = state.pem_current
    status["Loadcurrent_mA"] = state.load_current

    status["PVpower_mW"] = state.pv_power
    status["Batterypower_mW"] = state.battery_power
    status["PEMpower_mW"] = state.pem_power
    status["Loadpower_mW"] = state.load_power

    # Real battery estimate from the Arduino safety layer.
    status["realBatterySOC"] = state.real_battery_soc
    status["realBatteryCharge_mAh"] = state.real_battery_charge_mAh
    status["realBatteryCapacity_mAh"] = state.real_battery_capacity_mAh
    status["realBatteryChargeState"] = state.real_battery_charge_state
    status["realBatterySOCInitialized"] = state.real_battery_soc_initialized
    status["realBatterySOCStatus"] = state.real_battery_soc_status
    status["realBatteryCurrentVoltage"] = state.battery_voltage
    status["realBatteryInitialLookupVoltage"] = state.real_battery_initial_lookup_voltage
    status["realBatteryLookupEstimatedSOC"] = state.real_battery_lookup_soc_percent
    status["realBatteryLookupVoltageMin"] = state.real_battery_lookup_voltage_min
    status["realBatteryLookupVoltageMax"] = state.real_battery_lookup_voltage_max

    # Virtual battery model used by the scaled EMS demo.
    status["virtualBatterySOC"] = state.battery_soc
    status["virtualBatteryCharge_mAh"] = state.battery_charge_mah
    status["virtualBatteryCapacity_mAh"] = state.battery_virtual_capacity_mah
    status["virtualBatteryChargeState"] = state.battery_charge_state

    status["h2_volume_mL"] = state.h2_volume_mL
    status["h2_usable_mL"] = state.h2_usable_mL
    status["h2_usable_soc"] = state.h2_usable_soc
    status["h2_mode"] = state.h2_mode

    if not status.get("mode"):
        status["mode"] = f"S{state.scenario}" if state.scenario else "-"

    return {
        "runtime": {
            "clients": state.clients,
            "bridge_ok": state.bridge_ok,
            "last_error": state.last_error,
            "price_zone": state.price_zone,
            "price_source": state.price_source,
            "price_date": state.price_date,
            "last_price_update": state.last_price_update,
            "last_demand_update": state.last_demand_update,
            "ems_enabled": state.ems_enabled,
            "ems_status": state.ems_status,
        },
        "demo": {
            "enabled": state.demo_enabled,
            "running": state.demo_running,
            "cycle": state.demo_cycle,
            "slot_seconds": state.demo_slot_seconds,
            "elapsed_seconds": state.demo_elapsed_seconds,
            "log_file": state.log_file,
            "last_log_update": state.last_log_update,
        },
        "manual": {
            "raw_log_running": state.raw_log_running,
            "raw_log_file": state.raw_log_file,
            "last_raw_log_update": state.last_raw_log_update,
            "raw_log_sample_count": state.raw_log_sample_count,
        },
        "prices": state.prices,
        "price_date": state.price_date,
        "demand_profile": state.demand_profile,
        "live_history": state.live_history,
        "price_threshold": state.price_threshold,
        "current_hour": state.current_hour,
        "current_minute": state.current_minute,
        "current_slot": state.current_slot,
        "current_time_label": state.current_time_label,
        "current_interval_label": state.current_interval_label,
        "current_price": state.current_price,
        "current_demand_mW": state.current_demand_mW,
        "price_state": state.price_state,
        "pv_available": state.pv_available(),
        "ems_enabled": state.ems_enabled,
        "ems_status": state.ems_status,
        "scheduler": {
            "current_decision": state.current_decision,
            "current_command": state.current_command,
            "target_scenario": state.target_scenario,
            "reason": state.reason,
            "last_decision_update": state.last_decision_update,
            "log_file": state.log_file,
            "last_log_update": state.last_log_update,
        },
        "control": {
            "control_mode": state.control_mode,
            "auto_enabled": state.control_mode == "auto",
        },
        "hydrogen": {
            "h2_volume_mL": state.h2_volume_mL,
            "h2_usable_mL": state.h2_usable_mL,
            "h2_usable_soc": state.h2_usable_soc,
            "h2_last_delta_mL": state.h2_last_delta_mL,
            "h2_mode": state.h2_mode,
        },
        "components": state.to_component_state(),
        "arduino_status": status,
    }


def publish_state():
    with state_lock:
        payload = build_payload()

    ui.send_message("telemetry", payload)


def send_telemetry():
    publish_state()


def on_state_request(client_id, data):
    known_clients.add(client_id)

    with state_lock:
        _ensure_optional_state_attributes()
        state.clients = len(known_clients)

    publish_state()


def on_price_control(client_id, data):
    known_clients.add(client_id)

    data = data or {}
    action = data.get("action", "")

    manual_scenario_to_send = None

    with state_lock:
        _ensure_optional_state_attributes()
        state.clients = len(known_clients)

        if action == "refresh":
            state.refresh_requested = True

        elif action == "reset_system":
            state.reset_requested = True

        elif action == "set_zone":
            zone = str(data.get("zone", DEFAULT_PRICE_ZONE)).upper()

            if zone in VALID_PRICE_ZONES:
                state.price_zone = zone
                state.price_mode = "api"
                state.refresh_requested = True
            else:
                state.last_error = "Invalid price zone"

        elif action == "set_price_date":
            price_date = str(data.get("date", state.price_date)).strip()

            if price_date:
                state.price_date = price_date
                state.price_mode = "api"
                state.refresh_requested = True
                state.reason = f"Price test date set to {price_date}."
            else:
                state.last_error = "Invalid price date"

        elif action == "start_ems":
            state.ems_start_requested = True

        elif action == "stop_ems":
            state.ems_stop_requested = True

        elif action == "start_demo":
            state.demo_start_requested = True

        elif action == "restart_demo":
            state.demo_start_requested = True

        elif action == "stop_demo":
            state.demo_stop_requested = True

        elif action == "start_raw_log":
            state.raw_log_start_requested = True

        elif action == "stop_raw_log":
            state.raw_log_stop_requested = True

        elif action == "set_control_mode":
            mode = str(data.get("mode", "manual")).lower()
            state.control_mode = "auto" if mode == "auto" else "manual"

        elif action == "set_manual_scenario":
            try:
                manual_scenario_to_send = int(data.get("scenario", 1))
            except (TypeError, ValueError):
                manual_scenario_to_send = 1

            state.apply_manual_scenario(manual_scenario_to_send)

        elif action == "set_hydrogen_soc":
            try:
                state.set_hydrogen_soc(float(data.get("soc", state.pem_soc)))
                state.reason = "Hydrogen estimation was manually initialised from the WebUI."
            except (TypeError, ValueError):
                state.last_error = "Invalid hydrogen estimation input"

        elif action == "set_battery_soc":
            try:
                state.set_virtual_battery_soc(float(data.get("soc", state.battery_soc)))
                state.reason = "Virtual battery charge state was manually applied from the WebUI."
            except (TypeError, ValueError):
                state.last_error = "Invalid battery charge input"

        elif action == "set_manual_price":
            try:
                manual_price = float(data.get("price", state.current_price))
                state.current_price = manual_price
                state.price_mode = "manual"
                state.price_state = (
                    "HIGH"
                    if manual_price >= state.price_threshold
                    else "LOW"
                )
                state.reason = "Manual electricity price applied from the WebUI."
            except (TypeError, ValueError):
                state.last_error = "Invalid manual price input"

        else:
            state.last_error = f"Unknown UI action: {action}"

    if manual_scenario_to_send is not None:
        from ems_loop import set_manual_scenario

        set_manual_scenario(manual_scenario_to_send)

    publish_state()


def api_status():
    with state_lock:
        return build_payload()


def setup_ui():
    ui.expose_api("GET", "/api/status", api_status)
    ui.on_message("state_request", on_state_request)
    ui.on_message("price_control", on_price_control)