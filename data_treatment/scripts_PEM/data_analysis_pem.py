from pathlib import Path
import re
import sys

import matplotlib
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def find_bachelor_dir():
    script_dir = Path(__file__).resolve().parent

    for parent in [script_dir] + list(script_dir.parents):
        if (parent / "data").exists() and (parent / "data_treatment").exists():
            return parent

    raise FileNotFoundError("Could not find bachelor folder")


BACHELOR_DIR = find_bachelor_dir()
sys.path.append(str(BACHELOR_DIR))

from data_treatment.plots.plot_style import (  # noqa: E402
    BLUE,
    CURRENT_COLORS,
    GREEN,
    GREY,
    PURPLE,
    polish_axes,
    save_report_figure,
    set_report_style,
)

DATA_DIR = BACHELOR_DIR / "data" / "PEM_test"
CHARGE_DISCHARGE_DIR = DATA_DIR / "charge_discharge"
SWEEP_DIR = DATA_DIR / "current_sweep"
VOLUME_FILE = DATA_DIR / "volume_readings" / "readings.csv"

OUTPUT_DIR = BACHELOR_DIR / "app" / "python" / "data" / "processed_PEM"
PLOT_DIR = BACHELOR_DIR / "data_treatment" / "plots" / "pem_plots"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
PLOT_DIR.mkdir(parents=True, exist_ok=True)

PEM_PREFIX = "ina4"
PEM_SENSOR = 0x45
FULL_CYCLE_FILE = CHARGE_DISCHARGE_DIR / "discharge_PEM_full.csv"
PREFERRED_SWEEP_FILE = "sweep_increasing_load_10s.csv"
POLARIZATION_FILE = SWEEP_DIR / "PEM_polarization_characteristics.csv"

INITIAL_CUTOFF_VOLTAGE = 0.50
MAX_ELECTROLYSIS_CURRENT_A = 0.40
SWEEP_MEASURED_HYDROGEN_ML = 12.0
POLARIZATION_STEP_DURATION_S = 30.0
POLARIZATION_AVERAGE_WINDOW_S = 10.0

FARADAY_CONSTANT_C_PER_MOL = 96485.33212
HYDROGEN_ELECTRONS_PER_MOL = 2
MOLAR_VOLUME_ML_PER_MOL_25C = 24465.0

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


def integrate(x, y):
    if len(x) < 2:
        return 0.0

    return float(np.trapezoid(y, x))


def h2_from_charge_mL(charge_c):
    hydrogen_mol = charge_c / (HYDROGEN_ELECTRONS_PER_MOL * FARADAY_CONSTANT_C_PER_MOL)
    return hydrogen_mol * MOLAR_VOLUME_ML_PER_MOL_25C


def extract_test_info(file_path):
    name = file_path.stem.lower()
    current_match = re.search(r"(\d{3})a", name)
    duration_match = re.search(r"(\d+)s", name)
    repeat_match = re.search(r"_r(\d+)", name)

    current_a = int(current_match.group(1)) / 100 if current_match else np.nan
    duration_s = int(duration_match.group(1)) if duration_match else np.nan
    repeat = int(repeat_match.group(1)) if repeat_match else np.nan

    return current_a, duration_s, repeat


def load_volume_data():
    volume = pd.read_csv(VOLUME_FILE)
    for column in ["current_A", "time_s", "volume_mL"]:
        volume[column] = pd.to_numeric(volume[column], errors="coerce")

    return volume.dropna(subset=["current_A", "time_s", "volume_mL"])


def measured_hydrogen(volume_data, current_a, duration_s):
    match = volume_data[
        np.isclose(volume_data["current_A"], current_a)
        & np.isclose(volume_data["time_s"], duration_s)
    ]

    if len(match) == 0:
        return np.nan

    return float(match["volume_mL"].iloc[0])


def read_log(file_path):
    df = pd.read_csv(file_path)
    df.columns = df.columns.str.strip()

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

    return df.dropna(subset=["time_s", "pem_voltage_V", "pem_current_A", "pem_power_W"])


def contiguous_segments(df, mask):
    mask = np.asarray(mask, dtype=bool)
    if len(mask) == 0 or not mask.any():
        return []

    edges = np.diff(np.concatenate(([0], mask.astype(int), [0])))
    starts = np.where(edges == 1)[0]
    ends = np.where(edges == -1)[0]

    return [df.iloc[start:end].copy() for start, end in zip(starts, ends)]


