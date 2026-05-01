from pathlib import Path
import re

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def find_bachelor_dir():
    script_dir = Path(__file__).resolve().parent

    for parent in [script_dir] + list(script_dir.parents):
        if (parent / "data").exists() and (parent / "data_treatment").exists():
            return parent

    raise FileNotFoundError("Could not find bachelor folder")


BACHELOR_DIR = find_bachelor_dir()

DATA_DIR = BACHELOR_DIR / "data" / "PEM_test"
CHARGE_DISCHARGE_DIR = DATA_DIR / "charge_discharge"
SWEEP_DIR = DATA_DIR / "current_sweep"

VOLUME_FILE = DATA_DIR / "volume_readings" / "readings.csv"

OUTPUT_DIR = BACHELOR_DIR / "data_treatment" / "processed_PEM"
PLOT_DIR = BACHELOR_DIR / "data_treatment" / "plots" / "pem_plots"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
PLOT_DIR.mkdir(parents=True, exist_ok=True)

PEM_PREFIX = "ina4"
CUTOFF_VOLTAGE = 0.50
MAX_ELECTROLYSIS_CURRENT_A = 0.40


def extract_test_info(file_path):
    name = file_path.stem.lower()

    current_match = re.search(r"_(\d{3})a_", name)
    duration_match = re.search(r"_(\d+)s_", name)
    repeat_match = re.search(r"_r(\d+)", name)

    current_a = int(current_match.group(1)) / 100 if current_match else None
    duration_s = int(duration_match.group(1)) if duration_match else None
    repeat = int(repeat_match.group(1)) if repeat_match else None

    return current_a, duration_s, repeat


def load_volume_data():
    volume = pd.read_csv(VOLUME_FILE)

    volume["current_A"] = pd.to_numeric(volume["current_A"], errors="coerce")
    volume["time_s"] = pd.to_numeric(volume["time_s"], errors="coerce")
    volume["volume_mL"] = pd.to_numeric(volume["volume_mL"], errors="coerce")

    volume = volume.dropna(subset=["current_A", "time_s", "volume_mL"])
    volume["volume_rate_mL_per_s"] = volume["volume_mL"] / volume["time_s"]

    return volume


def estimate_hydrogen_volume(volume_data, current_a, duration_s):
    if current_a is None or duration_s is None:
        return np.nan

    match = volume_data[
        np.isclose(volume_data["current_A"], current_a)
        & np.isclose(volume_data["time_s"], duration_s)
    ]

    if len(match) == 0:
        return np.nan

    return match["volume_mL"].iloc[0]


def read_log(file_path):
    if file_path.stat().st_size == 0:
        raise ValueError(f"Empty file: {file_path.name}")

    df = pd.read_csv(file_path)
    df.columns = df.columns.str.strip()

    if len(df) == 0:
        raise ValueError(f"No rows in file: {file_path.name}")

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["time_s"] = (df["timestamp"] - df["timestamp"].iloc[0]).dt.total_seconds()

        df["scenario"] = pd.to_numeric(df["scenario"], errors="coerce")

        df["pem_voltage_V"] = pd.to_numeric(df[f"{PEM_PREFIX}_bus_V"], errors="coerce")
        df["pem_current_A"] = pd.to_numeric(df[f"{PEM_PREFIX}_current_mA"], errors="coerce") / 1000

    elif "elapsed_s" in df.columns:
        df["time_s"] = pd.to_numeric(df["elapsed_s"], errors="coerce")
        df["scenario"] = np.nan
        df["mode"] = "old_sweep"

        df["pem_voltage_V"] = pd.to_numeric(df["bus_V"], errors="coerce")
        df["pem_current_A"] = pd.to_numeric(df["current_mA"], errors="coerce") / 1000

    else:
        raise ValueError(f"Unknown log format: {file_path.name}")

    df["pem_power_W"] = df["pem_voltage_V"] * df["pem_current_A"]

    df = df.dropna(subset=["time_s", "pem_voltage_V", "pem_current_A", "pem_power_W"])

    return df


