from __future__ import annotations

import threading
import time
from datetime import datetime

from config import DEFAULT_PRICE_ZONE, DK_TZ, PRICE_SOURCE
from ems_limits import EMS_LIMITS


def _as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def _scenario_from_mode(mode):
    text = str(mode or "")

    for scenario in range(1, 7):
        if f"S{scenario}" in text:
            return scenario

    return 0


def _empty_live_history():
    return {
        "cycle": 0,
        "pv_power_mW": [None] * 96,
        "battery_power_mW": [None] * 96,
        "pem_power_mW": [None] * 96,
        "load_power_mW": [None] * 96,
        "scenario": [None] * 96,
    }


def _h2_usable_range_mL():
    return EMS_LIMITS.pem.h2_max_mL - EMS_LIMITS.pem.h2_min_usable_mL


def _h2_volume_from_soc(soc_percent):
    soc_fraction = _clamp(float(soc_percent), 0.0, 100.0) / 100.0

    return EMS_LIMITS.pem.h2_min_usable_mL + soc_fraction * _h2_usable_range_mL()


def _h2_soc_from_volume(h2_volume_mL):
    usable_range = _h2_usable_range_mL()

    if usable_range <= 0:
        return 0.0

    soc_percent = (
        (h2_volume_mL - EMS_LIMITS.pem.h2_min_usable_mL)
        / usable_range
    ) * 100.0

    return _clamp(soc_percent, 0.0, 100.0)


def _virtual_battery_capacity_mAh():
    return EMS_LIMITS.battery.demo_capacity_mAh


def _virtual_battery_voltage_for_current(battery_voltage=0.0):
    voltage = _as_float(battery_voltage, EMS_LIMITS.battery.demo_nominal_voltage_V)

    if voltage <= 0.1:
        return EMS_LIMITS.battery.demo_nominal_voltage_V

    return voltage


BATTERY_SOC_LOOKUP_POINTS = (
    (0.0, 0.5 * (3.2256 + 3.03315)),
    (2.0, 0.5 * (3.5411 + 3.5124)),
    (5.0, 0.5 * (3.70655 + 3.7214)),
    (10.0, 0.5 * (3.7299 + 3.7698)),
    (15.0, 0.5 * (3.7669 + 3.8077)),
    (20.0, 0.5 * (3.7970 + 3.8366)),
    (30.0, 0.5 * (3.82345 + 3.8655)),
    (40.0, 0.5 * (3.8521 + 3.8890)),
    (50.0, 0.5 * (3.8974 + 3.9229)),
    (60.0, 0.5 * (3.9507 + 3.9803)),
    (70.0, 0.5 * (4.0195 + 4.0560)),
    (80.0, 0.5 * (4.1133 + 4.1396)),
    (90.0, 0.5 * (4.21845 + 4.2348)),
    (95.0, 0.5 * (4.2793 + 4.2858)),
    (98.0, 0.5 * (4.3194 + 4.3210)),
    (100.0, 0.5 * (4.3463 + 4.35825)),
)


def _real_battery_capacity_mAh():
    return EMS_LIMITS.battery.real_capacity_mAh


def _estimate_real_battery_soc_from_voltage(voltage):
    voltage = _as_float(voltage, None)

    if voltage is None:
        return None

    first_soc, first_voltage = BATTERY_SOC_LOOKUP_POINTS[0]
    last_soc, last_voltage = BATTERY_SOC_LOOKUP_POINTS[-1]

    if voltage < first_voltage or voltage > last_voltage:
        return None

    if voltage == first_voltage:
        return first_soc

    if voltage == last_voltage:
        return last_soc

    for (soc0, v0), (soc1, v1) in zip(
        BATTERY_SOC_LOOKUP_POINTS,
        BATTERY_SOC_LOOKUP_POINTS[1:],
    ):
        if v0 <= voltage <= v1:
            if abs(v1 - v0) < 1e-9:
                return soc0

            fraction = (voltage - v0) / (v1 - v0)
            return soc0 + fraction * (soc1 - soc0)

    return first_soc


def _real_battery_voltage_inside_lookup_range(voltage):
    voltage = _as_float(voltage, None)

    if voltage is None:
        return False

    return BATTERY_SOC_LOOKUP_POINTS[0][1] <= voltage <= BATTERY_SOC_LOOKUP_POINTS[-1][1]