def trim_charge(segment, duration_s=None):
    if len(segment) < 2:
        return segment

    segment = segment.copy()
    start_candidates = np.where(segment["pem_current_A"].to_numpy() > 0.05)[0]
    if len(start_candidates) > 0:
        segment = segment.iloc[start_candidates[0]:].copy()

    segment["local_time_s"] = segment["time_s"] - segment["time_s"].iloc[0]

    if not pd.isna(duration_s):
        segment = segment[segment["local_time_s"] <= duration_s].copy()

    return segment


def trim_discharge(segment):
    if len(segment) < 2:
        return segment

    segment = segment.copy()
    segment["local_time_s"] = segment["time_s"] - segment["time_s"].iloc[0]

    abs_current = abs(segment["pem_current_A"]).to_numpy()
    search_start = max(int(len(abs_current) * 0.2), 30)
    if search_start >= len(abs_current):
        return segment

    near_zero = abs_current[search_start:] < 0.005
    zero_edges = np.diff(np.concatenate(([0], near_zero.astype(int), [0])))
    zero_starts = np.where(zero_edges == 1)[0]
    zero_ends = np.where(zero_edges == -1)[0]

    for start, end in zip(zero_starts, zero_ends):
        if end - start >= 3:
            segment = segment.iloc[:search_start + start].copy()
            segment["local_time_s"] = segment["time_s"] - segment["time_s"].iloc[0]
            break

    return segment


def segment_energy_score(segment, discharge=False):
    if len(segment) < 2:
        return 0.0

    power = abs(segment["pem_power_W"]) if discharge else np.maximum(segment["pem_power_W"], 0)
    return integrate(segment["local_time_s"], power)


def best_segment(segments, *, duration_s=None, discharge=False):
    best = pd.DataFrame()
    best_score = -np.inf

    for segment in segments:
        segment = trim_discharge(segment) if discharge else trim_charge(segment, duration_s)
        score = segment_energy_score(segment, discharge=discharge)
        if score > best_score:
            best = segment
            best_score = score

    return best


def split_charge_discharge(df, duration_s=None):
    mode_text = df.get("mode", pd.Series("", index=df.index)).astype(str)

    charge_mask = (
        (df["scenario"] == 3)
        | mode_text.str.contains("PV -> PEM", regex=False, na=False)
        | (df["pem_current_A"] > 0.01)
    )
    discharge_mask = (
        (df["scenario"] == 6)
        | mode_text.str.contains("PEM -> Load", regex=False, na=False)
        | (df["pem_current_A"] < -0.005)
    )

    charge = best_segment(contiguous_segments(df, charge_mask), duration_s=duration_s)
    discharge = best_segment(contiguous_segments(df, discharge_mask), discharge=True)

    return charge, discharge


def get_sweep_file():
    preferred = SWEEP_DIR / PREFERRED_SWEEP_FILE
    if preferred.exists():
        return preferred

    sweep_files = sorted(SWEEP_DIR.glob("sweep_increasing_load*.csv"))
    if not sweep_files:
        raise FileNotFoundError("No PEM current sweep file found")

    return sweep_files[0]