def split_charge_discharge(df):
    mode_text = df["mode"].astype(str) if "mode" in df.columns else pd.Series("", index=df.index)

    charge = df[
        (df["scenario"] == 3)
        | (mode_text.str.contains("PV -> PEM", regex=False, na=False))
        | (df["pem_current_A"] > 0.01)
    ].copy()

    discharge = df[
        (df["scenario"] == 6)
        | (mode_text.str.contains("PEM -> Load", regex=False, na=False))
        | (df["pem_current_A"] < -0.005)
    ].copy()

    if len(charge) > 0:
        charge["local_time_s"] = charge["time_s"] - charge["time_s"].iloc[0]

    if len(discharge) > 0:
        discharge["local_time_s"] = discharge["time_s"] - discharge["time_s"].iloc[0]

    return charge, discharge


def integrate_energy(time_s, power_w):
    if len(time_s) < 2:
        return 0.0

    return np.trapezoid(power_w, time_s)


def summarize_combined_file(file_path, volume_data):
    df = read_log(file_path)
    charge, discharge = split_charge_discharge(df)

    current_a, duration_s, repeat = extract_test_info(file_path)
    hydrogen_volume_mL = estimate_hydrogen_volume(volume_data, current_a, duration_s)

    if len(charge) > 1:
        charge_power = np.maximum(charge["pem_power_W"], 0)
        input_energy_j = integrate_energy(charge["local_time_s"], charge_power)

        measured_charge_duration_s = charge["local_time_s"].iloc[-1]
        avg_charge_voltage_v = charge["pem_voltage_V"].mean()
        avg_charge_current_a = charge["pem_current_A"].mean()
        avg_charge_power_w = charge_power.mean()
    else:
        input_energy_j = 0.0
        measured_charge_duration_s = 0.0
        avg_charge_voltage_v = 0.0
        avg_charge_current_a = 0.0
        avg_charge_power_w = 0.0

    usable = discharge[discharge["pem_voltage_V"] >= CUTOFF_VOLTAGE].copy()

    if len(discharge) > 0:
        measured_discharge_duration_s = discharge["local_time_s"].iloc[-1]
        min_discharge_voltage_v = discharge["pem_voltage_V"].min()
        max_discharge_voltage_v = discharge["pem_voltage_V"].max()
        max_discharge_current_a = abs(discharge["pem_current_A"]).max()
    else:
        measured_discharge_duration_s = 0.0
        min_discharge_voltage_v = 0.0
        max_discharge_voltage_v = 0.0
        max_discharge_current_a = 0.0

    if len(usable) > 1:
        discharge_power = abs(usable["pem_power_W"])
        output_energy_j = integrate_energy(usable["local_time_s"], discharge_power)

        usable_discharge_duration_s = usable["local_time_s"].iloc[-1] - usable["local_time_s"].iloc[0]
        avg_usable_power_w = discharge_power.mean()
        avg_usable_voltage_v = usable["pem_voltage_V"].mean()
        avg_usable_current_a = abs(usable["pem_current_A"]).mean()
    else:
        output_energy_j = 0.0
        usable_discharge_duration_s = 0.0
        avg_usable_power_w = 0.0
        avg_usable_voltage_v = 0.0
        avg_usable_current_a = 0.0

    hydrogen_per_input_energy = (
        hydrogen_volume_mL / input_energy_j
        if input_energy_j > 0 and not pd.isna(hydrogen_volume_mL)
        else np.nan
    )

    return {
        "file": file_path.name,
        "charge_current_setpoint_A": current_a,
        "charge_duration_setpoint_s": duration_s,
        "repeat": repeat,
        "hydrogen_volume_mL": hydrogen_volume_mL,
        "hydrogen_per_input_energy_mL_per_J": hydrogen_per_input_energy,
        "measured_charge_duration_s": measured_charge_duration_s,
        "avg_charge_voltage_V": avg_charge_voltage_v,
        "avg_charge_current_A": avg_charge_current_a,
        "avg_charge_power_W": avg_charge_power_w,
        "input_energy_J": input_energy_j,
        "measured_discharge_duration_s": measured_discharge_duration_s,
        "usable_discharge_duration_s": usable_discharge_duration_s,
        "avg_usable_voltage_V": avg_usable_voltage_v,
        "avg_usable_current_A": avg_usable_current_a,
        "avg_usable_power_W": avg_usable_power_w,
        "output_energy_J": output_energy_j,
        "min_discharge_voltage_V": min_discharge_voltage_v,
        "max_discharge_voltage_V": max_discharge_voltage_v,
        "max_discharge_current_A": max_discharge_current_a,
    }


