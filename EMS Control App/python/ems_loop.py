"""
File: ems_loop.py

Description:
    This script is part of the bachelor project:
    "Investigation of reversible electrolyzers and implementation of energy
    management control strategies through IoT embedded microcontroller".

    The main control loop for the EMS application. It periodically updates 
    the current price and demand inputs, fetches the latest measurements from 
    the Arduino, runs the scheduling logic to decide on the optimal scenario, 
    sends control commands to the Arduino, and logs the relevant data for analysis.  

Authors:
    Jacob Norman Sørensen
    Matilde Marie Grønkjær Matell

Institution:
    Technical University of Denmark (DTU)

Date:
    2026-05-18
"""

from __future__ import annotations

import csv
import time
from datetime import datetime
from pathlib import Path

from bridge import (
    fetch_arduino_status,
    push_load_trigger_to_mcu,
    push_manual_scenario_to_mcu,
    push_price_to_mcu,
    push_relay_to_mcu,
    push_scenario_to_mcu,
)
from config import (
    DEMO_ENABLED,
    DEMO_SLOT_SECONDS,
    DK_TZ,
    LOOP_SLEEP_SECONDS,
)
from data.price_data.prices import fetch_prices_for_date
from data.variable_load_signal.demand_profile_may import load_demand_profile
from ems_limits import EMS_LIMITS
from ems_state import state, state_lock
from scheduler import SchedulerInputs, decide_scenario
from ui import publish_state


LOG_DIR = Path(__file__).resolve().parent / "logs"

LOG_FIELDS = [
    "real_time",
    "demo_cycle",
    "slot",
    "time_label",
    "interval_label",

    "ems_enabled",
    "ems_status",

    "price_dkk_kwh",
    "price_state",
    "demand_mW",

    "pv_available",
    "target_scenario",
    "actual_scenario",
    "scenario_accepted",
    "reject_reason",
    "scheduler_reason",
    "command",

    "panel_voltage_V",
    "battery_voltage_V",
    "pem_voltage_V",
    "load_voltage_V",

    "pv_current_mA",
    "battery_current_mA",
    "pem_current_mA",
    "load_current_mA",

    "pv_power_mW",
    "battery_power_mW",
    "pem_power_mW",
    "load_power_mW",

    "virtual_battery_soc_percent",
    "virtual_battery_charge_mAh",
    "virtual_battery_capacity_mAh",
    "virtual_battery_charge_state",
    "real_battery_soc_percent",
    "real_battery_charge_mAh",
    "real_battery_capacity_mAh",
    "real_battery_charge_state",
    "real_battery_soc_initialized",
    "real_battery_soc_status",
    "real_battery_initial_lookup_voltage",
    "real_battery_lookup_soc_percent",

    "pem_soc_percent",
    "h2_volume_mL",
    "h2_usable_mL",
    "h2_mode",

    "load_trigger",
]

RAW_LOG_FIELDS = [
    "real_time",
    "ems_enabled",
    "ems_status",
    "demo_running",
    "control_mode",

    "demo_cycle",
    "slot",
    "time_label",
    "interval_label",

    "price_dkk_kwh",
    "price_state",
    "demand_mW",

    "pv_available",
    "target_scenario",
    "actual_scenario",
    "scenario_accepted",
    "reject_reason",
    "arduino_mode",
    "load_trigger",

    "panel_voltage_V",
    "battery_voltage_V",
    "pem_voltage_V",
    "load_voltage_V",

    "pv_current_mA",
    "battery_current_mA",
    "pem_current_mA",
    "load_current_mA",

    "pv_power_mW",
    "battery_power_mW",
    "pem_power_mW",
    "load_power_mW",

    "virtual_battery_soc_percent",
    "virtual_battery_charge_mAh",
    "virtual_battery_capacity_mAh",
    "virtual_battery_charge_state",
    "real_battery_soc_percent",
    "real_battery_charge_mAh",
    "real_battery_capacity_mAh",
    "real_battery_charge_state",
    "real_battery_soc_initialized",
    "real_battery_soc_status",
    "real_battery_initial_lookup_voltage",
    "real_battery_lookup_soc_percent",

    "pem_soc_percent",
    "h2_volume_mL",
    "h2_usable_mL",
    "h2_usable_soc_percent",
    "h2_mode",
    "h2_last_delta_mL",
]