def summarize_sweep():
    file_path = get_sweep_file()
    df = read_log(file_path)
    charge, discharge = split_charge_discharge(df)
    sweep = discharge if len(discharge) > 1 else df

    usable = sweep[sweep["pem_voltage_V"] >= INITIAL_CUTOFF_VOLTAGE]
    collapse = sweep[sweep["pem_voltage_V"] < INITIAL_CUTOFF_VOLTAGE]

    if len(usable) > 0:
        max_current_a = float(abs(usable["pem_current_A"]).max())
        max_power_w = float(abs(usable["pem_power_W"]).max())
    else:
        max_current_a = 0.0
        max_power_w = 0.0

    collapse_voltage_v = (
        float(collapse["pem_voltage_V"].iloc[0])
        if len(collapse) > 0
        else float(sweep["pem_voltage_V"].min())
    )

    if len(charge) > 1:
        input_charge_c = integrate(charge["local_time_s"], np.maximum(charge["pem_current_A"], 0))
        coulomb_h2_mL = h2_from_charge_mL(input_charge_c)
        measured_h2_mL = SWEEP_MEASURED_HYDROGEN_ML if file_path.name == PREFERRED_SWEEP_FILE else np.nan
        h2_error_mL = coulomb_h2_mL - measured_h2_mL if not pd.isna(measured_h2_mL) else np.nan
        h2_error_pct = 100.0 * h2_error_mL / measured_h2_mL if measured_h2_mL > 0 else np.nan
        faradaic_efficiency_pct = 100.0 * measured_h2_mL / coulomb_h2_mL if coulomb_h2_mL > 0 else np.nan
        charge_duration_s = float(charge["local_time_s"].iloc[-1])
        avg_charge_current_a = float(np.maximum(charge["pem_current_A"], 0).mean())
        input_energy_j = integrate(charge["local_time_s"], np.maximum(charge["pem_power_W"], 0))
    else:
        input_charge_c = 0.0
        coulomb_h2_mL = np.nan
        measured_h2_mL = np.nan
        h2_error_mL = np.nan
        h2_error_pct = np.nan
        faradaic_efficiency_pct = np.nan
        charge_duration_s = 0.0
        avg_charge_current_a = 0.0
        input_energy_j = 0.0

    return pd.DataFrame([
        {
            "file": file_path.name,
            "max_sustainable_current_A": max_current_a,
            "max_sustainable_power_W": max_power_w,
            "collapse_voltage_V": collapse_voltage_v,
            "min_voltage_V": float(sweep["pem_voltage_V"].min()),
            "charge_duration_s": charge_duration_s,
            "avg_charge_current_A": avg_charge_current_a,
            "input_charge_C": input_charge_c,
            "input_energy_J": input_energy_j,
            "coulomb_counted_hydrogen_mL": coulomb_h2_mL,
            "measured_hydrogen_mL": measured_h2_mL,
            "hydrogen_error_mL": h2_error_mL,
            "hydrogen_error_pct": h2_error_pct,
            "faradaic_efficiency_pct": faradaic_efficiency_pct,
        }
    ])


def summarize_charge_discharge_file(file_path, volume_data, cutoff_voltage):
    current_a, duration_s, repeat = extract_test_info(file_path)
    df = read_log(file_path)
    charge, discharge = split_charge_discharge(df, duration_s)
    usable = discharge[discharge["pem_voltage_V"] >= cutoff_voltage].copy()

    h2_mL = measured_hydrogen(volume_data, current_a, duration_s)
    charge_power = np.maximum(charge["pem_power_W"], 0) if len(charge) > 1 else pd.Series(dtype=float)
    discharge_power = abs(usable["pem_power_W"]) if len(usable) > 1 else pd.Series(dtype=float)

    input_energy_j = integrate(charge["local_time_s"], charge_power) if len(charge) > 1 else 0.0
    output_energy_j = integrate(usable["local_time_s"], discharge_power) if len(usable) > 1 else 0.0

    return {
        "file": file_path.name,
        "charge_current_setpoint_A": current_a,
        "charge_duration_setpoint_s": duration_s,
        "repeat": repeat,
        "hydrogen_volume_mL": h2_mL,
        "hydrogen_per_input_energy_mL_per_J": h2_mL / input_energy_j if input_energy_j > 0 else np.nan,
        "measured_charge_duration_s": float(charge["local_time_s"].iloc[-1]) if len(charge) > 1 else 0.0,
        "avg_charge_voltage_V": float(charge["pem_voltage_V"].mean()) if len(charge) > 1 else 0.0,
        "avg_charge_current_A": float(charge["pem_current_A"].mean()) if len(charge) > 1 else 0.0,
        "avg_charge_power_W": float(charge_power.mean()) if len(charge_power) > 0 else 0.0,
        "input_energy_J": input_energy_j,
        "measured_discharge_duration_s": float(discharge["local_time_s"].iloc[-1]) if len(discharge) > 1 else 0.0,
        "usable_discharge_duration_s": float(usable["local_time_s"].iloc[-1] - usable["local_time_s"].iloc[0]) if len(usable) > 1 else 0.0,
        "avg_usable_voltage_V": float(usable["pem_voltage_V"].mean()) if len(usable) > 1 else 0.0,
        "avg_usable_current_A": float(abs(usable["pem_current_A"]).mean()) if len(usable) > 1 else 0.0,
        "avg_usable_power_W": float(discharge_power.mean()) if len(discharge_power) > 0 else 0.0,
        "output_energy_J": output_energy_j,
        "min_discharge_voltage_V": float(discharge["pem_voltage_V"].min()) if len(discharge) > 1 else 0.0,
        "max_discharge_voltage_V": float(discharge["pem_voltage_V"].max()) if len(discharge) > 1 else 0.0,
        "max_discharge_current_A": float(abs(discharge["pem_current_A"]).max()) if len(discharge) > 1 else 0.0,
    }


