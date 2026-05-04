from pathlib import Path
import sys

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


SCRIPT_DIR = Path(__file__).resolve().parent

BACHELOR_DIR = SCRIPT_DIR.parents[1]
sys.path.append(str(BACHELOR_DIR / "data_treatment"))

from plot_style import BLUE, GREEN, PURPLE, polish_axes, save_report_figure, set_report_style

DATA_DIR = BACHELOR_DIR / "data" / "Battery_test"

OUTPUT_DIR = BACHELOR_DIR / "data_treatment" / "processed_Battery"
PLOT_DIR = BACHELOR_DIR / "data_treatment" / "plots" / "battery_plots"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
PLOT_DIR.mkdir(parents=True, exist_ok=True)


def read_battery_log(file_path):
    df = pd.read_csv(file_path)

    df["pc_time"] = pd.to_datetime(df["pc_time"])
    df["elapsed_s"] = pd.to_numeric(df["elapsed_s"], errors="coerce")
    df["voltage_V"] = pd.to_numeric(df["voltage_corrected_V"], errors="coerce")
    df["current_A"] = pd.to_numeric(df["current_mA"], errors="coerce") / 1000

    df["power_W"] = df["voltage_V"] * df["current_A"]

    df = df.dropna(subset=["elapsed_s", "voltage_V", "current_A", "power_W"])

    return df


def integrate_energy(time_s, power_w):
    if len(time_s) < 2:
        return 0.0

    return np.trapz(power_w, time_s)


def integrate_charge(time_s, current_a):
    if len(time_s) < 2:
        return 0.0

    charge_as = np.trapz(current_a, time_s)
    charge_ah = charge_as / 3600

    return charge_ah


def get_active_part(df):
    if "mode" not in df.columns:
        return df.copy()

    active = df[df["mode"].str.upper() != "REST"].copy()

    if len(active) < 2:
        return df.copy()

    active["elapsed_s"] = active["elapsed_s"] - active["elapsed_s"].iloc[0]

    return active


def summarize_charge(file_path):
    df = read_battery_log(file_path)
    active = get_active_part(df)

    time_s = active["elapsed_s"].to_numpy()
    power_w = active["power_W"].to_numpy()
    current_a = active["current_A"].to_numpy()

    return {
        "file": file_path.name,
        "measured_duration_s": active["elapsed_s"].iloc[-1],
        "start_voltage_V": active["voltage_V"].iloc[0],
        "end_voltage_V": active["voltage_V"].iloc[-1],
        "min_voltage_V": active["voltage_V"].min(),
        "max_voltage_V": active["voltage_V"].max(),
        "avg_current_A": active["current_A"].mean(),
        "max_current_A": active["current_A"].max(),
        "avg_power_W": active["power_W"].mean(),
        "max_power_W": active["power_W"].max(),
        "input_energy_Wh": abs(integrate_energy(time_s, power_w)) / 3600,
        "charged_capacity_Ah": abs(integrate_charge(time_s, current_a)),
    }


def summarize_discharge(file_path):
    df = read_battery_log(file_path)
    active = get_active_part(df)

    time_s = active["elapsed_s"].to_numpy()
    power_w = active["power_W"].to_numpy()
    current_a = active["current_A"].to_numpy()

    discharge_power_w = np.maximum(-power_w, 0)
    discharge_current_a = np.maximum(-current_a, 0)

    return {
        "file": file_path.name,
        "measured_duration_s": active["elapsed_s"].iloc[-1],
        "start_voltage_V": active["voltage_V"].iloc[0],
        "end_voltage_V": active["voltage_V"].iloc[-1],
        "min_voltage_V": active["voltage_V"].min(),
        "max_voltage_V": active["voltage_V"].max(),
        "avg_discharge_current_A": discharge_current_a.mean(),
        "max_discharge_current_A": discharge_current_a.max(),
        "avg_discharge_power_W": discharge_power_w.mean(),
        "max_discharge_power_W": discharge_power_w.max(),
        "usable_energy_Wh": integrate_energy(time_s, discharge_power_w) / 3600,
        "usable_capacity_Ah": integrate_charge(time_s, discharge_current_a),
    }


def add_discharge_energy_columns(df):
    df = df.copy()

    time_s = df["elapsed_s"].to_numpy()
    power_w = np.maximum(-df["power_W"].to_numpy(), 0)
    current_a = np.maximum(-df["current_A"].to_numpy(), 0)

    energy_j = np.zeros(len(df))
    charge_as = np.zeros(len(df))

    for i in range(1, len(df)):
        dt = time_s[i] - time_s[i - 1]
        energy_j[i] = energy_j[i - 1] + 0.5 * (power_w[i] + power_w[i - 1]) * dt
        charge_as[i] = charge_as[i - 1] + 0.5 * (current_a[i] + current_a[i - 1]) * dt

    total_energy_j = energy_j[-1] if energy_j[-1] > 0 else 1.0
    total_charge_as = charge_as[-1] if charge_as[-1] > 0 else 1.0

    df["discharged_energy_Wh"] = energy_j / 3600
    df["discharged_capacity_Ah"] = charge_as / 3600
    df["soc_energy_percent"] = 100 * (1 - energy_j / total_energy_j)
    df["soc_charge_percent"] = 100 * (1 - charge_as / total_charge_as)

    return df


def make_soc_lookup(discharge_df):
    df = add_discharge_energy_columns(discharge_df)

    df["soc_bin"] = df["soc_energy_percent"].round().astype(int)

    lookup = df.groupby("soc_bin").agg(
        voltage_mean_V=("voltage_V", "mean"),
        voltage_min_V=("voltage_V", "min"),
        voltage_max_V=("voltage_V", "max"),
        current_mean_A=("current_A", "mean"),
        power_mean_W=("power_W", "mean"),
    ).reset_index()

    lookup = lookup.rename(columns={"soc_bin": "soc_percent"})
    lookup = lookup.sort_values("soc_percent").reset_index(drop=True)

    return lookup