logged_slots = set()


def ensure_ems_attributes():
    """
    Ensure that all expected EMS state attributes exist before logging or UI updates.
    """

    if not hasattr(state, "ems_enabled"):
        state.ems_enabled = False

    if not hasattr(state, "ems_start_requested"):
        state.ems_start_requested = False

    if not hasattr(state, "ems_stop_requested"):
        state.ems_stop_requested = False

    if not hasattr(state, "ems_status"):
        state.ems_status = "standby"

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


def get_now():
    """
    Returns the current date and time.
    """

    return datetime.now(DK_TZ)


def slot_to_time_label(slot):
    """ 
    Convert a slot number in HH:MM format.    
    """

    hour = slot // 4
    minute = (slot % 4) * 15
    return f"{hour:02d}:{minute:02d}"


def slot_to_interval_label(slot):
    """ 
    Convert a slot number to a time interval label in HH:MM-HH:MM format.    
    """

    start_hour = slot // 4
    start_minute = (slot % 4) * 15

    end_hour = start_hour
    end_minute = start_minute + 15

    if end_minute >= 60:
        end_minute = 0
        end_hour = (end_hour + 1) % 24

    return f"{start_hour:02d}:{start_minute:02d}-{end_hour:02d}:{end_minute:02d}"



def make_fallback_prices():
    """
    Returns a fallback price list with a constant price, used when the price fetch fails.
    """

    return [0.50] * 96


