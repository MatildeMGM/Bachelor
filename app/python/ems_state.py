# This file contains the shared EMS state object used across the Python app.

import threading

from app.python.config import DEFAULT_PRICE_ZONE, PRICE_SOURCE


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

        # PV forecast
        self.pv_forecast = []
        self.current_pv_forecast = 0.0
        self.last_pv_update = ""

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

        # App status
        self.bridge_ok = None
        self.last_error = ""
        self.clients = 0
        self.arduino_status = {}

        #battery
        self.battery_soc = 0.0
        self.battery_energy_wh = 0.0
        self.battery_charge_state = ""


state = EMSState()
state_lock = threading.Lock()
known_clients = set()