def _real_battery_charge_state(soc_percent, initialized=True):
    if not initialized:
        return "waiting_for_initial_soc"

    if soc_percent <= 10.0:
        return "empty"

    if soc_percent <= 30.0:
        return "low"

    if soc_percent <= 70.0:
        return "medium"

    if soc_percent <= 90.0:
        return "high"

    return "full"


class EMSState:
    def __init__(self):
        self.prices = []
        self.price_mode = "api"
        self.price_state = "LOW"
        self.price_threshold = EMS_LIMITS.price.high_price_min_DKK_per_kWh
        self.price_zone = DEFAULT_PRICE_ZONE
        self.price_source = PRICE_SOURCE
        self.price_date = datetime.now(DK_TZ).date().isoformat()
        self.current_price = 0.0
        self.current_hour = 0
        self.current_minute = 0
        self.current_slot = 0
        self.current_time_label = "00:00"
        self.current_interval_label = "00:00-00:15"
        self.last_price_update = ""

        self.demo_enabled = True
        self.demo_running = False
        self.demo_cycle = 0
        self.demo_slot_seconds = 7.5
        self.demo_elapsed_seconds = 0.0
        self.demo_started_at = time.monotonic()

        self.demo_start_requested = False
        self.demo_stop_requested = False
        self.demo_cycle_complete_requested = False

        self.ems_enabled = False
        self.ems_start_requested = False
        self.ems_stop_requested = False
        self.ems_status = "standby"

        self.log_file = ""
        self.last_log_update = ""

        self.live_history = _empty_live_history()

        self.demand_profile = []
        self.current_demand_mW = 0.0
        self.current_demand_w = 0.0
        self.last_demand_update = ""

        self.panel_voltage = 0.0
        self.battery_voltage = 0.0
        self.load_voltage = 0.0
        self.pem_voltage = 0.0

        self.pv_current = 0.0
        self.load_current = 0.0
        self.pem_current = 0.0
        self.battery_current = 0.0

        self.pv_power = 0.0
        self.load_power = 0.0
        self.pem_power = 0.0
        self.battery_power = 0.0

        self.pv_mode = "auto"
        self.pv_latched_available = False
        self.pv_low_power_since = None

        self.control_mode = "auto"
        self.mode = ""
        self.scenario = 0
        self.target_scenario = 1
        self.last_scenario = 0
        self.last_scenario_change_monotonic = time.monotonic()

        self.current_decision = {}
        self.current_command = ""
        self.reason = "Automatic EMS mode enabled."
        self.last_decision_update = ""

        self.bridge_ok = None
        self.last_error = ""
        self.clients = 0
        self.arduino_status = {}

        # Virtual battery state used by the short EMS demo.
        # The EMS battery model is now handled in mAh and updated with real
        # elapsed seconds, not accelerated demo time.
        self.battery_soc = 50.0
        self.battery_virtual_capacity_mah = _virtual_battery_capacity_mAh()
        self.battery_charge_mah = self.battery_virtual_capacity_mah * self.battery_soc / 100.0
        self.battery_charge_state = "medium"

        # Backwards-compatible derived values. They are not used as the primary
        # battery state, but keeping them avoids breaking older UI/log code.
        self.battery_energy_mWh = 0.0
        self.battery_energy_wh = 0.0
        self.battery_virtual_capacity_mWh = 0.0

        # Real physical battery estimate. This is now owned by Python, not the
        # Arduino sketch. The Arduino only supplies voltage/current/power I/O.
        self.real_battery_soc = 0.0
        self.real_battery_charge_mAh = 0.0
        self.real_battery_capacity_mAh = _real_battery_capacity_mAh()
        self.real_battery_charge_state = "waiting_for_initial_soc"
        self.real_battery_soc_initialized = False
        self.real_battery_soc_status = "waiting_for_initial_soc"
        self.real_battery_initial_lookup_voltage = None
        self.real_battery_lookup_soc_percent = None
        self.real_battery_lookup_voltage_min = BATTERY_SOC_LOOKUP_POINTS[0][1]
        self.real_battery_lookup_voltage_max = BATTERY_SOC_LOOKUP_POINTS[-1][1]
        self.real_battery_last_update_monotonic = None

        # Backwards-compatible real battery energy estimate.
        self.real_battery_energy_wh = 0.0

        self.pem_soc = 0.0
        self.h2_volume_mL = _h2_volume_from_soc(self.pem_soc)
        self.h2_usable_mL = self.h2_volume_mL - EMS_LIMITS.pem.h2_min_usable_mL
        self.h2_usable_soc = self.pem_soc
        self.h2_last_delta_mL = 0.0
        self.h2_mode = "empty"

        self.refresh_requested = False
        self.reset_requested = False

        self.sync_virtual_battery_state()
        self.sync_hydrogen_state()

    def apply_arduino_status(self, status):
        self.arduino_status = status or {}

        self.panel_voltage = _as_float(self.arduino_status.get("panelVoltage"))
        self.battery_voltage = _as_float(self.arduino_status.get("batteryVoltage"))
        self.load_voltage = _as_float(self.arduino_status.get("loadVoltage"))

        self.pem_voltage = _as_float(
            self.arduino_status.get(
                "pemrfcVoltage",
                self.arduino_status.get("PEMvoltage", 0.0),
            )
        )

        # Arduino still reports its original raw fields in A and W for
        # backwards compatibility. The Python EMS converts and stores all
        # currents in mA and powers in mW.
        self.pv_current = _as_float(
            self.arduino_status.get("PVcurrent_mA"),
            _as_float(self.arduino_status.get("PVcurrent")) * 1000.0,
        )
        self.load_current = _as_float(
            self.arduino_status.get("Loadcurrent_mA"),
            _as_float(self.arduino_status.get("Loadcurrent")) * 1000.0,
        )
        self.pem_current = _as_float(
            self.arduino_status.get("PEMcurrent_mA"),
            _as_float(self.arduino_status.get("PEMcurrent")) * 1000.0,
        )
        self.battery_current = _as_float(
            self.arduino_status.get("Batcurrent_mA"),
            _as_float(self.arduino_status.get("Batcurrent")) * 1000.0,
        )

        self.pv_power = _as_float(
            self.arduino_status.get("PVpower_mW"),
            _as_float(self.arduino_status.get("PVpower")) * 1000.0,
        )
        self.load_power = _as_float(
            self.arduino_status.get("Loadpower_mW"),
            _as_float(self.arduino_status.get("Loadpower")) * 1000.0,
        )
        self.pem_power = _as_float(
            self.arduino_status.get("PEMpower_mW"),
            _as_float(self.arduino_status.get("PEMpower")) * 1000.0,
        )
        self.battery_power = _as_float(
            self.arduino_status.get("Batterypower_mW"),
            _as_float(self.arduino_status.get("Batterypower")) * 1000.0,
        )

        self.real_battery_capacity_mAh = _real_battery_capacity_mAh()
        self.real_battery_lookup_soc_percent = _estimate_real_battery_soc_from_voltage(
            self.battery_voltage
        )
        self.real_battery_lookup_voltage_min = BATTERY_SOC_LOOKUP_POINTS[0][1]
        self.real_battery_lookup_voltage_max = BATTERY_SOC_LOOKUP_POINTS[-1][1]

        self.mode = str(self.arduino_status.get("mode", ""))

        scenario = _scenario_from_mode(self.mode)

        if not scenario:
            scenario = int(_as_float(
                self.arduino_status.get(
                    "activeScenario",
                    self.arduino_status.get("active_scenario", 0),
                ),
                0,
            ))

        if scenario and scenario != self.scenario:
            self.last_scenario = self.scenario
            self.scenario = scenario
            self.last_scenario_change_monotonic = time.monotonic()

    def update_current_demand(self):
        if self.demand_profile and len(self.demand_profile) > self.current_slot:
            self.current_demand_mW = _as_float(self.demand_profile[self.current_slot])
        else:
            self.current_demand_mW = EMS_LIMITS.demand.min_demand_power_mW

        self.current_demand_w = self.current_demand_mW / 1000.0

    def update_price_state(self):
        if self.price_mode == "manual":
            return

        self.price_state = (
            "HIGH"
            if self.current_price >= self.price_threshold
            else "LOW"
        )

    def update_pv_latch(self):
        now = time.monotonic()

        if self.pv_mode == "force_available":
            self.pv_latched_available = True
            self.pv_low_power_since = None
            return

        if self.pv_mode == "force_unavailable":
            self.pv_latched_available = False
            self.pv_low_power_since = None
            return

        if not self.pv_latched_available:
            self.pv_latched_available = (
                self.panel_voltage > EMS_LIMITS.pv.min_voltage_for_use_V
            )
            self.pv_low_power_since = None
            return

        if self.pv_power < EMS_LIMITS.pv.min_power_for_available_mW:
            if self.pv_low_power_since is None:
                self.pv_low_power_since = now
                return

            if now - self.pv_low_power_since >= EMS_LIMITS.pv.latch_off_delay_seconds:
                self.pv_latched_available = False
                self.pv_low_power_since = None
        else:
            self.pv_low_power_since = None

    def pv_available(self):
        return bool(self.pv_latched_available)

    def seconds_since_last_switch(self):
        return max(0.0, time.monotonic() - self.last_scenario_change_monotonic)

    def reset_live_history(self):
        self.live_history = _empty_live_history()
        self.live_history["cycle"] = self.demo_cycle

    def update_live_history(self):
        if not self.live_history or self.live_history.get("cycle") != self.demo_cycle:
            self.reset_live_history()

        slot = max(0, min(95, int(self.current_slot)))
        scenario = self.scenario or self.target_scenario

        self.live_history["pv_power_mW"][slot] = self.pv_power
        self.live_history["battery_power_mW"][slot] = self.battery_power
        self.live_history["pem_power_mW"][slot] = self.pem_power
        self.live_history["load_power_mW"][slot] = self.load_power
        self.live_history["scenario"][slot] = scenario

    def sync_virtual_battery_state(self):
        capacity_mAh = _virtual_battery_capacity_mAh()
        self.battery_virtual_capacity_mah = capacity_mAh

        self.battery_charge_mah = _clamp(
            self.battery_charge_mah,
            0.0,
            capacity_mAh,
        )

        if capacity_mAh > 0:
            self.battery_soc = 100.0 * self.battery_charge_mah / capacity_mAh
        else:
            self.battery_soc = 0.0

        # Derived values kept only for compatibility with older code. The EMS
        # battery state itself is expressed in mAh.
        voltage = _virtual_battery_voltage_for_current(self.battery_voltage)
        self.battery_energy_mWh = self.battery_charge_mah * voltage
        self.battery_energy_wh = self.battery_energy_mWh / 1000.0
        self.battery_virtual_capacity_mWh = capacity_mAh * voltage

        if self.battery_soc <= EMS_LIMITS.battery.min_soc_discharge_percent:
            self.battery_charge_state = "empty"
        elif self.battery_soc <= 30.0:
            self.battery_charge_state = "low"
        elif self.battery_soc < EMS_LIMITS.battery.full_soc_control_percent:
            self.battery_charge_state = "medium"
        else:
            self.battery_charge_state = "control_full"

    def update_virtual_battery_from_scenario(self, dt_seconds):
        if dt_seconds <= 0:
            return

        dt_hours = dt_seconds / 3600.0
        delta_charge_mAh = 0.0
        scenario_in_effect = self.scenario or self.target_scenario
        voltage = _virtual_battery_voltage_for_current(self.battery_voltage)

        if scenario_in_effect == 2:
            measured_pv_power_mW = max(0.0, self.pv_power)

            charge_power_mW = max(
                EMS_LIMITS.demand.min_demand_power_mW,
                min(measured_pv_power_mW, EMS_LIMITS.demand.max_demand_power_mW),
            )

            charge_current_mA = charge_power_mW / voltage
            delta_charge_mAh = charge_current_mA * dt_hours

        elif scenario_in_effect == 5:
            discharge_power_mW = max(
                EMS_LIMITS.demand.min_demand_power_mW,
                min(self.current_demand_mW, EMS_LIMITS.demand.max_demand_power_mW),
            )

            discharge_current_mA = discharge_power_mW / voltage
            delta_charge_mAh = -discharge_current_mA * dt_hours

        self.battery_charge_mah += delta_charge_mAh
        self.sync_virtual_battery_state()

    def set_virtual_battery_soc(self, soc_percent):
        capacity_mAh = _virtual_battery_capacity_mAh()
        soc = _clamp(float(soc_percent), 0.0, 100.0)

        self.battery_soc = soc
        self.battery_charge_mah = capacity_mAh * soc / 100.0

        self.sync_virtual_battery_state()

    def sync_real_battery_state(self):
        capacity_mAh = _real_battery_capacity_mAh()
        self.real_battery_capacity_mAh = capacity_mAh

        self.real_battery_charge_mAh = _clamp(
            _as_float(self.real_battery_charge_mAh, 0.0),
            0.0,
            capacity_mAh,
        )

        if capacity_mAh > 0.0:
            self.real_battery_soc = 100.0 * self.real_battery_charge_mAh / capacity_mAh
        else:
            self.real_battery_soc = 0.0

        voltage = _virtual_battery_voltage_for_current(self.battery_voltage)
        self.real_battery_energy_wh = (self.real_battery_charge_mAh / 1000.0) * voltage
        self.real_battery_charge_state = _real_battery_charge_state(
            self.real_battery_soc,
            self.real_battery_soc_initialized,
        )

    def reset_real_battery_soc_estimator(self):
        self.real_battery_soc = 0.0
        self.real_battery_charge_mAh = 0.0
        self.real_battery_capacity_mAh = _real_battery_capacity_mAh()
        self.real_battery_charge_state = "waiting_for_initial_soc"
        self.real_battery_soc_initialized = False
        self.real_battery_soc_status = "waiting_for_initial_soc"
        self.real_battery_initial_lookup_voltage = None
        self.real_battery_lookup_soc_percent = None
        self.real_battery_lookup_voltage_min = BATTERY_SOC_LOOKUP_POINTS[0][1]
        self.real_battery_lookup_voltage_max = BATTERY_SOC_LOOKUP_POINTS[-1][1]
        self.real_battery_last_update_monotonic = None
        self.real_battery_energy_wh = 0.0

    def initialize_real_battery_from_lookup(self):
        lookup_soc = _estimate_real_battery_soc_from_voltage(self.battery_voltage)

        if lookup_soc is None:
            self.real_battery_soc_status = "waiting_for_valid_battery_voltage"
            self.real_battery_charge_state = "waiting_for_valid_battery_voltage"
            return False

        self.real_battery_initial_lookup_voltage = self.battery_voltage
        self.real_battery_lookup_soc_percent = lookup_soc
        self.real_battery_soc_initialized = True
        self.real_battery_soc_status = "initialised_from_python_lookup_table"
        self.real_battery_charge_mAh = _real_battery_capacity_mAh() * lookup_soc / 100.0
        self.sync_real_battery_state()
        return True

    def update_real_battery_from_current(self, dt_seconds):
        self.real_battery_lookup_soc_percent = _estimate_real_battery_soc_from_voltage(
            self.battery_voltage
        )

        if not self.real_battery_soc_initialized:
            if not _real_battery_voltage_inside_lookup_range(self.battery_voltage):
                self.real_battery_soc_status = "waiting_for_voltage_in_lookup_range"
                self.real_battery_charge_state = self.real_battery_soc_status
                return

            if not self.initialize_real_battery_from_lookup():
                return

        if dt_seconds <= 0:
            self.sync_real_battery_state()
            return

        dt_hours = dt_seconds / 3600.0
        self.real_battery_charge_mAh += self.battery_current * dt_hours
        self.real_battery_soc_status = "python_current_integrated_after_lookup_initialisation"
        self.sync_real_battery_state()

    def sync_hydrogen_state(self):
        self.h2_volume_mL = _clamp(
            self.h2_volume_mL,
            EMS_LIMITS.pem.h2_min_usable_mL,
            EMS_LIMITS.pem.h2_max_mL,
        )

        self.h2_usable_mL = max(
            0.0,
            self.h2_volume_mL - EMS_LIMITS.pem.h2_min_usable_mL,
        )

        self.h2_usable_soc = _h2_soc_from_volume(self.h2_volume_mL)
        self.pem_soc = self.h2_usable_soc

    def update_hydrogen_from_current(self, dt_seconds):
        if dt_seconds <= 0:
            return

        old_h2_volume = self.h2_volume_mL
        delta_h2_mL = 0.0

        if self.pem_current > EMS_LIMITS.pem.charge_current_threshold_mA:
            charge_C = (self.pem_current / 1000.0) * dt_seconds
            delta_h2_mL = charge_C * EMS_LIMITS.pem.h2_charge_mL_per_C
            self.h2_mode = "charging"

        elif self.pem_current < EMS_LIMITS.pem.discharge_current_threshold_mA:
            discharge_C = (abs(self.pem_current) / 1000.0) * dt_seconds
            delta_h2_mL = -discharge_C * EMS_LIMITS.pem.h2_discharge_mL_per_C
            self.h2_mode = "discharging"

        else:
            self.h2_mode = "idle" if self.h2_usable_soc > 0 else "empty"

        self.h2_volume_mL = old_h2_volume + delta_h2_mL
        self.sync_hydrogen_state()
        self.h2_last_delta_mL = self.h2_volume_mL - old_h2_volume

    def set_hydrogen_soc(self, soc_percent):
        self.pem_soc = _clamp(float(soc_percent), 0.0, 100.0)
        self.h2_volume_mL = _h2_volume_from_soc(self.pem_soc)
        self.sync_hydrogen_state()

        if self.pem_soc <= 0.0:
            self.h2_mode = "empty"
        else:
            self.h2_mode = "manual"

    def apply_scheduler_decision(self, scenario, reason):
        scenario = max(1, min(6, int(scenario)))

        self.target_scenario = scenario
        self.reason = str(reason)
        self.current_command = f"SCENARIO,{scenario}"

        self.current_decision = {
            "slot": self.current_slot,
            "scenario": scenario,
            "scenario_label": f"S{scenario}",
            "demand_mW": self.current_demand_mW,
            "price_state": self.price_state,
            "pv_available": self.pv_available(),
            "virtual_battery_soc": self.battery_soc,
            "virtual_battery_charge_mAh": self.battery_charge_mah,
            "virtual_battery_capacity_mAh": self.battery_virtual_capacity_mah,
            "pem_soc": self.pem_soc,
            "h2_volume_mL": self.h2_volume_mL,
            "h2_usable_mL": self.h2_usable_mL,
            "h2_mode": self.h2_mode,
            "reason": self.reason,
            "command": self.current_command,
        }

        self.last_decision_update = time.strftime("%Y-%m-%d %H:%M:%S")

    def apply_manual_scenario(self, scenario):
        scenario = max(1, min(6, int(scenario)))

        self.control_mode = "manual"
        self.target_scenario = scenario
        self.reason = "Manual scenario selected from the WebUI."
        self.current_command = f"SCENARIO,{scenario}"

        self.current_decision = {
            "slot": self.current_slot,
            "scenario": scenario,
            "scenario_label": f"S{scenario} manual",
            "demand_mW": self.current_demand_mW,
            "reason": self.reason,
            "command": self.current_command,
        }

    def apply_manual_mode_decision(self):
        if not self.current_decision:
            self.current_decision = {
                "slot": self.current_slot,
                "scenario": self.target_scenario or self.scenario or 1,
                "scenario_label": "Manual mode",
                "demand_mW": self.current_demand_mW,
                "reason": "Manual mode is active. Automatic scenario changes are disabled.",
                "command": self.current_command,
            }

    def to_component_state(self):
        return {
            "demand_mW": self.current_demand_mW,
            "pv_voltage_V": self.panel_voltage,
            "pv_current_mA": self.pv_current,
            "pv_power_mW": self.pv_power,
            "pv_available": self.pv_available(),

            "battery_voltage_V": self.battery_voltage,
            "battery_current_mA": self.battery_current,
            "battery_power_mW": self.battery_power,

            "virtual_battery_soc_percent": self.battery_soc,
            "virtual_battery_charge_mAh": self.battery_charge_mah,
            "virtual_battery_capacity_mAh": self.battery_virtual_capacity_mah,
            "virtual_battery_charge_state": self.battery_charge_state,

            "real_battery_soc_percent": self.real_battery_soc,
            "real_battery_charge_mAh": self.real_battery_charge_mAh,
            "real_battery_capacity_mAh": self.real_battery_capacity_mAh,
            "real_battery_charge_state": self.real_battery_charge_state,
            "real_battery_soc_initialized": self.real_battery_soc_initialized,
            "real_battery_soc_status": self.real_battery_soc_status,
            "real_battery_initial_lookup_voltage": self.real_battery_initial_lookup_voltage,
            "real_battery_lookup_soc_percent": self.real_battery_lookup_soc_percent,
            "real_battery_lookup_voltage_min": self.real_battery_lookup_voltage_min,
            "real_battery_lookup_voltage_max": self.real_battery_lookup_voltage_max,

            # Backwards-compatible keys used by older UI code.
            "battery_soc_percent": self.battery_soc,
            "battery_charge_state": self.battery_charge_state,
            "battery_charge_mAh": self.battery_charge_mah,
            "battery_virtual_capacity_mAh": self.battery_virtual_capacity_mah,

            "pem_voltage_V": self.pem_voltage,
            "pem_current_mA": self.pem_current,
            "pem_power_mW": self.pem_power,
            "pem_soc_percent": self.pem_soc,
            "h2_volume_mL": self.h2_volume_mL,
            "h2_usable_mL": self.h2_usable_mL,
            "h2_usable_soc_percent": self.h2_usable_soc,
            "h2_last_delta_mL": self.h2_last_delta_mL,
            "h2_mode": self.h2_mode,
            "load_voltage_V": self.load_voltage,
            "load_current_mA": self.load_current,
            "load_power_mW": self.load_power,
        }


state = EMSState()
state_lock = threading.Lock()
known_clients = set()
