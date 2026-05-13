class EMSState:
    def __init__(self):
        # Prices
        self.prices = []
        self.current_price = 0.0
        self.current_hour = 0

        # Electrical values
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

        # Status
        self.bridge_ok = None
        self.last_error = ""