def update_demo_time():
    """
    Updates the demo time based on the elapsed time since the demo started.
    """

    if not state.demo_running:
        state.current_time_label = slot_to_time_label(state.current_slot)
        state.current_interval_label = slot_to_interval_label(state.current_slot)
        return

    elapsed = time.monotonic() - state.demo_started_at
    absolute_slot = int(elapsed // state.demo_slot_seconds)

    if absolute_slot >= 96:
        state.demo_elapsed_seconds = state.demo_slot_seconds * 96
        state.demo_cycle = 0
        state.current_slot = 95
        state.current_hour = 23
        state.current_minute = 45
        state.current_time_label = slot_to_time_label(state.current_slot)
        state.current_interval_label = slot_to_interval_label(state.current_slot)
        state.demo_cycle_complete_requested = True
        return

    state.demo_elapsed_seconds = elapsed
    state.demo_cycle = 0
    state.current_slot = absolute_slot
    state.current_hour = state.current_slot // 4
    state.current_minute = (state.current_slot % 4) * 15
    state.current_time_label = slot_to_time_label(state.current_slot)
    state.current_interval_label = slot_to_interval_label(state.current_slot)


def update_current_inputs():
    """
    Updates the current inputs based on the latest available data.
    """
    
    update_demo_time()

    if state.price_mode != "manual":
        if state.prices and len(state.prices) > state.current_slot:
            state.current_price = float(state.prices[state.current_slot])
        else:
            state.current_price = 0.0

    state.update_price_state()
    state.update_current_demand()


def refresh_prices():
    """
    Refreshes the price data for the current date.
    """

    try:
        state.prices = fetch_prices_for_date(
            zone=state.price_zone,
            target_date=state.price_date,
        )
        state.last_error = ""
    except Exception as exc:
        state.prices = make_fallback_prices()
        state.last_error = f"Price fetch failed, using fallback prices: {exc}"

    state.last_price_update = get_now().isoformat(timespec="seconds")


def refresh_demand_profile():
    """
    Refreshes the demand profile data for the current date.
    """

    try:
        state.demand_profile = load_demand_profile()
        state.last_error = ""
    except Exception as exc:
        state.demand_profile = [EMS_LIMITS.demand.min_demand_power_mW] * 96
        state.last_error = f"Demand profile load failed, using fallback demand: {exc}"

    state.last_demand_update = get_now().isoformat(timespec="seconds")


def refresh_inputs():
    """
    Refreshes all input data for the current date.
    """

    refresh_prices()
    refresh_demand_profile()
    update_current_inputs()


def update_state_from_arduino(dt_seconds):
    """
    Updates the state based on the latest data from the Arduino.
    """

    status = fetch_arduino_status()
    state.apply_arduino_status(status)
    state.update_real_battery_from_current(dt_seconds)

    state.update_pv_latch()
    state.update_live_history()

    if state.demo_running and state.ems_enabled:
        state.update_virtual_battery_from_scenario(dt_seconds=dt_seconds)

    state.update_hydrogen_from_current(dt_seconds)


def run_scheduler():
    """
    Runs the scheduler to determine the optimal scenario based on current conditions.
    """

    decision = decide_scenario(
        SchedulerInputs(
            price_state=state.price_state,
            pv_available=state.pv_available(),
            battery_soc=state.battery_soc,
            pem_soc=state.pem_soc,
            battery_voltage_V=state.battery_voltage,
            load_demand_mW=state.current_demand_mW,
        )
    )

    state.apply_scheduler_decision(decision.scenario, decision.reason)


def maybe_send_auto_scenario():
    """
    Sends the auto scenario to the MCU if the conditions are met.
    """
    
    if not state.ems_enabled:
        return

    if state.control_mode != "auto":
        state.apply_manual_mode_decision()
        return

    if not state.demo_running:
        return

    if state.seconds_since_last_switch() < EMS_LIMITS.runtime.min_switch_seconds:
        return

    run_scheduler()

    if state.target_scenario != state.scenario:
        push_scenario_to_mcu(state.current_command)




def write_log_row(path, fieldnames, row):
    """
    Writes a single row of data to the specified log file in CSV format.
    """

    if not path:
        return

    with Path(path).open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writerow(row)

def start_demo_log():
    """
    Initializes the demo log by creating a new CSV file.
    """

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    filename = "ems_demo_{}.csv".format(get_now().strftime("%Y%m%d_%H%M%S"))
    path = LOG_DIR / filename

    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=LOG_FIELDS)
        writer.writeheader()

    state.log_file = str(path)
    state.last_log_update = "Log started at " + get_now().isoformat(timespec="seconds")
    logged_slots.clear()


def start_raw_log():
    """
    Initializes the raw log by creating a new CSV file.
    """

    ensure_ems_attributes()

    if state.raw_log_running:
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    filename = "ems_raw_{}.csv".format(get_now().strftime("%Y%m%d_%H%M%S"))
    path = LOG_DIR / filename

    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=RAW_LOG_FIELDS)
        writer.writeheader()

    state.raw_log_file = str(path)
    state.raw_log_running = True
    state.raw_log_sample_count = 0
    state.last_raw_log_update = "Raw log started at " + get_now().isoformat(timespec="seconds")
    state.reason = "Raw logging started. Demo, EMS mode and load trigger were not changed."


def stop_raw_log():
    """
    Stops the raw log and updates the state.
    """

    ensure_ems_attributes()

    state.raw_log_running = False
    state.last_raw_log_update = "Raw log stopped at " + get_now().isoformat(timespec="seconds")
    state.reason = "Raw logging stopped."


