import serial
import csv
import time
from datetime import datetime
from pathlib import Path

port = "COM6"          # Change if needed
baudrate = 9600
expected_columns = 4   # bus_V,current_mA,power_mW,shunt_mV

script_dir = Path(__file__).resolve().parent
filename = script_dir / f"SOLAR_ina226_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"


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


def parse_numeric_row(line, expected_len):
    parts = [p.strip() for p in line.split(",")]
    if len(parts) != expected_len:
        return None

    values = []
    for p in parts:
        try:
            values.append(float(p))
        except ValueError:
            return None

    return values


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
        "shunt_mV"
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

            values = parse_numeric_row(line, expected_columns)
            if values is None:
                print(f"Skipped malformed row: {line}")
                continue

            now = datetime.now()
            elapsed_s = time.time() - start_time

            writer.writerow([
                now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                f"{elapsed_s:.3f}",
                f"{values[0]:.4f}",
                f"{values[1]:.4f}",
                f"{values[2]:.4f}",
                f"{values[3]:.4f}",
            ])
            f.flush()

            print(
                f"{elapsed_s:8.3f}s | "
                f"V={values[0]:7.4f} V | "
                f"I={values[1]:9.4f} mA | "
                f"P={values[2]:9.4f} mW | "
                f"Shunt={values[3]:8.4f} mV"
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