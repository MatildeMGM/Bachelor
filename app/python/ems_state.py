# This file contains the shared EMS state object used across the Python app.

import threading
import time

from config import DEFAULT_PRICE_ZONE, PRICE_SOURCE


def _as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _scenario_from_mode(mode):
    text = str(mode or "")
    for scenario in range(1, 7):
        if f"S{scenario}" in text:
            return scenario
    return 0


class EMSState:
    def __init__(self):
        # Prices and time
        self.prices = []
        self.price_zone = DEFAULT_PRICE_ZONE
        self.current_price = 0.0
        self.current_hour = 0
        self.current_minute = 0
        self.current_slot = 0
        self.current_time_label = ""
        self.current_interval_label = ""
        self.price_source = PRICE_SOURCE
        self.last_price_update = ""

        # Accelerated demo timing
        self.demo_enabled = True
        self.demo_running = True
        self.demo_cycle = 0
        self.demo_slot_seconds = 7.5
        self.demo_elapsed_seconds = 0.0
        self.demo_started_at = 0.0

        # Demand lookahead
        self.demand_profile = []
        self.current_demand_w = 0.0
        self.last_demand_update = ""

        # Electrical measurements
        self.panel_voltage = 0.0
        self.battery_voltage = 0.0
        self.load_voltage = 0.0
        self.pem_voltage = 0.0

        # Currents
        self.pv_current = 0.0
        self.load_current = 0.0
        self.pem_current = 0.0
        self.battery_current = 0.0

        # Power
        self.pv_power = 0.0
        self.load_power = 0.0
        self.pem_power = 0.0
        self.battery_power = 0.0

        # EMS logic
        self.mode = ""
        self.scenario = 0
        self.target_scenario = 0
        self.last_scenario = 0
        self.last_scenario_change_monotonic = time.monotonic()
        self.current_decision = {}
        self.current_command = ""
        self.schedule = []
        self.schedule_command = ""
        self.last_schedule_update = ""
        self.last_decision_update = ""
        self.log_file = ""
        self.last_log_update = ""

        # App status
        self.bridge_ok = None
        self.last_error = ""
        self.clients = 0
        self.arduino_status = {}

        #battery
        self.battery_soc = 0.0
        self.battery_energy_wh = 0.0
        self.battery_charge_state = ""

        # PEM state is not directly measured as hydrogen volume, so this remains
        # an EMS estimate updated by the scheduler/control layer.
        self.pem_hydrogen_ml = 0.0

    def apply_arduino_status(self, status):
        self.arduino_status = status or {}

        self.panel_voltage = _as_float(self.arduino_status.get("panelVoltage"))
        self.battery_voltage = _as_float(self.arduino_status.get("batteryVoltage"))
        self.load_voltage = _as_float(self.arduino_status.get("loadVoltage"))
        self.pem_voltage = _as_float(self.arduino_status.get("pemrfcVoltage"))

        self.pv_current = _as_float(self.arduino_status.get("PVcurrent"))
        self.load_current = _as_float(self.arduino_status.get("Loadcurrent"))
        self.pem_current = _as_float(self.arduino_status.get("PEMcurrent"))
        self.battery_current = _as_float(self.arduino_status.get("Batcurrent"))

        self.pv_power = _as_float(self.arduino_status.get("PVpower"))
        self.load_power = _as_float(self.arduino_status.get("Loadpower"))
        self.pem_power = _as_float(self.arduino_status.get("PEMpower"))
        self.battery_power = _as_float(self.arduino_status.get("Batterypower"))

        self.battery_soc = _as_float(self.arduino_status.get("batterySOC"))
        self.battery_energy_wh = _as_float(self.arduino_status.get("batteryEnergyWh"))
        self.battery_charge_state = str(
            self.arduino_status.get("batteryChargeState", "")
        )

        self.mode = str(self.arduino_status.get("mode", ""))
        scenario = _scenario_from_mode(self.mode)
        if scenario and scenario != self.scenario:
            self.last_scenario = self.scenario
            self.scenario = scenario
            self.last_scenario_change_monotonic = time.monotonic()

    def update_current_demand(self):
        if self.demand_profile and len(self.demand_profile) > self.current_slot:
            self.current_demand_w = _as_float(self.demand_profile[self.current_slot])
        else:
            self.current_demand_w = 0.0

    def seconds_since_last_switch(self):
        return max(0.0, time.monotonic() - self.last_scenario_change_monotonic)

    def to_component_state(self):
        from scheduler import ComponentState

        return ComponentState(
            battery_soc_percent=self.battery_soc,
            battery_voltage_v=self.battery_voltage,
            battery_energy_wh=self.battery_energy_wh,
            pem_hydrogen_ml=self.pem_hydrogen_ml,
            pem_voltage_v=self.pem_voltage,
            pv_voltage_v=self.panel_voltage,
            pv_current_a=self.pv_current,
            pv_power_w=self.pv_power,
            last_scenario=self.scenario or 1,
            seconds_since_last_switch=self.seconds_since_last_switch(),
        )

    def apply_scheduler_decision(self, decision):
        self.current_decision = decision or {}
        self.current_command = str(self.current_decision.get("command", ""))
        self.target_scenario = int(
            self.current_decision.get("scenario", self.target_scenario or 0)
        )

        if "pem_hydrogen_est_ml" in self.current_decision:
            self.pem_hydrogen_ml = _as_float(
                self.current_decision.get("pem_hydrogen_est_ml"),
                self.pem_hydrogen_ml,
            )


state = EMSState()
state_lock = threading.Lock()
known_clients = set()