def make_battery_state_table(discharge_df):
    df = add_discharge_energy_columns(discharge_df)

    bins = [0, 20, 40, 60, 80, 100]
    labels = ["EMPTY", "LOW", "MEDIUM", "HIGH", "FULL"]

    df["battery_state"] = pd.cut(
        df["soc_energy_percent"],
        bins=bins,
        labels=labels,
        include_lowest=True
    )

    state_table = df.groupby("battery_state", observed=False).agg(
        soc_min_percent=("soc_energy_percent", "min"),
        soc_max_percent=("soc_energy_percent", "max"),
        voltage_min_V=("voltage_V", "min"),
        voltage_mean_V=("voltage_V", "mean"),
        voltage_max_V=("voltage_V", "max"),
        remaining_energy_mean_Wh=("discharged_energy_Wh", lambda x: df["discharged_energy_Wh"].max() - x.mean()),
        avg_discharge_current_A=("current_A", "mean"),
        avg_discharge_power_W=("power_W", "mean"),
    ).reset_index()

    state_table["ems_state"] = state_table["battery_state"].map({
        "EMPTY": "LOW",
        "LOW": "LOW",
        "MEDIUM": "MEDIUM",
        "HIGH": "HIGH",
        "FULL": "HIGH",
    })

    return state_table


def plot_charge(df):
    set_report_style()
    fig, ax1 = plt.subplots(figsize=(8.0, 4.8))

    ax1.plot(df["elapsed_s"] / 60, df["voltage_V"], color=BLUE, label="Voltage")
    ax1.set_xlabel("Time [s]")
    ax1.set_ylabel("Voltage [V]")

    ax2 = ax1.twinx()
    ax2.plot(df["elapsed_s"] / 60, df["current_A"] * 1000, color=GREEN, label="Current")
    ax2.set_ylabel("Current [mA]")
    ax1.set_xlabel("Time [min]")
    ax1.set_title("Battery Charge Test")

    lines = ax1.get_lines() + ax2.get_lines()
    labels = [line.get_label() for line in lines]
    ax1.legend(lines, labels, loc="best")
    polish_axes(ax1)
    ax2.grid(False)
    save_report_figure(fig, PLOT_DIR / "battery_charge_voltage_current.png")


def plot_discharge_vs_soc(df):
    set_report_style()
    df = add_discharge_energy_columns(df)

    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    ax.plot(df["soc_energy_percent"], df["voltage_V"], color=BLUE, label="Voltage")
    ax.invert_xaxis()
    ax.set_xlabel("State of charge [%]")
    ax.set_ylabel("Voltage [V]")
    ax.set_title("Battery Voltage During Discharge")
    ax.legend(loc="best")
    polish_axes(ax)
    save_report_figure(fig, PLOT_DIR / "battery_voltage_vs_soc.png")

    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    ax.plot(
        df["soc_energy_percent"],
        -df["current_A"] * 1000,
        color=GREEN,
        label="Discharge current",
    )
    ax.invert_xaxis()
    ax.set_xlabel("State of charge [%]")
    ax.set_ylabel("Current [mA]")
    ax.set_title("Battery Discharge Current")
    ax.legend(loc="best")
    polish_axes(ax)
    save_report_figure(fig, PLOT_DIR / "battery_current_vs_soc.png")

    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    ax.plot(
        df["soc_energy_percent"],
        -df["power_W"] * 1000,
        color=PURPLE,
        label="Discharge power",
    )
    ax.invert_xaxis()
    ax.set_xlabel("State of charge [%]")
    ax.set_ylabel("Power [mW]")
    ax.set_title("Battery Discharge Power")
    ax.legend(loc="best")
    polish_axes(ax)
    save_report_figure(fig, PLOT_DIR / "battery_power_vs_soc.png")


def main():
    charge_files = sorted(DATA_DIR.glob("BATTERY_CHARGE*.csv"))
    discharge_files = sorted(DATA_DIR.glob("BATTERY_DISCHARGE*.csv"))

    if len(charge_files) == 0:
        raise FileNotFoundError("No charge file found in data/Battery_test")

    if len(discharge_files) == 0:
        raise FileNotFoundError("No discharge file found in data/Battery_test")

    charge_file = charge_files[0]
    discharge_file = discharge_files[0]

    charge_df = get_active_part(read_battery_log(charge_file))
    discharge_df = get_active_part(read_battery_log(discharge_file))

    charge_summary = pd.DataFrame([summarize_charge(charge_file)])
    discharge_summary = pd.DataFrame([summarize_discharge(discharge_file)])

    soc_lookup = make_soc_lookup(discharge_df)
    battery_state_table = make_battery_state_table(discharge_df)

    charge_summary.to_csv(OUTPUT_DIR / "battery_charge_summary.csv", index=False)
    discharge_summary.to_csv(OUTPUT_DIR / "battery_discharge_summary.csv", index=False)
    soc_lookup.to_csv(OUTPUT_DIR / "battery_soc_lookup_table.csv", index=False)
    battery_state_table.to_csv(OUTPUT_DIR / "battery_state_table.csv", index=False)

    plot_charge(charge_df)
    plot_discharge_vs_soc(discharge_df)

    print("\nBattery charge summary:")
    print(charge_summary)

    print("\nBattery discharge summary:")
    print(discharge_summary)

    print("\nBattery state table:")
    print(battery_state_table)

    print("\nSaved processed files in:")
    print(OUTPUT_DIR)

    print("\nSaved plots in:")
    print(PLOT_DIR)


if __name__ == "__main__":
    main()