def log_raw_sample():
    """
    Logs a single sample to the raw log file.
    """

    ensure_ems_attributes()

    if not state.raw_log_running:
        return

    if not state.raw_log_file:
        return

    status = state.arduino_status or {}

    row = {
        "real_time": get_now().isoformat(timespec="seconds"),
        "ems_enabled": state.ems_enabled,
        "ems_status": state.ems_status,
        "demo_running": state.demo_running,
        "control_mode": state.control_mode,

        "demo_cycle": state.demo_cycle,
        "slot": state.current_slot,
        "time_label": state.current_time_label,
        "interval_label": state.current_interval_label,

        "price_dkk_kwh": state.current_price,
        "price_state": state.price_state,
        "demand_mW": state.current_demand_mW,

        "pv_available": state.pv_available(),
        "target_scenario": state.target_scenario,
        "actual_scenario": state.scenario,
        "scenario_accepted": status.get("scenarioAccepted", ""),
        "reject_reason": status.get("lastRejectReason", status.get("lastError", "")),
        "arduino_mode": status.get("mode", ""),
        "load_trigger": status.get("loadTrigger", ""),

        "panel_voltage_V": status.get("panelVoltage", ""),
        "battery_voltage_V": status.get("batteryVoltage", ""),
        "pem_voltage_V": status.get("pemrfcVoltage", ""),
        "load_voltage_V": status.get("loadVoltage", ""),

        "pv_current_mA": state.pv_current,
        "battery_current_mA": state.battery_current,
        "pem_current_mA": state.pem_current,
        "load_current_mA": state.load_current,

        "pv_power_mW": state.pv_power,
        "battery_power_mW": state.battery_power,
        "pem_power_mW": state.pem_power,
        "load_power_mW": state.load_power,

        "virtual_battery_soc_percent": state.battery_soc,
        "virtual_battery_charge_mAh": state.battery_charge_mah,
        "virtual_battery_capacity_mAh": state.battery_virtual_capacity_mah,
        "virtual_battery_charge_state": state.battery_charge_state,
        "real_battery_soc_percent": state.real_battery_soc,
        "real_battery_charge_mAh": state.real_battery_charge_mAh,
        "real_battery_capacity_mAh": state.real_battery_capacity_mAh,
        "real_battery_charge_state": state.real_battery_charge_state,
        "real_battery_soc_initialized": state.real_battery_soc_initialized,
        "real_battery_soc_status": state.real_battery_soc_status,
        "real_battery_initial_lookup_voltage": state.real_battery_initial_lookup_voltage,
        "real_battery_lookup_soc_percent": state.real_battery_lookup_soc_percent,

        "pem_soc_percent": state.pem_soc,
        "h2_volume_mL": state.h2_volume_mL,
        "h2_usable_mL": state.h2_usable_mL,
        "h2_usable_soc_percent": state.h2_usable_soc,
        "h2_mode": state.h2_mode,
        "h2_last_delta_mL": state.h2_last_delta_mL,
    }

    write_log_row(state.raw_log_file, RAW_LOG_FIELDS, row)

    state.raw_log_sample_count += 1
    state.last_raw_log_update = get_now().isoformat(timespec="seconds")


def handle_raw_log_requests():
    """
    Handles requests to start or stop the raw log.
    """

    ensure_ems_attributes()

    if state.raw_log_start_requested:
        state.raw_log_start_requested = False
        start_raw_log()

    if state.raw_log_stop_requested:
        state.raw_log_stop_requested = False
        stop_raw_log()



def reset_system_to_initial_state():
    """
    Reset the EMS/UI state to a safe initial state.
    """

    state.ems_enabled = False
    state.ems_status = "standby"
    state.ems_start_requested = False
    state.ems_stop_requested = False

    state.demo_running = False
    state.demo_start_requested = False
    state.demo_stop_requested = False
    state.demo_enabled = DEMO_ENABLED
    state.demo_slot_seconds = DEMO_SLOT_SECONDS
    state.demo_started_at = time.monotonic()
    state.demo_elapsed_seconds = 0.0
    state.demo_cycle = 0
    state.demo_cycle_complete_requested = False
    state.current_slot = 0
    state.current_hour = 0
    state.current_minute = 0
    state.current_time_label = "00:00"
    state.current_interval_label = "00:00-00:15"

    state.raw_log_running = False
    state.raw_log_start_requested = False
    state.raw_log_stop_requested = False
    state.raw_log_file = ""
    state.raw_log_sample_count = 0
    state.last_raw_log_update = ""

    state.log_file = ""
    state.last_log_update = ""
    logged_slots.clear()
    state.reset_live_history()

    state.price_mode = "api"
    state.current_price = 0.0

    state.pv_mode = "auto"
    state.pv_latched_available = False
    state.pv_low_power_since = None

    state.control_mode = "auto"
    state.target_scenario = 1
    state.last_scenario = state.scenario
    state.current_command = ""
    state.current_decision = {}
    state.last_decision_update = ""
    state.last_scenario_change_monotonic = time.monotonic()

    state.set_virtual_battery_soc(50.0)

    state.reason = (
        "EMS reset to initial safe state. Demo, logs, plot history and virtual "
        "battery estimate were reset. Selected price date and PEM state were preserved. "
        "The Arduino was requested to return to S1."
    )
    state.last_error = ""

    refresh_inputs()

    try:
        push_load_trigger_to_mcu(False)
        push_price_to_mcu()
        push_manual_scenario_to_mcu("SCENARIO,1")
        state.reset_real_battery_soc_estimator()
        state.apply_arduino_status(fetch_arduino_status())
        state.update_real_battery_from_current(0.0)
        state.bridge_ok = True
    except Exception as exc:
        state.bridge_ok = False
        state.last_error = f"EMS reset error: {exc}"


