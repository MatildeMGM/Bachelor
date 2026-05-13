import threading
import time

from arduino.app_utils import App, Bridge
from arduino.app_bricks.web_ui import WebUI

from config import (
    BRIDGE_TIMEOUT_S,
    DEFAULT_STEP_INTERVAL_S,
    MAX_STEP_INTERVAL_S,
    MIN_STEP_INTERVAL_S,
    SIM_STEP_SECONDS,
)
from simulator import ElectrolyzerPlant

ui = WebUI()

plant = ElectrolyzerPlant()
state_lock = threading.Lock()

runtime = {
    "running": False,
    "step_interval_s": DEFAULT_STEP_INTERVAL_S,
    "bridge_ok": None,
    "last_error": "",
    "clients": 0,
}

known_clients = set()


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def build_payload():
    state = plant.get_state()
    return {
        **state,
        "runtime": {
            "clients": runtime["clients"],
            "step_interval_s": runtime["step_interval_s"],
            "sim_step_seconds": SIM_STEP_SECONDS,
            "bridge_ok": runtime["bridge_ok"],
            "running": runtime["running"],
            "last_error": runtime["last_error"],
        },
    }


def send_telemetry():
    ui.send_message("telemetry", build_payload())


def push_frame_to_mcu(current):
    payload = "SIM,{step},{wind_kw:.1f},{used_kw:.1f},{h2_total_kg:.3f},{eff:.5f},{s1},{s2},{s3},{s4}".format(
        step=current["step"],
        wind_kw=current["wind_kw"],
        used_kw=current["used_kw"],
        h2_total_kg=current["h2_total_kg"],
        eff=current["system_efficiency"],
        s1=current["electrolyzers"][0]["state"],
        s2=current["electrolyzers"][1]["state"],
        s3=current["electrolyzers"][2]["state"],
        s4=current["electrolyzers"][3]["state"],
    )
    try:
        Bridge.call("apply_sim_frame", payload, timeout=BRIDGE_TIMEOUT_S)
        runtime["bridge_ok"] = True
    except Exception as e:
        runtime["bridge_ok"] = False
        runtime["last_error"] = f"Bridge error: {e}"


def step_and_publish(push_bridge=True):
    with state_lock:
        current = plant.step()
        if push_bridge:
            push_frame_to_mcu(current)

        payload = {
            "current": current,
            "history": list(plant.history),
            "meta": plant.get_state()["meta"],
            "runtime": {
                "clients": runtime["clients"],
                "step_interval_s": runtime["step_interval_s"],
                "sim_step_seconds": SIM_STEP_SECONDS,
                "bridge_ok": runtime["bridge_ok"],
                "running": runtime["running"],
                "last_error": runtime["last_error"],
            },
        }

    ui.send_message("telemetry", payload)


def sim_loop():
    while True:
        try:
            if runtime["running"]:
                step_and_publish(push_bridge=True)
            else:
                send_telemetry()
        except Exception as e:
            runtime["last_error"] = str(e)
            try:
                send_telemetry()
            except Exception:
                pass

        time.sleep(runtime["step_interval_s"])


def on_state_request(client_id, data):
    known_clients.add(client_id)
    runtime["clients"] = len(known_clients)
    send_telemetry()


def on_sim_control(client_id, data):
    known_clients.add(client_id)
    runtime["clients"] = len(known_clients)

    action = (data or {}).get("action", "")

    with state_lock:
        global plant

        if action == "toggle":
            runtime["running"] = not runtime["running"]

        elif action == "step":
            runtime["running"] = False

        elif action == "reset":
            current_strategy = getattr(plant, "strategy", "S1")
            plant = ElectrolyzerPlant()
            plant.set_strategy(current_strategy)
            runtime["last_error"] = ""
            runtime["bridge_ok"] = None

        elif action == "set_speed":
            seconds = (data or {}).get("seconds", DEFAULT_STEP_INTERVAL_S)
            runtime["step_interval_s"] = clamp(
                float(seconds),
                MIN_STEP_INTERVAL_S,
                MAX_STEP_INTERVAL_S,
            )
        elif action == "set_strategy":
            strategy = (data or {}).get("strategy", "S1")
            plant.set_strategy(strategy)

    if action == "step":
        step_and_publish(push_bridge=True)
    else:
        send_telemetry()


ui.on_message("state_request", on_state_request)
ui.on_message("sim_control", on_sim_control)

threading.Thread(target=sim_loop, daemon=True).start()
App.run()