def summarize_sweep(file_path):
    df = read_log(file_path)

    collapse_points = df[df["pem_voltage_V"] < CUTOFF_VOLTAGE]

    if len(collapse_points) > 0:
        collapse_index = collapse_points.index[0]
        location = df.index.get_loc(collapse_index)
        previous_index = df.index[location - 1] if location > 0 else collapse_index

        max_sustainable_current_a = abs(df.loc[previous_index, "pem_current_A"])
        collapse_voltage_v = df.loc[collapse_index, "pem_voltage_V"]
    else:
        max_sustainable_current_a = abs(df["pem_current_A"]).max()
        collapse_voltage_v = df["pem_voltage_V"].min()

    return {
        "file": file_path.name,
        "max_sustainable_current_A": max_sustainable_current_a,
        "collapse_voltage_V": collapse_voltage_v,
        "max_power_W": abs(df["pem_power_W"]).max(),
        "min_voltage_V": df["pem_voltage_V"].min(),
    }


def make_state_table(summary):
    table = summary.copy()
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
            "charge_current_setpoint_A",
            "charge_duration_setpoint_s",
            "hydrogen_volume_mL",
            "avg_usable_power_W",
            "usable_discharge_duration_s",
            "output_energy_J",
            "min_discharge_voltage_V",
            "file",
        ]
    ]


def make_control_parameters(summary, sweep_summary):
    usable = summary[
        (summary["usable_discharge_duration_s"] > 0)
        & (summary["output_energy_J"] > 0)
    ]

    if len(usable) > 0:
        minimum_hydrogen_level_mL = usable["hydrogen_volume_mL"].min()
        minimum_charge_time_s = usable["charge_duration_setpoint_s"].min()
    else:
        minimum_hydrogen_level_mL = np.nan
        minimum_charge_time_s = np.nan

    if len(sweep_summary) > 0:
        maximum_usable_discharge_current_A = sweep_summary["max_sustainable_current_A"].min()
    else:
        maximum_usable_discharge_current_A = summary["max_discharge_current_A"].max()

    return pd.DataFrame([
        {
            "minimum_hydrogen_level_for_discharge_mL": minimum_hydrogen_level_mL,
            "minimum_usable_fuel_cell_voltage_V": CUTOFF_VOLTAGE,
            "maximum_usable_discharge_current_A": maximum_usable_discharge_current_A,
            "maximum_electrolysis_current_A": MAX_ELECTROLYSIS_CURRENT_A,
            "minimum_charge_time_before_useful_discharge_s": minimum_charge_time_s,
            "minimum_time_before_switching_mode_s": minimum_charge_time_s,
        }
    ])


def plot_charge_power():
    plt.figure()

    for file_path in sorted(CHARGE_DISCHARGE_DIR.glob("*.csv")):
        try:
            df = read_log(file_path)
            charge, _ = split_charge_discharge(df)
        except ValueError as error:
            print(f"Skipping {file_path.name}: {error}")
            continue

        if len(charge) > 1:
            plt.plot(
                charge["local_time_s"],
                np.maximum(charge["pem_power_W"], 0) * 1000,
                label=file_path.stem
            )

    plt.xlabel("Time [s]")
    plt.ylabel("Input power [mW]")
    plt.title("PEM charging power")
    plt.legend(fontsize=7)
    plt.tight_layout()
    plt.savefig(PLOT_DIR / "pem_charging_power.png", dpi=300)
    plt.close()


def plot_discharge_voltage():
    plt.figure()

    for file_path in sorted(CHARGE_DISCHARGE_DIR.glob("*.csv")):
        try:
            df = read_log(file_path)
            _, discharge = split_charge_discharge(df)
        except ValueError as error:
            print(f"Skipping {file_path.name}: {error}")
            continue

        if len(discharge) > 1:
            plt.plot(
                discharge["local_time_s"],
                discharge["pem_voltage_V"],
                label=file_path.stem
            )

    plt.axhline(CUTOFF_VOLTAGE, linestyle=":", label="Cutoff voltage")
    plt.xlabel("Time [s]")
    plt.ylabel("Voltage [V]")
    plt.title("PEM discharge voltage")
    plt.legend(fontsize=7)
    plt.tight_layout()
    plt.savefig(PLOT_DIR / "pem_discharge_voltage.png", dpi=300)
    plt.close()