def start_ems():
    """
    Starts the EMS system and applies state based on the Arduino status.
    """

    state.ems_enabled = True
    state.ems_status = "running"
    state.control_mode = "manual"

    update_current_inputs()

    state.apply_manual_scenario(1)
    state.reason = (
        "EMS system started from the WebUI. "
        "System is in manual standby using S1 until demo or auto mode is started."
    )

    try:
        push_load_trigger_to_mcu(False)
        push_price_to_mcu()
        push_manual_scenario_to_mcu("SCENARIO,1")
    
        state.reset_real_battery_soc_estimator()
        state.apply_arduino_status(fetch_arduino_status())
        state.update_real_battery_from_current(0.0)
        state.bridge_ok = True
    
    except Exception as exc:
        state.bridge_ok = False
        state.last_error = f"EMS reset error: {exc}"


def stop_ems():
    """
    Stops the EMS system and applies safe standby scenario.
    """

    state.ems_enabled = False
    state.ems_status = "standby"

    state.demo_running = False
    state.demo_start_requested = False
    state.demo_stop_requested = False

    state.control_mode = "manual"
    update_current_inputs()

    state.apply_manual_scenario(1)
    state.reason = (
        "EMS system stopped from the WebUI. "
        "Automatic scheduling, demo logging and load trigger are disabled. "
        "System is moved to safe standby S1."
    )

    try:
        push_load_trigger_to_mcu(False)
        push_manual_scenario_to_mcu("SCENARIO,1")
        state.apply_arduino_status(fetch_arduino_status())
        state.bridge_ok = True
    except Exception as exc:
        state.bridge_ok = False
        state.last_error = f"EMS stop error: {exc}"


def start_demo():
    """
    Starts the demo and logging.
    """

    if not state.ems_enabled:
        state.demo_running = False
        state.reason = "Start EMS system before starting the demo."
        state.last_error = "Demo was not started because EMS system is in standby."
        return

    state.demo_enabled = DEMO_ENABLED
    state.demo_running = True
    state.demo_slot_seconds = DEMO_SLOT_SECONDS
    state.demo_started_at = time.monotonic()
    state.demo_elapsed_seconds = 0.0
    state.demo_cycle = 0
    state.demo_cycle_complete_requested = False
    state.current_slot = 0
    state.current_hour = 0
    state.current_minute = 0
    state.current_time_label = "00:00"
    state.current_interval_label = "00:00-00:15"

    state.reset_live_history()
    logged_slots.clear()

    state.reason = (
        "Demo logging started. Hydrogen state was not reset; "
        "the current estimated hydrogen state is used."
    )

    try:
        push_load_trigger_to_mcu(True)
    except Exception as exc:
        state.bridge_ok = False
        state.last_error = f"Could not start variable load trigger: {exc}"

    start_demo_log()


