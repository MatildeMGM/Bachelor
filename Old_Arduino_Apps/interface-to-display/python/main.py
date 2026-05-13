# python/main.py
from arduino.app_utils import App, Bridge
from arduino.app_bricks.web_ui import WebUI

ui = WebUI()

def clamp16(s: str) -> str:
    s = (s or "")
    s = s.replace("\n", " ").replace("\r", " ")
    return s[:16]

def on_lcd_write(client_id, data):
    try:
        print("lcd_write received from client:", client_id, "data:", data)

        line1 = clamp16(data.get("line1", ""))
        line2 = clamp16(data.get("line2", ""))

        # Tell browser we reached Python handler (before Bridge call)
        ui.send_message("lcd_debug", {"stage": "python_handler", "line1": line1, "line2": line2})

        # Call MCU
        result = Bridge.call("lcd_print", line1, line2, timeout=5)

        print("Bridge.call lcd_print result:", result)
        ui.send_message("lcd_ack", {"ok": True, "result": result, "line1": line1, "line2": line2})

    except Exception as e:
        print("ERROR in on_lcd_write:", repr(e))
        ui.send_message("lcd_error", {"ok": False, "error": str(e)})

ui.on_message("lcd_write", on_lcd_write)

App.run()