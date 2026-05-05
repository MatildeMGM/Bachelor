from pathlib import Path
import re
import sys

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


def find_bachelor_dir():
    script_dir = Path(__file__).resolve().parent

    for parent in [script_dir] + list(script_dir.parents):
        if (parent / "data").exists() and (parent / "data_treatment").exists():
            return parent

    raise FileNotFoundError("Could not find bachelor folder")


BACHELOR_DIR = find_bachelor_dir()
sys.path.append(str(BACHELOR_DIR))

from data_treatment.plots.plot_style import CURRENT_COLORS, BLUE, GREEN, PURPLE, GREY, polish_axes, save_report_figure, set_report_style

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

# --- SENSOR CALIBRATION CONSTANTS ---

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
FULL_CYCLE_FILE = CHARGE_DISCHARGE_DIR / "discharge_PEM_full.csv"

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


def split_contiguous_segments(df, mask):
    mask = np.asarray(mask, dtype=bool)

    if len(mask) == 0 or not mask.any():
        return []

    edges = np.diff(np.concatenate(([0], mask.astype(int), [0])))
    starts = np.where(edges == 1)[0]
    ends = np.where(edges == -1)[0]

    return [df.iloc[start:end].copy() for start, end in zip(starts, ends)]


def choose_primary_segment(segments, *, duration_s=None, discharge=False):
    best_segment = pd.DataFrame()
    best_score = -np.inf

    for segment in segments:
        segment = segment.copy()
        segment["local_time_s"] = segment["time_s"] - segment["time_s"].iloc[0]

        if discharge:
            segment = trim_discharge(segment)
            score = (
                integrate_energy(
                    segment["local_time_s"],
                    abs(segment["pem_power_W"]),
                )
                if len(segment) > 1
                else 0.0
            )
        else:
            segment = trim_charge(segment, duration_s)
            score = (
                integrate_energy(
                    segment["local_time_s"],
                    np.maximum(segment["pem_power_W"], 0),
                )
                if len(segment) > 1
                else 0.0
            )

        if score > best_score:
            best_score = score
            best_segment = segment

    return best_segment


def split_charge_discharge(df, duration_s=None):
    mode_text = df["mode"].astype(str) if "mode" in df.columns else pd.Series("", index=df.index)

    charge_mask = (
        (df["scenario"] == 3)
        | (mode_text.str.contains("PV -> PEM", regex=False, na=False))
        | (df["pem_current_A"] > 0.01)
    )

    discharge_mask = (
        (df["scenario"] == 6)
        | (mode_text.str.contains("PEM -> Load", regex=False, na=False))
        | (df["pem_current_A"] < -0.005)
    )

    charge = choose_primary_segment(
        split_contiguous_segments(df, charge_mask),
        duration_s=duration_s,
        discharge=False,
    )
    discharge = choose_primary_segment(
        split_contiguous_segments(df, discharge_mask),
        discharge=True,
    )

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


def find_first_sustained_time(segment, current_threshold_a, consecutive_points=3):
    if len(segment) == 0:
        return np.nan

    current_abs = abs(segment["pem_current_A"]).to_numpy()
    sustained = current_abs >= current_threshold_a

    if len(sustained) < consecutive_points:
        return np.nan

    window = np.convolve(
        sustained.astype(int),
        np.ones(consecutive_points, dtype=int),
        mode="valid",
    )
    indices = np.where(window == consecutive_points)[0]

    if len(indices) == 0:
        return np.nan

    return float(segment["local_time_s"].iloc[indices[0]])