def summarize_charge_discharge_tests(volume_data, cutoff_voltage):
    rows = []

    for file_path in sorted(CHARGE_DISCHARGE_DIR.glob("*.csv")):
        current_a, duration_s, _ = extract_test_info(file_path)
        if pd.isna(current_a) or pd.isna(duration_s):
            continue

        try:
            rows.append(summarize_charge_discharge_file(file_path, volume_data, cutoff_voltage))
        except ValueError as error:
            print(f"Skipping {file_path.name}: {error}")

    return pd.DataFrame(rows)


def first_sustained_time(segment, threshold_a, points=3):
    if len(segment) < points:
        return np.nan

    sustained = (abs(segment["pem_current_A"]) >= threshold_a).to_numpy()
    window = np.convolve(sustained.astype(int), np.ones(points, dtype=int), mode="valid")
    indices = np.where(window == points)[0]

    if len(indices) == 0:
        return np.nan

    return float(segment["local_time_s"].iloc[indices[0]])


def summarize_full_cycle(cutoff_voltage):
    df = read_log(FULL_CYCLE_FILE)
    charge, discharge = split_charge_discharge(df)
    usable = discharge[discharge["pem_voltage_V"] >= cutoff_voltage].copy()

    charge_energy_j = integrate(charge["local_time_s"], np.maximum(charge["pem_power_W"], 0))
    output_energy_j = integrate(usable["local_time_s"], abs(usable["pem_power_W"]))

    summary = pd.DataFrame([
        {
            "file": FULL_CYCLE_FILE.name,
            "charge_duration_s": float(charge["local_time_s"].iloc[-1]),
            "discharge_duration_s": float(discharge["local_time_s"].iloc[-1]),
            "usable_discharge_duration_s": float(usable["local_time_s"].max()) if len(usable) > 0 else 0.0,
            "startup_delay_s": first_sustained_time(discharge, 0.01),
            "stable_output_delay_s": first_sustained_time(discharge, 0.05),
            "charge_input_energy_J": charge_energy_j,
            "usable_output_energy_J": output_energy_j,
            "energy_efficiency_pct": 100.0 * output_energy_j / charge_energy_j if charge_energy_j > 0 else np.nan,
            "peak_output_power_W": float(abs(discharge["pem_power_W"]).max()),
            "max_charge_power_W": float(np.maximum(charge["pem_power_W"], 0).max()),
            "charge_end_voltage_V": float(charge["pem_voltage_V"].iloc[-1]),
            "discharge_start_voltage_V": float(discharge["pem_voltage_V"].iloc[0]),
            "discharge_min_voltage_V": float(discharge["pem_voltage_V"].min()),
            "cutoff_voltage_V": float(cutoff_voltage),
        }
    ])

    return summary, charge, discharge


