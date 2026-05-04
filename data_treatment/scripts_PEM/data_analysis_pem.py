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
INITIAL_CUTOFF_ESTIMATE = 0.50
MAX_ELECTROLYSIS_CURRENT_A = 0.40

# SENSOR CALIBRATION CONSTANTS 

CURRENT_CORRECTION = {
    0x40: lambda i: i + 0.000563,
    0x41: lambda i: i - 0.000033,
    0x44: lambda i: i + 0.000138,
    0x45: lambda i: 0.843 * i + 0.001,
}

VOLTAGE_CORRECTION = {
    0x40: lambda v: v - 0.068,
    0x41: lambda v: v - 0.066,
    0x44: lambda v: v - 0.180,
    0x45: lambda v: v - 0.064,
}

PEM_SENSOR = 0x45

def extract_test_info(file_path):
    name = file_path.stem.lower()

    # Match patterns like "020a" or "030a" for current
    current_match = re.search(r"(\d{3})a", name)
    duration_match = re.search(r"(\d+)s", name)
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

        raw_voltage = pd.to_numeric(df[f"{PEM_PREFIX}_bus_V"], errors="coerce")
        raw_current = pd.to_numeric(df[f"{PEM_PREFIX}_current_mA"], errors="coerce") / 1000

    elif "elapsed_s" in df.columns:
        df["time_s"] = pd.to_numeric(df["elapsed_s"], errors="coerce")
        df["scenario"] = np.nan
        df["mode"] = "old_sweep"

        raw_voltage = pd.to_numeric(df["bus_V"], errors="coerce")
        raw_current = pd.to_numeric(df["current_mA"], errors="coerce") / 1000

    else:
        raise ValueError(f"Unknown log format: {file_path.name}")

    df["pem_voltage_V"] = VOLTAGE_CORRECTION[PEM_SENSOR](raw_voltage)
    df["pem_current_A"] = CURRENT_CORRECTION[PEM_SENSOR](raw_current)

    df["pem_power_W"] = df["pem_voltage_V"] * df["pem_current_A"]

    df = df.dropna(subset=["time_s", "pem_voltage_V", "pem_current_A", "pem_power_W"])

    return df


def trim_charge(charge, duration_s):
    if len(charge) < 2:
        return charge

    charge = charge.copy()
    current = charge["pem_current_A"].to_numpy()

    start_candidates = np.where(current > 0.05)[0]

    if len(start_candidates) > 0:
        start_idx = start_candidates[0]
        charge = charge.iloc[start_idx:].copy()
        charge["local_time_s"] = charge["time_s"] - charge["time_s"].iloc[0]

    if duration_s is not None:
        charge = charge[charge["local_time_s"] <= duration_s].copy()

    if len(charge) < 2:
        return charge

    current = charge["pem_current_A"].to_numpy()
    search_start = max(int(len(current) * 0.5), 5)

    stop_candidates = np.where(current[search_start:] < 0.05)[0]

    if len(stop_candidates) > 0:
        stop_idx = search_start + stop_candidates[0]
        charge = charge.iloc[:stop_idx].copy()

    if len(charge) > 0:
        charge["local_time_s"] = charge["time_s"] - charge["time_s"].iloc[0]

    return charge


def trim_discharge(discharge):
    if len(discharge) < 2:
        return discharge

    discharge = discharge.copy()
    abs_current = np.abs(discharge["pem_current_A"].to_numpy())

    zero_threshold = 0.005
    start_search = max(int(len(abs_current) * 0.2), 30)

    if start_search >= len(abs_current):
        discharge["local_time_s"] = discharge["time_s"] - discharge["time_s"].iloc[0]
        return discharge

    near_zero_mask = abs_current[start_search:] < zero_threshold
    zero_runs = np.diff(np.concatenate(([0], near_zero_mask.astype(int), [0])))

    zero_starts = np.where(zero_runs == 1)[0]
    zero_ends = np.where(zero_runs == -1)[0]

    for start, end in zip(zero_starts, zero_ends):
        if end - start >= 3:
            cut_idx = start_search + start
            discharge = discharge.iloc[:cut_idx].copy()
            break

    if len(discharge) > 0:
        discharge["local_time_s"] = discharge["time_s"] - discharge["time_s"].iloc[0]

    return discharge


