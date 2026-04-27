import serial
import csv
import time
from datetime import datetime
from pathlib import Path

port = "COM6"          # Change if needed
baudrate = 9600
expected_numeric_columns = 7   # all except final mode string

script_dir = Path(__file__).resolve().parent
filename = script_dir / f"BATTERY_ina226_soc_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"


def open_serial():
    while True:
        try:
            ser = serial.Serial(port, baudrate, timeout=2)
            time.sleep(2)
            print(f"Connected to {port} at {baudrate} baud")
            print(f"Saving CSV to: {filename}")
            return ser
        except serial.SerialException as e:
            print(f"Could not open {port}: {e}")
            print("Retrying in 3 s...")
            time.sleep(3)


def parse_row(line):
    parts = [p.strip() for p in line.split(",")]

    # Expect 8 total columns:
    # 7 numeric + 1 text mode
    if len(parts) != 8:
        return None

    numeric_values = []
    for p in parts[:7]:
        try:
            numeric_values.append(float(p))
        except ValueError:
            return None

    mode = parts[7]
    if not mode:
        return None

    return numeric_values, mode


ser = open_serial()
start_time = time.time()

with open(filename, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow([
        "pc_time",
        "elapsed_s",
        "bus_V",
        "current_mA",
        "power_mW",
        "shunt_mV",
        "voltage_corrected_V",
        "soc_voltage_percent",
        "soc_percent",
        "mode"
    ])
    f.flush()

    while True:
        try:
            raw = ser.readline()
            if not raw:
                continue

            line = raw.decode("utf-8", errors="ignore").strip()
            if not line:
                continue

            # Skip header line from Arduino if present
            if line.startswith("bus_V,"):
                print("Detected Arduino header, skipping.")
                continue

            parsed = parse_row(line)
            if parsed is None:
                print(f"Skipped malformed row: {line}")
                continue

            values, mode = parsed

            now = datetime.now()
            elapsed_s = time.time() - start_time

            writer.writerow([
                now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                f"{elapsed_s:.3f}",
                f"{values[0]:.4f}",  # bus_V
                f"{values[1]:.4f}",  # current_mA
                f"{values[2]:.4f}",  # power_mW
                f"{values[3]:.4f}",  # shunt_mV
                f"{values[4]:.4f}",  # voltage_corrected_V
                f"{values[5]:.2f}",  # soc_voltage_percent
                f"{values[6]:.2f}",  # soc_percent
                mode
            ])
            f.flush()

            print(
                f"{elapsed_s:8.3f}s | "
                f"V={values[0]:7.4f} V | "
                f"I={values[1]:9.4f} mA | "
                f"P={values[2]:9.4f} mW | "
                f"Shunt={values[3]:8.4f} mV | "
                f"Vcorr={values[4]:7.4f} V | "
                f"SoC_V={values[5]:6.2f}% | "
                f"SoC={values[6]:6.2f}% | "
                f"Mode={mode}"
            )

        except serial.SerialException as e:
            print(f"Serial error: {e}")
            try:
                ser.close()
            except Exception:
                pass

            print("Reconnecting...")
            time.sleep(2)
            ser = open_serial()

        except KeyboardInterrupt:
            print("\nLogging stopped by user.")
            break

try:
    ser.close()
except Exception:
    pass

print(f"Data saved to {filename}")