def summarize_full_cycle(file_path, cutoff_voltage):
    df = read_log(file_path)
    charge, discharge = split_charge_discharge(df)

    if len(charge) == 0 or len(discharge) == 0:
        raise ValueError(f"Could not find both charge and discharge segments in {file_path.name}")

    full_cycle = {
        "file": file_path.name,
        "charge_duration_s": float(charge["local_time_s"].iloc[-1]),
        "discharge_duration_s": float(discharge["local_time_s"].iloc[-1]),
        "startup_delay_s": find_first_sustained_time(discharge, 0.01),
        "stable_output_delay_s": find_first_sustained_time(discharge, 0.05),
        "charge_input_energy_J": integrate_energy(
            charge["local_time_s"],
            np.maximum(charge["pem_power_W"], 0),
        ),
        "usable_output_energy_J": integrate_energy(
            discharge.loc[discharge["pem_voltage_V"] >= cutoff_voltage, "local_time_s"],
            abs(discharge.loc[discharge["pem_voltage_V"] >= cutoff_voltage, "pem_power_W"]),
        ),
        "peak_output_power_W": float(abs(discharge["pem_power_W"]).max()),
        "max_charge_power_W": float(np.maximum(charge["pem_power_W"], 0).max()),
        "charge_end_voltage_V": float(charge["pem_voltage_V"].iloc[-1]),
        "discharge_start_voltage_V": float(discharge["pem_voltage_V"].iloc[0]),
        "discharge_min_voltage_V": float(discharge["pem_voltage_V"].min()),
        "cutoff_voltage_V": float(cutoff_voltage),
    }

    full_cycle["usable_discharge_duration_s"] = float(
        discharge.loc[discharge["pem_voltage_V"] >= cutoff_voltage, "local_time_s"].max()
    )
    full_cycle["energy_efficiency_pct"] = (
        100.0 * full_cycle["usable_output_energy_J"] / full_cycle["charge_input_energy_J"]
        if full_cycle["charge_input_energy_J"] > 0
        else np.nan
    )

    return pd.DataFrame([full_cycle]), charge, discharge


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

    table["ems_state"] = table["pem_state"].map({
        "EMPTY": "LOW",
        "LOW": "LOW",
        "MEDIUM": "MEDIUM",
        "HIGH": "HIGH",
        "FULL": "HIGH",
    })

    return table[
        [
            "pem_state",
            "ems_state",
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


def make_control_parameters(summary, sweep_summary, cutoff_voltage, full_cycle_summary):
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

    with_hydrogen = usable.dropna(
        subset=[
            "hydrogen_volume_mL",
            "hydrogen_per_input_energy_mL_per_J",
        ]
    ).copy()
    output_per_hydrogen = with_hydrogen["output_energy_J"] / with_hydrogen["hydrogen_volume_mL"]
    hydrogen_consumption = 1.0 / output_per_hydrogen.replace(0, np.nan)

    hydrogen_production_rate = (
        float(with_hydrogen["hydrogen_per_input_energy_mL_per_J"].median())
        if len(with_hydrogen) > 0
        else 0.08
    )
    hydrogen_consumption_rate = (
        float(hydrogen_consumption.median())
        if len(hydrogen_consumption.dropna()) > 0
        else (6.0 / 14.0)
    )

    if len(full_cycle_summary) > 0:
        startup_delay_s = float(full_cycle_summary.iloc[0]["startup_delay_s"])
        stable_output_delay_s = float(full_cycle_summary.iloc[0]["stable_output_delay_s"])
    else:
        startup_delay_s = np.nan
        stable_output_delay_s = np.nan

    minimum_switch_time_s = startup_delay_s if not pd.isna(startup_delay_s) else 2.0

    return pd.DataFrame([
        {
            "minimum_hydrogen_level_for_discharge_mL": minimum_hydrogen_level_mL,
            "minimum_usable_fuel_cell_voltage_V": cutoff_voltage,
            "maximum_usable_discharge_current_A": maximum_usable_discharge_current_A,
            "maximum_electrolysis_current_A": MAX_ELECTROLYSIS_CURRENT_A,
            "minimum_charge_time_before_useful_discharge_s": minimum_charge_time_s,
            "minimum_time_before_switching_mode_s": minimum_switch_time_s,
            "hydrogen_production_mL_per_input_J": hydrogen_production_rate,
            "hydrogen_consumption_mL_per_output_J": hydrogen_consumption_rate,
            "pem_startup_delay_s": startup_delay_s,
            "pem_stable_output_delay_s": stable_output_delay_s,
        }
    ])


def get_plot_color(current_a, duration_s):
    return CURRENT_COLORS.get(round(float(current_a), 1), BLUE)


def get_duration_alpha(duration_s):
    if duration_s == 30:
        return 0.45
    if duration_s == 60:
        return 0.70
    return 1.00


THRESHOLD_GREY = "#4A4A4A"


def add_pem_curve_legend(ax, curve_handles, cutoff_handle=None):
    legend_handles = curve_handles.copy()
    if cutoff_handle is not None:
        legend_handles.append(cutoff_handle)

    ax.legend(
        handles=legend_handles,
        loc="center left",
        bbox_to_anchor=(1.02, 0.5),
        ncol=1,
        borderaxespad=0,
    )


def collect_charge_discharge_curves():
    plot_data = []

    for file_path in CHARGE_DISCHARGE_DIR.glob("*.csv"):
        try:
            current_a, duration_s, _ = extract_test_info(file_path)

            # Skip files that don't match the expected naming pattern
            if current_a is None or duration_s is None:
                continue

            df = read_log(file_path)
            charge, discharge = split_charge_discharge(df, duration_s)
        except ValueError as error:
            print(f"Skipping {file_path.name}: {error}")
            continue

        if len(charge) > 1 and len(discharge) > 1:
            plot_data.append((duration_s, current_a, charge, discharge, file_path))

    return sorted(plot_data, key=lambda x: (x[1], x[0]))


def plot_charge_power():
    set_report_style()
    fig, ax = plt.subplots(figsize=(7.4, 4.8))

    plot_data = collect_charge_discharge_curves()
    curve_handles = []

    for duration_s, current_a, charge, _, file_path in plot_data:
        label = f"{int(current_a * 1000)} mA, {duration_s} s"
        color = get_plot_color(current_a, duration_s)

        line = ax.plot(
            charge["local_time_s"],
            np.maximum(charge["pem_power_W"], 0) * 1000,
            label=label,
            color=color,
            alpha=get_duration_alpha(duration_s),
        )[0]
        curve_handles.append(line)

    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Input power [mW]")
    ax.set_title("PEM Charging Power")
    add_pem_curve_legend(ax, curve_handles)
    polish_axes(ax)
    save_report_figure(fig, PLOT_DIR / "pem_charging_power.png")


def plot_discharge_voltage(cutoff_voltage):
    set_report_style()
    fig, ax = plt.subplots(figsize=(7.4, 4.8))

    plot_data = collect_charge_discharge_curves()
    curve_handles = []

    for duration_s, current_a, _, discharge, file_path in plot_data:
        label = f"{int(current_a * 1000)} mA, {duration_s} s"
        color = get_plot_color(current_a, duration_s)

        line = ax.plot(
            discharge["local_time_s"],
            discharge["pem_voltage_V"],
            label=label,
            color=color,
            alpha=get_duration_alpha(duration_s),
        )[0]
        curve_handles.append(line)

    cutoff_handle = ax.axhline(
        cutoff_voltage,
        color=THRESHOLD_GREY,
        linestyle="--",
        linewidth=1.8,
        label=f"Cutoff: {cutoff_voltage:.3f} V",
    )

    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Voltage [V]")
    ax.set_title("PEM Discharge Voltage")
    add_pem_curve_legend(ax, curve_handles, cutoff_handle)
    polish_axes(ax)
    save_report_figure(fig, PLOT_DIR / "pem_discharge_voltage.png")


def plot_charge_discharge_subplot(cutoff_voltage):
    set_report_style()
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.8))
    charge_ax, discharge_ax = axes
    curve_handles = []

    for duration_s, current_a, charge, discharge, _ in collect_charge_discharge_curves():
        label = f"{int(current_a * 1000)} mA, {duration_s} s"
        color = get_plot_color(current_a, duration_s)
        alpha = get_duration_alpha(duration_s)

        charge_line = charge_ax.plot(
            charge["local_time_s"],
            np.maximum(charge["pem_power_W"], 0) * 1000,
            label=label,
            color=color,
            alpha=alpha,
        )[0]
        curve_handles.append(charge_line)

        discharge_ax.plot(
            discharge["local_time_s"],
            discharge["pem_voltage_V"],
            color=color,
            alpha=alpha,
        )

    cutoff_handle = discharge_ax.axhline(
        cutoff_voltage,
        color=THRESHOLD_GREY,
        linestyle="--",
        linewidth=1.8,
        label=f"Cutoff: {cutoff_voltage:.3f} V",
    )

    charge_ax.set_xlabel("Time [s]")
    charge_ax.set_ylabel("Input power [mW]")
    charge_ax.set_title("PEM Charging Power")
    polish_axes(charge_ax)

    discharge_ax.set_xlabel("Time [s]")
    discharge_ax.set_ylabel("Voltage [V]")
    discharge_ax.set_title("PEM Discharge Voltage")
    polish_axes(discharge_ax)

    blank = Line2D([], [], linestyle="none", label="")
    legend_handles = curve_handles + [cutoff_handle, blank, blank]

    fig.legend(
        handles=legend_handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.03),
        ncol=4,
        frameon=False,
    )
    fig.subplots_adjust(left=0.07, right=0.98, bottom=0.30, wspace=0.28)
    fig.savefig(PLOT_DIR / "pem_charge_discharge_subplot.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def plot_output_energy(summary):
    set_report_style()
    fig, ax = plt.subplots(figsize=(8.0, 4.8))

    for current_a, group in summary.groupby("charge_current_setpoint_A"):
        group = group.sort_values("charge_duration_setpoint_s")

        ax.plot(
            group["charge_duration_setpoint_s"],
            group["output_energy_J"],
            marker="o",
            color=get_plot_color(current_a, None),
            label=f"{int(current_a * 1000)} mA"
        )

    ax.set_xlabel("Charge duration [s]")
    ax.set_ylabel("Output energy [J]")
    ax.set_title("PEM Output Energy After Charging")
    ax.legend(loc="best")
    polish_axes(ax)
    save_report_figure(fig, PLOT_DIR / "pem_output_energy_vs_charge_time.png")


def plot_hydrogen_volume(summary):
    set_report_style()
    fig, ax = plt.subplots(figsize=(8.0, 4.8))

    for current_a, group in summary.groupby("charge_current_setpoint_A"):
        group = group.sort_values("charge_duration_setpoint_s")

        ax.plot(
            group["charge_duration_setpoint_s"],
            group["hydrogen_volume_mL"],
            marker="o",
            color=get_plot_color(current_a, None),
            label=f"{int(current_a * 1000)} mA"
        )

    ax.set_xlabel("Charge duration [s]")
    ax.set_ylabel("Hydrogen volume [mL]")
    ax.set_title("Hydrogen Production During PEM Charging")
    ax.legend(loc="best")
    polish_axes(ax)
    save_report_figure(fig, PLOT_DIR / "pem_hydrogen_volume_vs_charge_time.png")


def plot_output_energy_vs_hydrogen(summary):
    set_report_style()
    fig, ax = plt.subplots(figsize=(8.0, 4.8))

    for current_a, group in summary.groupby("charge_current_setpoint_A"):
        ax.scatter(
            group["hydrogen_volume_mL"],
            group["output_energy_J"],
            s=70,
            color=get_plot_color(current_a, None),
            label=f"{int(current_a * 1000)} mA",
        )

    ax.set_xlabel("Hydrogen volume [mL]")
    ax.set_ylabel("Output energy [J]")
    ax.set_title("PEM Output Energy as Function of Hydrogen Volume")
    ax.legend(loc="best")
    polish_axes(ax)
    save_report_figure(fig, PLOT_DIR / "pem_output_energy_vs_hydrogen_volume.png")


def plot_sweep(cutoff_voltage):
    set_report_style()
    fig, ax = plt.subplots(figsize=(8.0, 4.8))

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

        ax.plot(
            sweep_grouped["current_step_mA"],
            sweep_grouped["voltage_mean_V"],
            marker="o",
            color=BLUE,
            label=file_path.stem
        )

    ax.axhline(
        cutoff_voltage,
        color=GREY,
        linestyle="dashed",
    )
    ax.text(
        0.98,
        cutoff_voltage + 0.015,
        f"Cutoff voltage: {cutoff_voltage:.3f} V",
        color=GREY,
        ha="right",
        va="bottom",
        transform=ax.get_yaxis_transform(),
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.85, "pad": 2},
    )

    ax.set_xlabel("Current [mA]")
    ax.set_ylabel("Voltage [V]")
    ax.set_title("PEM Voltage During Current Sweep")
    ax.legend(loc="best")
    polish_axes(ax)
    save_report_figure(fig, PLOT_DIR / "pem_iv_curve.png")