def stop_demo():
    """
    Stops the demo and logging.
    """

    state.demo_running = False
    state.last_log_update = "Demo stopped at " + get_now().isoformat(timespec="seconds")

    try:
        push_load_trigger_to_mcu(False)
    except Exception as exc:
        state.bridge_ok = False
        state.last_error = f"Could not stop variable load trigger: {exc}"


def complete_demo_cycle():
    """
    Completes the demo cycle, resets the state, and applying safe standby scenario.
    """
    state.demo_running = False
    state.demo_start_requested = False
    state.demo_stop_requested = False
    state.demo_cycle_complete_requested = False

    state.apply_manual_scenario(1)
    state.reason = (
        "One 96-slot demo cycle was completed. Demo logging was stopped, "
        "the variable load trigger was disabled, and the system was returned to safe S1."
    )
    state.last_log_update = "Demo cycle completed at " + get_now().isoformat(timespec="seconds")

    try:
        push_load_trigger_to_mcu(False)
        push_price_to_mcu()
        push_manual_scenario_to_mcu("SCENARIO,1")
        state.apply_arduino_status(fetch_arduino_status())
        state.bridge_ok = True
    except Exception as exc:
        state.bridge_ok = False
        state.last_error = f"Demo cycle completion error: {exc}"


def log_current_slot():
    """
    Logs the current slot information to the log file.
    """

    if not state.demo_running:
        return

    if not state.log_file:
        return

    if not state.current_decision:
        return

    key = (state.demo_cycle, state.current_slot)

    if key in logged_slots:
        return

    status = state.arduino_status or {}

    row = {
        "real_time": get_now().isoformat(timespec="seconds"),
        "demo_cycle": state.demo_cycle,
        "slot": state.current_slot,
        "time_label": state.current_time_label,
        "interval_label": state.current_interval_label,

        "ems_enabled": state.ems_enabled,
        "ems_status": state.ems_status,

        "price_dkk_kwh": state.current_price,
        "price_state": state.price_state,
        "demand_mW": state.current_demand_mW,

        "pv_available": state.pv_available(),
        "target_scenario": state.target_scenario,
        "actual_scenario": state.scenario,
        "scenario_accepted": status.get("scenarioAccepted", ""),
        "reject_reason": status.get("lastRejectReason", status.get("lastError", "")),
        "scheduler_reason": state.reason,
        "command": state.current_command,

        "panel_voltage_V": status.get("panelVoltage", ""),
        "battery_voltage_V": status.get("batteryVoltage", ""),
        "pem_voltage_V": status.get("pemrfcVoltage", ""),
        "load_voltage_V": status.get("loadVoltage", ""),

        "pv_current_mA": state.pv_current,
        "battery_current_mA": state.battery_current,
        "pem_current_mA": state.pem_current,
        "load_current_mA": state.load_current,

        "pv_power_mW": state.pv_power,
        "battery_power_mW": state.battery_power,
        "pem_power_mW": state.pem_power,
        "load_power_mW": state.load_power,

        "virtual_battery_soc_percent": state.battery_soc,
        "virtual_battery_charge_mAh": state.battery_charge_mah,
        "virtual_battery_capacity_mAh": state.battery_virtual_capacity_mah,
        "virtual_battery_charge_state": state.battery_charge_state,
        "real_battery_soc_percent": state.real_battery_soc,
        "real_battery_charge_mAh": state.real_battery_charge_mAh,
        "real_battery_capacity_mAh": state.real_battery_capacity_mAh,
        "real_battery_charge_state": state.real_battery_charge_state,
        "real_battery_soc_initialized": state.real_battery_soc_initialized,
        "real_battery_soc_status": state.real_battery_soc_status,
        "real_battery_initial_lookup_voltage": state.real_battery_initial_lookup_voltage,
        "real_battery_lookup_soc_percent": state.real_battery_lookup_soc_percent,

        "pem_soc_percent": state.pem_soc,
        "h2_volume_mL": state.h2_volume_mL,
        "h2_usable_mL": state.h2_usable_mL,
        "h2_mode": state.h2_mode,

        "load_trigger": status.get("loadTrigger", ""),
    }

    write_log_row(state.log_file, LOG_FIELDS, row)

    logged_slots.add(key)
    state.last_log_update = get_now().isoformat(timespec="seconds")