def make_state_table(summary):
    table = summary.sort_values("output_energy_J").reset_index(drop=True).copy()
    labels = ["EMPTY", "LOW", "MEDIUM", "HIGH", "FULL"]

    if len(table) <= len(labels):
        table["pem_state"] = labels[:len(table)]
    else:
        table["pem_state"] = pd.qcut(table["output_energy_J"], len(labels), labels=labels, duplicates="drop")

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
    usable = summary[(summary["usable_discharge_duration_s"] > 0) & (summary["output_energy_J"] > 0)]
    with_h2 = usable.dropna(subset=["hydrogen_volume_mL", "hydrogen_per_input_energy_mL_per_J"])

    output_per_h2 = with_h2["output_energy_J"] / with_h2["hydrogen_volume_mL"]
    h2_consumption = 1.0 / output_per_h2.replace(0, np.nan)

    return pd.DataFrame([
        {
            "minimum_hydrogen_level_for_discharge_mL": float(usable["hydrogen_volume_mL"].min()) if len(usable) > 0 else np.nan,
            "minimum_usable_fuel_cell_voltage_V": cutoff_voltage,
            "maximum_usable_discharge_current_A": float(sweep_summary.iloc[0]["max_sustainable_current_A"]),
            "maximum_usable_discharge_power_W": float(sweep_summary.iloc[0]["max_sustainable_power_W"]),
            "maximum_electrolysis_current_A": MAX_ELECTROLYSIS_CURRENT_A,
            "minimum_charge_time_before_useful_discharge_s": float(usable["charge_duration_setpoint_s"].min()) if len(usable) > 0 else np.nan,
            "minimum_time_before_switching_mode_s": float(full_cycle_summary.iloc[0]["startup_delay_s"]),
            "hydrogen_production_mL_per_input_J": float(with_h2["hydrogen_per_input_energy_mL_per_J"].median()) if len(with_h2) > 0 else np.nan,
            "hydrogen_consumption_mL_per_output_J": float(h2_consumption.median()) if len(h2_consumption.dropna()) > 0 else np.nan,
            "pem_startup_delay_s": float(full_cycle_summary.iloc[0]["startup_delay_s"]),
            "pem_stable_output_delay_s": float(full_cycle_summary.iloc[0]["stable_output_delay_s"]),
        }
    ])


def test_color(current_a):
    return CURRENT_COLORS.get(round(float(current_a), 1), BLUE)


def duration_alpha(duration_s):
    if duration_s == 30:
        return 0.45
    if duration_s == 60:
        return 0.70

    return 1.0


def collect_curves():
    curves = []
    for file_path in sorted(CHARGE_DISCHARGE_DIR.glob("*.csv")):
        current_a, duration_s, _ = extract_test_info(file_path)
        if pd.isna(current_a) or pd.isna(duration_s):
            continue

        df = read_log(file_path)
        charge, discharge = split_charge_discharge(df, duration_s)
        if len(charge) > 1 and len(discharge) > 1:
            curves.append((current_a, duration_s, charge, discharge))

    return sorted(curves, key=lambda item: (item[0], item[1]))