def plot_full_cycle(charge, discharge, cutoff_voltage, full_cycle_summary):
    set_report_style()
    fig, axes = plt.subplots(2, 1, figsize=(8.2, 6.4), sharex=True)
    power_ax, voltage_ax = axes
    discharge_offset_s = float(charge["local_time_s"].iloc[-1]) + 10.0
    discharge_time_s = discharge["local_time_s"] + discharge_offset_s

    power_ax.plot(
        charge["local_time_s"],
        np.maximum(charge["pem_power_W"], 0) * 1000,
        color=GREEN,
        label="Charge input power",
    )
    power_ax.plot(
        discharge_time_s,
        abs(discharge["pem_power_W"]) * 1000,
        color=PURPLE,
        label="Discharge output power",
    )

    voltage_ax.plot(
        charge["local_time_s"],
        charge["pem_voltage_V"],
        color=GREEN,
        label="Charge voltage",
    )
    voltage_ax.plot(
        discharge_time_s,
        discharge["pem_voltage_V"],
        color=PURPLE,
        label="Discharge voltage",
    )

    summary_row = full_cycle_summary.iloc[0]
    if not pd.isna(summary_row["startup_delay_s"]):
        power_ax.axvline(
            discharge_offset_s + summary_row["startup_delay_s"],
            color=GREY,
            linestyle=":",
            linewidth=1.6,
            label=f"Startup delay: {summary_row['startup_delay_s']:.1f} s",
        )
    if not pd.isna(summary_row["stable_output_delay_s"]):
        power_ax.axvline(
            discharge_offset_s + summary_row["stable_output_delay_s"],
            color=BLUE,
            linestyle="--",
            linewidth=1.6,
            label=f"Stable output: {summary_row['stable_output_delay_s']:.1f} s",
        )

    voltage_ax.axhline(
        cutoff_voltage,
        color=THRESHOLD_GREY,
        linestyle="--",
        linewidth=1.8,
        label=f"Cutoff: {cutoff_voltage:.3f} V",
    )

    power_ax.set_ylabel("Power [mW]")
    power_ax.set_title("PEM Full Charge and Discharge Cycle", fontsize=18)
    power_ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1.0), borderaxespad=0)
    polish_axes(power_ax)

    voltage_ax.set_xlabel("Cycle time [s]")
    voltage_ax.set_ylabel("Voltage [V]")
    voltage_ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1.0), borderaxespad=0)
    polish_axes(voltage_ax)
    fig.tight_layout(rect=(0, 0, 0.8, 1))
    fig.savefig(PLOT_DIR / "pem_full_cycle.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


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
    full_cycle_summary, full_cycle_charge, full_cycle_discharge = summarize_full_cycle(
        FULL_CYCLE_FILE,
        cutoff_voltage,
    )

    pem_state_table = make_state_table(combined_summary)
    control_parameters = make_control_parameters(
        combined_summary,
        sweep_summary,
        cutoff_voltage,
        full_cycle_summary,
    )

    combined_summary.to_csv(OUTPUT_DIR / "pem_charge_discharge_summary.csv", index=False)
    full_cycle_summary.to_csv(OUTPUT_DIR / "pem_full_cycle_summary.csv", index=False)
    pem_state_table.to_csv(OUTPUT_DIR / "pem_state_table.csv", index=False)
    sweep_summary.to_csv(OUTPUT_DIR / "current_sweep_summary.csv", index=False)
    control_parameters.to_csv(OUTPUT_DIR / "pem_control_parameters.csv", index=False)

    plot_charge_power()
    plot_discharge_voltage(cutoff_voltage)
    plot_charge_discharge_subplot(cutoff_voltage)
    plot_output_energy(combined_summary)
    plot_hydrogen_volume(combined_summary)
    plot_output_energy_vs_hydrogen(combined_summary)
    plot_sweep(cutoff_voltage)
    plot_full_cycle(full_cycle_charge, full_cycle_discharge, cutoff_voltage, full_cycle_summary)

    print("\nPEM state table:")
    print(pem_state_table)

    print("\nPEM control parameters:")
    print(control_parameters)

    print("\nCurrent sweep summary:")
    print(sweep_summary)

    print("\nPEM full cycle summary:")
    print(full_cycle_summary)

    print("\nEmpirical cutoff voltage:")
    print(cutoff_voltage)

    print("\nSaved output files in:")
    print(OUTPUT_DIR)

    print("\nSaved plots in:")
    print(PLOT_DIR)


if __name__ == "__main__":
    main()