def handle_reset_requests():
    """
    Handles requests to reset the EMS system to the initial safe state.
    """

    ensure_ems_attributes()

    if state.reset_requested:
        state.reset_requested = False
        reset_system_to_initial_state()
        return True

    return False


def handle_ems_requests():
    """
    Handles requests to start or stop the EMS system.
    """

    if state.ems_stop_requested:
        state.ems_stop_requested = False
        stop_ems()
        return

    if state.ems_start_requested:
        state.ems_start_requested = False
        start_ems()


def handle_demo_requests():
    """
    Handles requests to start or stop the demo.
    """

    if state.demo_start_requested:
        state.demo_start_requested = False
        start_demo()

    if state.demo_stop_requested:
        state.demo_stop_requested = False
        stop_demo()


def ems_loop():
    """
    The main loop of the EMS application. 
    It periodically updates inputs, fetches data from the Arduino, 
    runs the scheduler, sends commands to the Arduino, and logs data.
    """ 

    ensure_ems_attributes()

    state.demo_enabled = DEMO_ENABLED
    state.demo_running = False
    state.demo_slot_seconds = DEMO_SLOT_SECONDS
    state.demo_started_at = time.monotonic()

    state.ems_enabled = False
    state.ems_status = "standby"

    last_update_time = time.monotonic()

    with state_lock:
        refresh_inputs()

    while True:
        now = time.monotonic()
        dt_seconds = now - last_update_time
        last_update_time = now

        try:
            with state_lock:
                ensure_ems_attributes()

                if handle_reset_requests():
                    publish_state()
                    time.sleep(LOOP_SLEEP_SECONDS)
                    continue
                
                handle_ems_requests()
                handle_demo_requests()
                handle_raw_log_requests()
                
                if state.refresh_requested:
                    refresh_inputs()
                    state.reset_live_history()
                    state.refresh_requested = False

                update_current_inputs()
                update_state_from_arduino(dt_seconds)
                log_raw_sample()

                if state.ems_enabled:
                    push_price_to_mcu()

                maybe_send_auto_scenario()
                log_current_slot()

                if state.demo_cycle_complete_requested:
                    complete_demo_cycle()
                else:
                    state.bridge_ok = True

        except Exception as exc:
            with state_lock:
                state.bridge_ok = False
                state.last_error = f"EMS loop error: {exc}"

        publish_state()
        time.sleep(LOOP_SLEEP_SECONDS)


def set_manual_scenario(scenario):
    """
    Sets the manual scenario for the EMS system.
    """

    with state_lock:
        ensure_ems_attributes()

        if not state.ems_enabled:
            state.reason = "Start EMS system before selecting manual scenarios."
            state.last_error = "Manual scenario was blocked because EMS system is in standby."
            return

        update_current_inputs()
        state.apply_manual_scenario(scenario)

        try:
            push_price_to_mcu()
            push_manual_scenario_to_mcu(state.current_command)
            state.apply_arduino_status(fetch_arduino_status())
            state.bridge_ok = True
        except Exception as exc:
            state.bridge_ok = False
            state.last_error = f"Manual scenario error: {exc}"


def set_manual_relay(relay, output_state):
    """
    Sets the manual relay state for the EMS system.
    """
    
    with state_lock:
        ensure_ems_attributes()

        if not state.ems_enabled:
            state.reason = "Start EMS system before using manual relay control."
            state.last_error = "Manual relay control was blocked because EMS system is in standby."
            return

        state.control_mode = "manual"
        update_current_inputs()

        try:
            push_relay_to_mcu(relay, output_state)
            state.apply_arduino_status(fetch_arduino_status())
            state.bridge_ok = True
        except Exception as exc:
            state.bridge_ok = False
            state.last_error = f"Manual relay error: {exc}"