def split_charge_discharge(df, duration_s=None):
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
        charge = trim_charge(charge, duration_s)

    if len(discharge) > 0:
        discharge["local_time_s"] = discharge["time_s"] - discharge["time_s"].iloc[0]
        discharge = trim_discharge(discharge)

    return charge, discharge


def integrate_energy(time_s, power_w):
    if len(time_s) < 2:
        return 0.0

    return np.trapezoid(power_w, time_s)


def summarize_sweep(file_path):
    df = read_log(file_path)

    collapse_points = df[df["pem_voltage_V"] < INITIAL_CUTOFF_ESTIMATE]

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


def get_empirical_cutoff_voltage(sweep_summary):
    if len(sweep_summary) == 0:
        return INITIAL_CUTOFF_ESTIMATE

    cutoff = sweep_summary["collapse_voltage_V"].dropna()

    if len(cutoff) == 0:
        return INITIAL_CUTOFF_ESTIMATE

    return float(cutoff.iloc[0])


def summarize_combined_file(file_path, volume_data, cutoff_voltage):
    current_a, duration_s, repeat = extract_test_info(file_path)

    df = read_log(file_path)
    charge, discharge = split_charge_discharge(df, duration_s)

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

    usable = discharge[discharge["pem_voltage_V"] >= cutoff_voltage].copy()

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


def make_control_parameters(summary, sweep_summary, cutoff_voltage):
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
            "minimum_usable_fuel_cell_voltage_V": cutoff_voltage,
            "maximum_usable_discharge_current_A": maximum_usable_discharge_current_A,
            "maximum_electrolysis_current_A": MAX_ELECTROLYSIS_CURRENT_A,
            "minimum_charge_time_before_useful_discharge_s": minimum_charge_time_s,
            "minimum_time_before_switching_mode_s": minimum_charge_time_s,
        }
    ])


def get_plot_color(current_a, duration_s):
    color_map = {
        30: ["#FFCCBC", "#FFAB91", "#FF8A65"],
        60: ["#B2DFDB", "#80CBC4", "#4DB6AC"],
        120: ["#E1BEE7", "#CE93D8", "#BA68C8"],
    }

    colors = color_map.get(duration_s, ["#D0D0D0", "#A0A0A0", "#707070"])

    if current_a == 0.2:
        color_idx = 0
    elif current_a == 0.3:
        color_idx = 1
    else:
        color_idx = 2

    return colors[color_idx % len(colors)]


def plot_charge_power():
    plt.figure(figsize=(10, 6))

    plot_data = []

    for file_path in CHARGE_DISCHARGE_DIR.glob("*.csv"):
        try:
            current_a, duration_s, _ = extract_test_info(file_path)
            
            # Skip files that don't match the expected naming pattern
            if current_a is None or duration_s is None:
                continue
                
            df = read_log(file_path)
            charge, _ = split_charge_discharge(df, duration_s)
        except ValueError as error:
            print(f"Skipping {file_path.name}: {error}")
            continue

        if len(charge) > 1:
            plot_data.append((duration_s, current_a, charge, file_path))

    plot_data.sort(key=lambda x: (x[0], x[1]))

    for duration_s, current_a, charge, file_path in plot_data:
        label = f"{int(current_a * 1000)} mA in {duration_s} s"
        color = get_plot_color(current_a, duration_s)

        plt.plot(
            charge["local_time_s"],
            np.maximum(charge["pem_power_W"], 0) * 1000,
            label=label,
            color=color,
            linewidth=2
        )

    plt.xlabel("Time [s]", fontsize=12)
    plt.ylabel("Input power [mW]", fontsize=12)
    plt.title("PEM charging power", fontsize=14)
    plt.legend(fontsize=9, loc='best')
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(PLOT_DIR / "pem_charging_power.png", dpi=300)
    plt.close()


