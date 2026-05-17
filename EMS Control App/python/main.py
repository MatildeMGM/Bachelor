"""
File: main.py

Description:
    This script is part of the bachelor project:
    "Investigation of reversible electrolyzers and implementation of energy
    management control strategies through IoT embedded microcontroller".

    This is the main entry point for the Python EMS application. 
    It sets up the user interface and starts the main EMS control loop in a separate thread.
    This script acts as the starting point for the Arduino Uno Q, 
    and is the bottomline for the entire application.
  
Authors:
    Jacob Norman Sørensen
    Matilde Marie Grønkjær Matell

Institution:
    Technical University of Denmark (DTU)

Date:
    2026-05-18
"""

from __future__ import annotations
import threading
from arduino.app_utils import App
from ems_loop import ems_loop
from ui import setup_ui


def main() -> None:
    setup_ui()

    threading.Thread(
        target=ems_loop,
        daemon=True,
        name="ems-loop",
    ).start()

    print("Starting EMS App...")

    App.run()


if __name__ == "__main__":
    main()