def plot_output_energy(summary):
    plt.figure()

    for current_a, group in summary.groupby("charge_current_setpoint_A"):
        group = group.sort_values("charge_duration_setpoint_s")

        plt.plot(
            group["charge_duration_setpoint_s"],
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


def plot_hydrogen_volume(summary):
    plt.figure()

    for current_a, group in summary.groupby("charge_current_setpoint_A"):
        group = group.sort_values("charge_duration_setpoint_s")

        plt.plot(
            group["charge_duration_setpoint_s"],
            group["hydrogen_volume_mL"],
            marker="o",
            label=f"{current_a:.2f} A"
        )

    plt.xlabel("Charge duration [s]")
    plt.ylabel("Hydrogen volume [mL]")
    plt.title("Hydrogen production during charging")
    plt.legend()
    plt.tight_layout()
    plt.savefig(PLOT_DIR / "pem_hydrogen_volume_vs_charge_time.png", dpi=300)
    plt.close()


def plot_output_energy_vs_hydrogen(summary):
    plt.figure()

    plt.scatter(
        summary["hydrogen_volume_mL"],
        summary["output_energy_J"]
    )

    plt.xlabel("Hydrogen volume [mL]")
    plt.ylabel("Output energy [J]")
    plt.title("PEM output energy as function of hydrogen volume")
    plt.tight_layout()
    plt.savefig(PLOT_DIR / "pem_output_energy_vs_hydrogen_volume.png", dpi=300)
    plt.close()


def plot_sweep():
    for file_path in sorted(SWEEP_DIR.glob("sweep_increasing_load*.csv")):
        try:
            df = read_log(file_path)
        except ValueError as error:
            print(f"Skipping {file_path.name}: {error}")
            continue

        df_sorted = df.sort_values(by="pem_current_A")

        plt.figure()
        plt.plot(
            abs(df_sorted["pem_current_A"]) * 1000,
            df_sorted["pem_voltage_V"],
            marker="o",
            markersize=3,
            label="Measured I V curve"
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
    volume_data = load_volume_data()

    combined_rows = []

    for file_path in sorted(CHARGE_DISCHARGE_DIR.glob("*.csv")):
        try:
            combined_rows.append(summarize_combined_file(file_path, volume_data))
        except ValueError as error:
            print(f"Skipping {file_path.name}: {error}")

    combined_summary = pd.DataFrame(combined_rows)

    sweep_rows = []

    for file_path in sorted(SWEEP_DIR.glob("sweep_increasing_load*.csv")):
        try:
            sweep_rows.append(summarize_sweep(file_path))
        except ValueError as error:
            print(f"Skipping {file_path.name}: {error}")

    sweep_summary = pd.DataFrame(sweep_rows)

    pem_state_table = make_state_table(combined_summary)
    control_parameters = make_control_parameters(combined_summary, sweep_summary)

    combined_summary.to_csv(OUTPUT_DIR / "pem_charge_discharge_summary.csv", index=False)
    pem_state_table.to_csv(OUTPUT_DIR / "pem_state_table.csv", index=False)
    sweep_summary.to_csv(OUTPUT_DIR / "current_sweep_summary.csv", index=False)
    control_parameters.to_csv(OUTPUT_DIR / "pem_control_parameters.csv", index=False)

    plot_charge_power()
    plot_discharge_voltage()
    plot_output_energy(combined_summary)
    plot_hydrogen_volume(combined_summary)
    plot_output_energy_vs_hydrogen(combined_summary)
    plot_sweep()

    print("\nPEM state table:")
    print(pem_state_table)

    print("\nPEM control parameters:")
    print(control_parameters)

    print("\nCurrent sweep summary:")
    print(sweep_summary)

    print("\nSaved output files in:")
    print(OUTPUT_DIR)

    print("\nSaved plots in:")
    print(PLOT_DIR)


if __name__ == "__main__":
    main()