def plot_charge_discharge(cutoff_voltage):
    set_report_style()
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.8))
    charge_ax, discharge_ax = axes
    legend_handles = []

    for current_a, duration_s, charge, discharge in collect_curves():
        label = f"{int(current_a * 1000)} mA, {duration_s:.0f} s"
        color = test_color(current_a)
        alpha = duration_alpha(duration_s)

        line = charge_ax.plot(
            charge["local_time_s"],
            np.maximum(charge["pem_power_W"], 0) * 1000,
            color=color,
            alpha=alpha,
            label=label,
        )[0]
        legend_handles.append(line)

        discharge_ax.plot(
            discharge["local_time_s"],
            discharge["pem_voltage_V"],
            color=color,
            alpha=alpha,
        )

    cutoff_handle = discharge_ax.axhline(
        cutoff_voltage,
        color="#4A4A4A",
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
    fig.legend(
        handles=legend_handles + [cutoff_handle, blank, blank],
        loc="upper center",
        bbox_to_anchor=(0.5, 0.03),
        ncol=4,
        frameon=False,
    )
    fig.subplots_adjust(left=0.07, right=0.98, bottom=0.30, wspace=0.28)
    fig.savefig(PLOT_DIR / "pem_charge_discharge_subplot.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def plot_summary_lines(summary, x_col, y_col, ylabel, title, output_name):
    set_report_style()
    fig, ax = plt.subplots(figsize=(8.0, 4.8))

    for current_a, group in summary.groupby("charge_current_setpoint_A"):
        group = group.sort_values(x_col)
        ax.plot(
            group[x_col],
            group[y_col],
            marker="o",
            color=test_color(current_a),
            label=f"{int(current_a * 1000)} mA",
        )

    ax.set_xlabel("Charge duration [s]")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(loc="best")
    polish_axes(ax)
    save_report_figure(fig, PLOT_DIR / output_name)


def plot_output_energy_vs_hydrogen(summary):
    set_report_style()
    fig, ax = plt.subplots(figsize=(8.0, 4.8))

    for current_a, group in summary.groupby("charge_current_setpoint_A"):
        ax.scatter(
            group["hydrogen_volume_mL"],
            group["output_energy_J"],
            s=70,
            color=test_color(current_a),
            label=f"{int(current_a * 1000)} mA",
        )

    ax.set_xlabel("Hydrogen volume [mL]")
    ax.set_ylabel("Output energy [J]")
    ax.set_title("PEM Output Energy as Function of Hydrogen Volume")
    ax.legend(loc="best")
    polish_axes(ax)
    save_report_figure(fig, PLOT_DIR / "pem_output_energy_vs_hydrogen_volume.png")


def summarize_polarization_curve(cutoff_voltage):
    if not POLARIZATION_FILE.exists():
        return pd.DataFrame()

    df = read_log(POLARIZATION_FILE)
    _, discharge = split_charge_discharge(df)

    if len(discharge) < 2:
        return pd.DataFrame()

    discharge = discharge.copy()
    start_time_s = discharge["time_s"].iloc[0]
    discharge["step_index"] = np.floor(
        (discharge["time_s"] - start_time_s) / POLARIZATION_STEP_DURATION_S
    ).astype(int)
    discharge["step_time_s"] = (
        discharge["time_s"] - start_time_s
    ) - discharge["step_index"] * POLARIZATION_STEP_DURATION_S

    stable = discharge[
        discharge["step_time_s"]
        >= POLARIZATION_STEP_DURATION_S - POLARIZATION_AVERAGE_WINDOW_S
    ].copy()

    rows = []
    previous_current_a = -np.inf

    for step_index, step in stable.groupby("step_index"):
        if len(step) < 2:
            continue

        current_a = float(abs(step["pem_current_A"]).mean())
        voltage_v = float(step["pem_voltage_V"].mean())
        power_w = current_a * voltage_v

        rows.append({
            "step_index": int(step_index),
            "current_A": current_a,
            "current_mA": current_a * 1000,
            "voltage_V": voltage_v,
            "power_W": power_w,
            "power_mW": power_w * 1000,
            "is_above_cutoff": voltage_v >= cutoff_voltage,
            "is_increasing_current": current_a >= previous_current_a,
        })

        previous_current_a = current_a

    return pd.DataFrame(rows)


def plot_polarization_curve(cutoff_voltage):
    polarization = summarize_polarization_curve(cutoff_voltage)
    if len(polarization) == 0:
        return polarization

    set_report_style()
    fig, ax = plt.subplots(figsize=(8.0, 4.8))

    increasing = polarization[polarization["is_increasing_current"]].copy()
    collapsed = polarization[~polarization["is_increasing_current"]].copy()

    ax.plot(
        increasing["current_A"],
        increasing["voltage_V"],
        marker="o",
        color=BLUE,
        linewidth=1.8,
        label="Averaged load steps",
    )

    if len(collapsed) > 0:
        ax.scatter(
            collapsed["current_A"],
            collapsed["voltage_V"],
            s=45,
            color=GREY,
            alpha=0.75,
            label="After collapse",
        )

    ax.axhline(
        cutoff_voltage,
        color="#4A4A4A",
        linestyle="--",
        linewidth=1.6,
        label=f"Cutoff: {cutoff_voltage:.3f} V",
    )

    ax.set_xlabel("Current [A]")
    ax.set_ylabel("Voltage [V]")
    ax.set_title("PEM Fuel Cell Polarization Curve")
    ax.legend(loc="best")
    polish_axes(ax)
    save_report_figure(fig, PLOT_DIR / "pem_polarization_curve.png")

    return polarization


def plot_full_cycle(charge, discharge, cutoff_voltage, full_cycle_summary):
    set_report_style()
    fig, axes = plt.subplots(2, 1, figsize=(8.2, 6.4), sharex=True)
    power_ax, voltage_ax = axes

    discharge_offset_s = float(charge["local_time_s"].iloc[-1]) + 10.0
    discharge_time_s = discharge["local_time_s"] + discharge_offset_s

    power_ax.plot(charge["local_time_s"], np.maximum(charge["pem_power_W"], 0) * 1000, color=GREEN, label="Charge input power")
    power_ax.plot(discharge_time_s, abs(discharge["pem_power_W"]) * 1000, color=PURPLE, label="Discharge output power")
    voltage_ax.plot(charge["local_time_s"], charge["pem_voltage_V"], color=GREEN, label="Charge voltage")
    voltage_ax.plot(discharge_time_s, discharge["pem_voltage_V"], color=PURPLE, label="Discharge voltage")

    row = full_cycle_summary.iloc[0]
    if not pd.isna(row["startup_delay_s"]):
        power_ax.axvline(discharge_offset_s + row["startup_delay_s"], color=GREY, linestyle=":", linewidth=1.6, label=f"Startup delay: {row['startup_delay_s']:.1f} s")
    if not pd.isna(row["stable_output_delay_s"]):
        power_ax.axvline(discharge_offset_s + row["stable_output_delay_s"], color=BLUE, linestyle="--", linewidth=1.6, label=f"Stable output: {row['stable_output_delay_s']:.1f} s")

    voltage_ax.axhline(cutoff_voltage, color="#4A4A4A", linestyle="--", linewidth=1.8, label=f"Cutoff: {cutoff_voltage:.3f} V")

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


def save_outputs(
    sweep_summary,
    charge_summary,
    full_cycle_summary,
    state_table,
    control_parameters,
    polarization_summary,
):
    sweep_summary.to_csv(OUTPUT_DIR / "current_sweep_summary.csv", index=False)
    charge_summary.to_csv(OUTPUT_DIR / "pem_charge_discharge_summary.csv", index=False)
    full_cycle_summary.to_csv(OUTPUT_DIR / "pem_full_cycle_summary.csv", index=False)
    state_table.to_csv(OUTPUT_DIR / "pem_state_table.csv", index=False)
    control_parameters.to_csv(OUTPUT_DIR / "pem_control_parameters.csv", index=False)

    if len(polarization_summary) > 0:
        polarization_summary.to_csv(OUTPUT_DIR / "pem_polarization_summary.csv", index=False)


def make_plots(charge_summary, cutoff_voltage, full_cycle_charge, full_cycle_discharge, full_cycle_summary):
    plot_charge_discharge(cutoff_voltage)
    plot_summary_lines(
        charge_summary,
        "charge_duration_setpoint_s",
        "output_energy_J",
        "Output energy [J]",
        "PEM Output Energy After Charging",
        "pem_output_energy_vs_charge_time.png",
    )
    plot_summary_lines(
        charge_summary,
        "charge_duration_setpoint_s",
        "hydrogen_volume_mL",
        "Hydrogen volume [mL]",
        "Hydrogen Production During PEM Charging",
        "pem_hydrogen_volume_vs_charge_time.png",
    )
    plot_output_energy_vs_hydrogen(charge_summary)
    polarization_summary = plot_polarization_curve(cutoff_voltage)
    plot_full_cycle(full_cycle_charge, full_cycle_discharge, cutoff_voltage, full_cycle_summary)

    return polarization_summary


def main():
    volume_data = load_volume_data()
    sweep_summary = summarize_sweep()
    cutoff_voltage = float(sweep_summary.iloc[0]["collapse_voltage_V"])

    charge_summary = summarize_charge_discharge_tests(volume_data, cutoff_voltage)
    full_cycle_summary, full_cycle_charge, full_cycle_discharge = summarize_full_cycle(cutoff_voltage)
    state_table = make_state_table(charge_summary)
    control_parameters = make_control_parameters(charge_summary, sweep_summary, cutoff_voltage, full_cycle_summary)
    polarization_summary = summarize_polarization_curve(cutoff_voltage)

    save_outputs(
        sweep_summary,
        charge_summary,
        full_cycle_summary,
        state_table,
        control_parameters,
        polarization_summary,
    )
    make_plots(charge_summary, cutoff_voltage, full_cycle_charge, full_cycle_discharge, full_cycle_summary)

    print("\nPEM state table:")
    print(state_table)
    print("\nPEM control parameters:")
    print(control_parameters)
    print("\nCurrent sweep summary:")
    print(sweep_summary)
    print("\nPEM full cycle summary:")
    print(full_cycle_summary)
    print("\nPEM polarization summary:")
    print(polarization_summary)
    print("\nSaved output files in:")
    print(OUTPUT_DIR)
    print("\nSaved plots in:")
    print(PLOT_DIR)


if __name__ == "__main__":
    main()
