from pathlib import Path
import re

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

BACHELOR_DIR = SCRIPT_DIR.parents[2]

DATA_DIR = BACHELOR_DIR / "data" / "PEM_test"

CHARGE_DIR = DATA_DIR / "charge"
DISCHARGE_DIR = DATA_DIR / "discharge"
SWEEP_DIR = DATA_DIR / "current_sweep"

OUTPUT_DIR = BACHELOR_DIR / "data_treatment" / "processed_PEM"
PLOT_DIR = BACHELOR_DIR / "data_treatment" / "plots"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
PLOT_DIR.mkdir(parents=True, exist_ok=True)

PEM_PREFIX = "ina4"
CUTOFF_VOLTAGE = 0.50


def extract_test_info(file_path):
    name = file_path.stem.lower()

    current_match = re.search(r"_(\d{3})a_", name)
    duration_match = re.search(r"_(\d+)s_", name)
    repeat_match = re.search(r"_r(\d+)", name)

    current_a = int(current_match.group(1)) / 100 if current_match else None
    duration_s = int(duration_match.group(1)) if duration_match else None
    repeat = int(repeat_match.group(1)) if repeat_match else None

    return current_a, duration_s, repeat


def read_log(file_path):
    df = pd.read_csv(file_path)

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["time_s"] = (df["timestamp"] - df["timestamp"].iloc[0]).dt.total_seconds()

    df["pem_voltage_V"] = pd.to_numeric(df[f"{PEM_PREFIX}_bus_V"], errors="coerce")
    df["pem_current_A"] = pd.to_numeric(df[f"{PEM_PREFIX}_current_mA"], errors="coerce") / 1000
    df["pem_power_W"] = pd.to_numeric(df[f"{PEM_PREFIX}_power_mW"], errors="coerce") / 1000

    df = df.dropna(subset=["time_s", "pem_voltage_V", "pem_current_A", "pem_power_W"])

    return df


def energy_joule(df):
    if len(df) < 2:
        return 0.0

    return np.trapz(df["pem_power_W"], df["time_s"])


def summarize_charge(file_path):
    df = read_log(file_path)
    current_a, duration_s, repeat = extract_test_info(file_path)

    return {
        "file": file_path.name,
        "charge_current_setpoint_A": current_a,
        "charge_duration_setpoint_s": duration_s,
        "repeat": repeat,
        "measured_duration_s": df["time_s"].iloc[-1],
        "avg_voltage_V": df["pem_voltage_V"].mean(),
        "avg_current_A": df["pem_current_A"].mean(),
        "avg_power_W": df["pem_power_W"].mean(),
        "input_energy_J": energy_joule(df),
        "min_voltage_V": df["pem_voltage_V"].min(),
        "max_voltage_V": df["pem_voltage_V"].max(),
    }


def summarize_discharge(file_path):
    df = read_log(file_path)
    current_a, duration_s, repeat = extract_test_info(file_path)

    usable = df[df["pem_voltage_V"] >= CUTOFF_VOLTAGE]

    if len(usable) > 1:
        usable_duration_s = usable["time_s"].iloc[-1] - usable["time_s"].iloc[0]
        output_energy_j = energy_joule(usable)
        avg_usable_power_w = usable["pem_power_W"].mean()
    else:
        usable_duration_s = 0.0
        output_energy_j = 0.0
        avg_usable_power_w = 0.0

    return {
        "file": file_path.name,
        "charge_current_A": current_a,
        "charge_duration_s": duration_s,
        "repeat": repeat,
        "measured_duration_s": df["time_s"].iloc[-1],
        "usable_duration_s": usable_duration_s,
        "avg_voltage_V": df["pem_voltage_V"].mean(),
        "avg_current_A": df["pem_current_A"].mean(),
        "avg_power_W": df["pem_power_W"].mean(),
        "avg_usable_power_W": avg_usable_power_w,
        "output_energy_J": output_energy_j,
        "min_voltage_V": df["pem_voltage_V"].min(),
        "max_voltage_V": df["pem_voltage_V"].max(),
    }


def summarize_sweep(file_path):
    df = read_log(file_path)
    _, _, repeat = extract_test_info(file_path)

    collapse_points = df[df["pem_voltage_V"] < CUTOFF_VOLTAGE]

    if len(collapse_points) > 0:
        collapse_index = collapse_points.index[0]
        previous_index = df.index[df.index.get_loc(collapse_index) - 1] if df.index.get_loc(collapse_index) > 0 else collapse_index
        max_sustainable_current_A = abs(df.loc[previous_index, "pem_current_A"])
        collapse_voltage_V = df.loc[collapse_index, "pem_voltage_V"]
    else:
        max_sustainable_current_A = abs(df["pem_current_A"]).max()
        collapse_voltage_V = df["pem_voltage_V"].min()

    return {
        "file": file_path.name,
        "repeat": repeat,
        "max_sustainable_current_A": max_sustainable_current_A,
        "collapse_voltage_V": collapse_voltage_V,
        "max_power_W": df["pem_power_W"].max(),
        "min_voltage_V": df["pem_voltage_V"].min(),
    }


