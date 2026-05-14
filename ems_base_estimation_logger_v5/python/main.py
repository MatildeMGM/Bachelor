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