def plot_discharge_voltage(cutoff_voltage):
    plt.figure(figsize=(10, 6))

    plot_data = []

    for file_path in CHARGE_DISCHARGE_DIR.glob("*.csv"):
        try:
            current_a, duration_s, _ = extract_test_info(file_path)
            
            # Skip files that don't match the expected naming pattern
            if current_a is None or duration_s is None:
                continue
                
            df = read_log(file_path)
            _, discharge = split_charge_discharge(df, duration_s)
        except ValueError as error:
            print(f"Skipping {file_path.name}: {error}")
            continue

        if len(discharge) > 1:
            plot_data.append((duration_s, current_a, discharge, file_path))

    plot_data.sort(key=lambda x: (x[0], x[1]))

    for duration_s, current_a, discharge, file_path in plot_data:
        label = f"{int(current_a * 1000)} mA in {duration_s} s"
        color = get_plot_color(current_a, duration_s)

        plt.plot(
            discharge["local_time_s"],
            discharge["pem_voltage_V"],
            label=label,
            color=color,
            linewidth=2
        )

    plt.axhline(
        cutoff_voltage,
        color='blue',
        linestyle='dotted',
        linewidth=2,
        label=f"Cutoff voltage: {cutoff_voltage:.3f} V"
    )

    plt.xlabel("Time [s]", fontsize=12)
    plt.ylabel("Voltage [V]", fontsize=12)
    plt.title("PEM discharge voltage", fontsize=14)
    plt.legend(fontsize=9, loc='best')
    plt.grid(alpha=0.3)
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


def plot_sweep(cutoff_voltage):
    plt.figure()

    for file_path in sorted(SWEEP_DIR.glob("sweep_increasing_load*.csv")):
        try:
            df = read_log(file_path)
        except ValueError as error:
            print(f"Skipping {file_path.name}: {error}")
            continue

        sweep = df.copy()
        sweep["current_mA_abs"] = abs(sweep["pem_current_A"]) * 1000
        sweep["current_step_mA"] = (sweep["current_mA_abs"] / 10).round() * 10

        sweep_grouped = sweep.groupby("current_step_mA").agg(
            voltage_mean_V=("pem_voltage_V", "mean")
        ).reset_index()

        sweep_grouped = sweep_grouped.sort_values("current_step_mA")

        plt.plot(
            sweep_grouped["current_step_mA"],
            sweep_grouped["voltage_mean_V"],
            marker="o",
            markersize=4,
            linewidth=2,
            label=file_path.stem
        )

    plt.axhline(
        cutoff_voltage,
        linestyle="dashed",
        label=f"Empirical cutoff voltage: {cutoff_voltage:.3f} V"
    )

    plt.xlabel("Current [mA]")
    plt.ylabel("Voltage [V]")
    plt.title("PEM I V curve")
    plt.legend()
    plt.tight_layout()
    plt.savefig(PLOT_DIR / "pem_iv_curve.png", dpi=300)
    plt.close()


def main():
    volume_data = load_volume_data()

    sweep_rows = []

    for file_path in sorted(SWEEP_DIR.glob("sweep_increasing_load*.csv")):
        try:
            sweep_rows.append(summarize_sweep(file_path))
        except ValueError as error:
            print(f"Skipping {file_path.name}: {error}")

    sweep_summary = pd.DataFrame(sweep_rows)
    cutoff_voltage = get_empirical_cutoff_voltage(sweep_summary)

    combined_rows = []

    for file_path in sorted(CHARGE_DISCHARGE_DIR.glob("*.csv")):
        try:
            combined_rows.append(
                summarize_combined_file(file_path, volume_data, cutoff_voltage)
            )
        except ValueError as error:
            print(f"Skipping {file_path.name}: {error}")

    combined_summary = pd.DataFrame(combined_rows)

    pem_state_table = make_state_table(combined_summary)
    control_parameters = make_control_parameters(combined_summary, sweep_summary, cutoff_voltage)

    combined_summary.to_csv(OUTPUT_DIR / "pem_charge_discharge_summary.csv", index=False)
    pem_state_table.to_csv(OUTPUT_DIR / "pem_state_table.csv", index=False)
    sweep_summary.to_csv(OUTPUT_DIR / "current_sweep_summary.csv", index=False)
    control_parameters.to_csv(OUTPUT_DIR / "pem_control_parameters.csv", index=False)

    plot_charge_power()
    plot_discharge_voltage(cutoff_voltage)
    plot_output_energy(combined_summary)
    plot_hydrogen_volume(combined_summary)
    plot_output_energy_vs_hydrogen(combined_summary)
    plot_sweep(cutoff_voltage)

    print("\nPEM state table:")
    print(pem_state_table)

    print("\nPEM control parameters:")
    print(control_parameters)

    print("\nCurrent sweep summary:")
    print(sweep_summary)

    print("\nEmpirical cutoff voltage:")
    print(cutoff_voltage)

    print("\nSaved output files in:")
    print(OUTPUT_DIR)

    print("\nSaved plots in:")
    print(PLOT_DIR)


if __name__ == "__main__":
    main()