def process_folder(folder, function):
    rows = []

    for file_path in sorted(folder.glob("*.csv")):
        rows.append(function(file_path))

    return pd.DataFrame(rows)


def make_state_table(discharge_summary):
    table = discharge_summary.copy()

    table = table.sort_values("output_energy_J").reset_index(drop=True)

    state_labels = ["EMPTY", "LOW", "MEDIUM", "HIGH", "FULL"]

    if len(table) <= len(state_labels):
        table["pem_state"] = state_labels[:len(table)]
    else:
        table["pem_state"] = pd.qcut(
            table["output_energy_J"],
            q=len(state_labels),
            labels=state_labels,
            duplicates="drop"
        )

    return table[
        [
            "pem_state",
            "charge_current_A",
            "charge_duration_s",
            "avg_usable_power_W",
            "usable_duration_s",
            "output_energy_J",
            "min_voltage_V",
            "file",
        ]
    ]


def plot_charge_power():
    plt.figure()

    for file_path in sorted(CHARGE_DIR.glob("*.csv")):
        df = read_log(file_path)
        plt.plot(df["time_s"], df["pem_power_W"] * 1000, label=file_path.stem)

    plt.xlabel("Time [s]")
    plt.ylabel("Input power [mW]")
    plt.title("PEM charging power")
    plt.legend(fontsize=7)
    plt.tight_layout()
    plt.savefig(PLOT_DIR / "pem_charging_power.png", dpi=300)
    plt.close()


def plot_discharge_voltage():
    plt.figure()

    for file_path in sorted(DISCHARGE_DIR.glob("*.csv")):
        df = read_log(file_path)
        plt.plot(df["time_s"], df["pem_voltage_V"], label=file_path.stem)

    plt.axhline(CUTOFF_VOLTAGE, linestyle=":", label="Cutoff voltage")
    plt.xlabel("Time [s]")
    plt.ylabel("Voltage [V]")
    plt.title("PEM discharge voltage")
    plt.legend(fontsize=7)
    plt.tight_layout()
    plt.savefig(PLOT_DIR / "pem_discharge_voltage.png", dpi=300)
    plt.close()


def plot_output_energy(discharge_summary):
    plt.figure()

    for current_a, group in discharge_summary.groupby("charge_current_A"):
        plt.plot(
            group["charge_duration_s"],
            group["output_energy_J"],
            marker="o",
            label=f"{current_a:.2f} A"
        )

    plt.xlabel("Charge duration [s]")
    plt.ylabel("Output energy [J]")
    plt.title("PEM output energy after charging")
    plt.legend()
    plt.tight_layout()
    plt.savefig(PLOT_DIR / "pem_output_energy_vs_charge_time.png", dpi=300)
    plt.close()


def plot_sweep():
    for file_path in sorted(SWEEP_DIR.glob("sweep_increasing_load_r*.csv")):
        df = read_log(file_path)

        df_sorted = df.sort_values(by="pem_current_A")

        plt.figure()
        plt.plot(
            abs(df_sorted["pem_current_A"]) * 1000,
            df_sorted["pem_voltage_V"],
            marker="o",
            markersize=3
        )

        plt.axhline(CUTOFF_VOLTAGE, linestyle=":", label="Cutoff voltage")

        plt.xlabel("Current [mA]")
        plt.ylabel("Voltage [V]")
        plt.title(f"PEM I V curve: {file_path.stem}")

        plt.legend()
        plt.tight_layout()

        plt.savefig(PLOT_DIR / f"{file_path.stem}_iv_curve.png", dpi=300)
        plt.close()


def main():
    charge_summary = process_folder(CHARGE_DIR, summarize_charge)
    discharge_summary = process_folder(DISCHARGE_DIR, summarize_discharge)
    sweep_summary = process_folder(SWEEP_DIR, summarize_sweep)

    pem_state_table = make_state_table(discharge_summary)

    charge_summary.to_csv(OUTPUT_DIR / "charge_summary.csv", index=False)
    discharge_summary.to_csv(OUTPUT_DIR / "discharge_summary.csv", index=False)
    sweep_summary.to_csv(OUTPUT_DIR / "current_sweep_summary.csv", index=False)
    pem_state_table.to_csv(OUTPUT_DIR / "pem_state_table.csv", index=False)

    plot_charge_power()
    plot_discharge_voltage()
    plot_output_energy(discharge_summary)
    plot_sweep()

    print("\nPEM state table:")
    print(pem_state_table)

    print("\nSaved output files in:")
    print(OUTPUT_DIR)


if __name__ == "__main__":
    main()