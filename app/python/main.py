# This file contains the app startup code and starts the background loop.

import threading

from arduino.app_utils import App

from ui import forecast_loop, setup_ui

setup_ui()

threading.Thread(target=forecast_loop, daemon=True).start()

print("Starting EMS App...")

App.run()