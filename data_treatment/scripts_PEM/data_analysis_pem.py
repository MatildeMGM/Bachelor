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
POLARIZATION_FILE = SWEEP_DIR / "PEM_polarization_characteristics.csv"

FALLBACK_MAX_ELECTROLYSIS_CURRENT_A = np.nan
POLARIZATION_MEASURED_HYDROGEN_ML = 15.6
POLARIZATION_STEP_DURATION_S = 30.0
POLARIZATION_AVERAGE_WINDOW_S = 10.0
COLLAPSE_ROLLING_WINDOW = 5
COLLAPSE_STARTUP_IGNORE_S = 20.0
COLLAPSE_DVDT_SIGMA = 6.0
COLLAPSE_MIN_DVDT_MAGNITUDE_V_PER_S = 0.002
FUEL_CELL_WAIT_CURRENT_A = 0.01
ELECTROLYSIS_STABLE_CURRENT_FRACTION = 0.90
STABLE_POINTS = 3

FARADAY_CONSTANT_C_PER_MOL = 96485.33212
HYDROGEN_ELECTRONS_PER_MOL = 2
MOLAR_VOLUME_ML_PER_MOL_25C = 24465.0

OBSOLETE_OUTPUTS = [
    OUTPUT_DIR / "current_sweep_summary.csv",
    OUTPUT_DIR / "pem_charge_discharge_summary.csv",
    OUTPUT_DIR / "pem_full_cycle_summary.csv",
    OUTPUT_DIR / "pem_state_table.csv",
    OUTPUT_DIR / "pem_polarization_summary.csv",
    OUTPUT_DIR / "pem_polarization_charge_summary.csv",
    PLOT_DIR / "pem_output_energy_vs_hydrogen_volume.png",
    PLOT_DIR / "pem_output_energy_vs_charge_time.png",
    PLOT_DIR / "pem_full_cycle.png",
    PLOT_DIR / "pem_polarization_cutoff_mpp.png",
]

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
    # Faraday's law: Q = integral(I dt), n_H2 = Q / (2F).
    hydrogen_mol = charge_c / (HYDROGEN_ELECTRONS_PER_MOL * FARADAY_CONSTANT_C_PER_MOL)
    return hydrogen_mol * MOLAR_VOLUME_ML_PER_MOL_25C


def theoretical_h2_mL_per_C():
    return h2_from_charge_mL(1.0)


def warn(message):
    print(f"WARNING: {message}")


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


def trim_charge(segment, duration_s=None, expected_current_a=None):
    if len(segment) < 2:
        return segment

    segment = segment.copy()
    start_candidates = np.where(segment["pem_current_A"].to_numpy() > 0.05)[0]
    if len(start_candidates) > 0:
        segment = segment.iloc[start_candidates[0]:].copy()

    segment["local_time_s"] = segment["time_s"] - segment["time_s"].iloc[0]

    if not pd.isna(duration_s):
        segment = segment[segment["local_time_s"] <= duration_s].copy()

    # Some logs include one or two relay-off samples at the end of the nominal
    # charge window. Trim only the low-current tail so the plots and charge
    # energy calculations represent the actual constant-current charge period.
    if expected_current_a is not None and not pd.isna(expected_current_a):
        tail_threshold_a = max(0.05, 0.5 * float(expected_current_a))
        while len(segment) > 1 and segment["pem_current_A"].iloc[-1] < tail_threshold_a:
            segment = segment.iloc[:-1].copy()

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


def best_segment(segments, *, duration_s=None, expected_current_a=None, discharge=False):
    best = pd.DataFrame()
    best_score = -np.inf

    for segment in segments:
        segment = (
            trim_discharge(segment)
            if discharge
            else trim_charge(segment, duration_s, expected_current_a)
        )
        score = segment_energy_score(segment, discharge=discharge)
        if score > best_score:
            best = segment
            best_score = score

    return best


def split_charge_discharge(df, duration_s=None, expected_charge_current_a=None):
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

    charge = best_segment(
        contiguous_segments(df, charge_mask),
        duration_s=duration_s,
        expected_current_a=expected_charge_current_a,
    )
    discharge = best_segment(contiguous_segments(df, discharge_mask), discharge=True)

    return charge, discharge


def summarize_charge_discharge_file(file_path, volume_data, minimum_usable_voltage_v):
    current_a, duration_s, repeat = extract_test_info(file_path)
    df = read_log(file_path)
    charge, discharge = split_charge_discharge(df, duration_s, current_a)
    if pd.isna(minimum_usable_voltage_v):
        usable = discharge.copy()
    else:
        usable = discharge[discharge["pem_voltage_V"] >= minimum_usable_voltage_v].copy()

    h2_mL = measured_hydrogen(volume_data, current_a, duration_s)
    charge_power = np.maximum(charge["pem_power_W"], 0) if len(charge) > 1 else pd.Series(dtype=float)
    discharge_power = abs(usable["pem_power_W"]) if len(usable) > 1 else pd.Series(dtype=float)

    # Energy is integrated power over time, E = integral(P dt), with P = V I.
    input_energy_j = integrate(charge["local_time_s"], charge_power) if len(charge) > 1 else 0.0
    output_energy_j = integrate(usable["local_time_s"], discharge_power) if len(usable) > 1 else 0.0
    input_charge_c = integrate(charge["local_time_s"], np.maximum(charge["pem_current_A"], 0)) if len(charge) > 1 else 0.0

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
        "input_charge_C": input_charge_c,
        "input_energy_J": input_energy_j,
        "wait_after_switching_to_electrolysis_s": time_until_stable_electrolysis(charge, current_a),
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


def summarize_charge_discharge_tests(volume_data, minimum_usable_voltage_v):
    rows = []

    for file_path in sorted(CHARGE_DISCHARGE_DIR.glob("*.csv")):
        current_a, duration_s, _ = extract_test_info(file_path)
        if pd.isna(current_a) or pd.isna(duration_s):
            continue

        try:
            rows.append(summarize_charge_discharge_file(file_path, volume_data, minimum_usable_voltage_v))
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


def time_until_stable_electrolysis(charge, expected_current_a=None, points=STABLE_POINTS):
    if len(charge) < points:
        return np.nan

    current = np.maximum(charge["pem_current_A"], 0).to_numpy()
    if expected_current_a is not None and not pd.isna(expected_current_a):
        threshold = ELECTROLYSIS_STABLE_CURRENT_FRACTION * float(expected_current_a)
    else:
        threshold = ELECTROLYSIS_STABLE_CURRENT_FRACTION * float(np.nanmedian(current))

    if not np.isfinite(threshold) or threshold <= 0:
        return np.nan

    sustained = current >= threshold
    window = np.convolve(sustained.astype(int), np.ones(points, dtype=int), mode="valid")
    indices = np.where(window == points)[0]
    if len(indices) == 0:
        return np.nan

    return float(charge["local_time_s"].iloc[indices[0]])


def minimum_wait_after_switching_to_electrolysis(charge_summary):
    waits = charge_summary["wait_after_switching_to_electrolysis_s"].dropna()
    if len(waits) == 0:
        warn("minimum_wait_after_switching_to_electrolysis_s could not be derived from charge curves")
        return np.nan

    return float(waits.median())


def summarize_full_cycle(minimum_usable_voltage_v):
    df = read_log(FULL_CYCLE_FILE)
    charge, discharge = split_charge_discharge(df)
    if pd.isna(minimum_usable_voltage_v):
        usable = discharge.copy()
    else:
        usable = discharge[discharge["pem_voltage_V"] >= minimum_usable_voltage_v].copy()

    charge_energy_j = integrate(charge["local_time_s"], np.maximum(charge["pem_power_W"], 0))
    output_energy_j = integrate(usable["local_time_s"], abs(usable["pem_power_W"]))
    fuel_cell_wait_s = first_sustained_time(discharge, FUEL_CELL_WAIT_CURRENT_A, STABLE_POINTS)
    electrolysis_wait_s = time_until_stable_electrolysis(charge)

    summary = pd.DataFrame([
        {
            "file": FULL_CYCLE_FILE.name,
            "charge_duration_s": float(charge["local_time_s"].iloc[-1]),
            "discharge_duration_s": float(discharge["local_time_s"].iloc[-1]),
            "usable_discharge_duration_s": float(usable["local_time_s"].max()) if len(usable) > 0 else 0.0,
            "minimum_wait_after_switching_to_fuel_cell_s": fuel_cell_wait_s,
            "minimum_wait_after_switching_to_electrolysis_s": electrolysis_wait_s,
            "charge_input_energy_J": charge_energy_j,
            "usable_output_energy_J": output_energy_j,
            "energy_efficiency_pct": 100.0 * output_energy_j / charge_energy_j if charge_energy_j > 0 else np.nan,
            "peak_output_power_W": float(abs(discharge["pem_power_W"]).max()),
            "max_charge_power_W": float(np.maximum(charge["pem_power_W"], 0).max()),
            "charge_end_voltage_V": float(charge["pem_voltage_V"].iloc[-1]),
            "discharge_start_voltage_V": float(discharge["pem_voltage_V"].iloc[0]),
            "discharge_min_voltage_V": float(discharge["pem_voltage_V"].min()),
            "minimum_usable_fuel_cell_voltage_V": float(minimum_usable_voltage_v),
        }
    ])

    return summary, charge, discharge


def detect_voltage_collapse(discharge):
    """
    Detect the onset of fuel-cell voltage collapse from dV/dt.

    MPP is not a cutoff voltage. The EMS lower voltage limit should come from
    the point where the discharge voltage leaves the stable plateau and starts
    collapsing quickly.
    """
    if len(discharge) < COLLAPSE_ROLLING_WINDOW + STABLE_POINTS:
        return None

    segment = discharge.copy()
    if "local_time_s" not in segment.columns:
        segment["local_time_s"] = segment["time_s"] - segment["time_s"].iloc[0]

    segment = (
        segment.groupby("local_time_s", as_index=False)
        .agg({
            "time_s": "first",
            "pem_voltage_V": "mean",
            "pem_current_A": "mean",
            "pem_power_W": "mean",
        })
        .sort_values("local_time_s")
        .reset_index(drop=True)
    )

    time_s = segment["local_time_s"].to_numpy(dtype=float)
    voltage = segment["pem_voltage_V"].to_numpy(dtype=float)
    smooth = (
        pd.Series(voltage)
        .rolling(COLLAPSE_ROLLING_WINDOW, center=True, min_periods=1)
        .median()
        .to_numpy()
    )

    if len(np.unique(time_s)) < 2:
        return None

    # dV/dt is calculated on the smoothed voltage to avoid triggering on a
    # single noisy sample.
    dvdt = np.gradient(smooth, time_s)
    duration_s = time_s[-1] - time_s[0]
    ignore_until_s = max(COLLAPSE_STARTUP_IGNORE_S, 0.20 * duration_s)

    plateau_mask = (time_s >= ignore_until_s) & (time_s <= ignore_until_s + 0.30 * duration_s)
    plateau_dvdt = dvdt[plateau_mask]
    plateau_dvdt = plateau_dvdt[np.isfinite(plateau_dvdt)]
    if len(plateau_dvdt) < STABLE_POINTS:
        return None

    baseline = float(np.median(plateau_dvdt))
    mad = float(np.median(np.abs(plateau_dvdt - baseline)))
    robust_sigma = 1.4826 * mad
    threshold = baseline - max(
        COLLAPSE_DVDT_SIGMA * robust_sigma,
        COLLAPSE_MIN_DVDT_MAGNITUDE_V_PER_S,
    )

    search_mask = time_s >= ignore_until_s
    collapse_condition = search_mask & (dvdt <= threshold)
    consecutive = np.convolve(
        collapse_condition.astype(int),
        np.ones(STABLE_POINTS, dtype=int),
        mode="valid",
    )
    candidate_indices = np.where(consecutive == STABLE_POINTS)[0]
    if len(candidate_indices) == 0:
        return None

    collapse_index = int(candidate_indices[0])
    return {
        "collapse_index": collapse_index,
        "collapse_time_s": float(time_s[collapse_index]),
        "collapse_voltage_V": float(smooth[collapse_index]),
        "collapse_dvdt_V_per_s": float(dvdt[collapse_index]),
        "collapse_dvdt_threshold_V_per_s": threshold,
    }


def collect_discharge_collapse_points(include_full_cycle=True):
    rows = []

    for file_path in sorted(CHARGE_DISCHARGE_DIR.glob("*.csv")):
        current_a, duration_s, repeat = extract_test_info(file_path)
        if pd.isna(current_a) or pd.isna(duration_s):
            continue

        df = read_log(file_path)
        _, discharge = split_charge_discharge(df, duration_s, current_a)
        detection = detect_voltage_collapse(discharge)
        if detection is None:
            warn(f"No dV/dt collapse point detected in {file_path.name}")
            continue

        rows.append({
            "file": file_path.name,
            "charge_current_setpoint_A": current_a,
            "charge_duration_setpoint_s": duration_s,
            "repeat": repeat,
            **detection,
        })

    if include_full_cycle and FULL_CYCLE_FILE.exists():
        df = read_log(FULL_CYCLE_FILE)
        _, discharge = split_charge_discharge(df)
        detection = detect_voltage_collapse(discharge)
        if detection is not None:
            rows.append({
                "file": FULL_CYCLE_FILE.name,
                "charge_current_setpoint_A": np.nan,
                "charge_duration_setpoint_s": np.nan,
                "repeat": np.nan,
                **detection,
            })

    return pd.DataFrame(rows)


def minimum_usable_voltage_from_collapse(collapse_points):
    if len(collapse_points) == 0:
        warn("minimum_usable_fuel_cell_voltage_V could not be derived from dV/dt collapse detection")
        return np.nan

    return float(collapse_points["collapse_voltage_V"].median())


def get_polarization_limit(polarization_summary):
    if len(polarization_summary) == 0:
        return np.nan, np.nan

    usable = polarization_summary[polarization_summary["is_usable_step"]].copy()

    if len(usable) == 0:
        return np.nan, np.nan

    # Use stable averaged load-step values, not a single noisy instantaneous max.
    max_current_a = float(usable["current_A"].max())
    max_power_w = float(usable["power_W"].max())

    return max_current_a, max_power_w


def make_control_parameters(
    summary,
    minimum_usable_voltage_v,
    full_cycle_summary,
    polarization_summary,
    polarization_charge_summary,
):
    usable = summary[(summary["usable_discharge_duration_s"] > 0) & (summary["output_energy_J"] > 0)]
    with_paired_h2 = usable.dropna(subset=["hydrogen_volume_mL"])
    with_paired_h2 = with_paired_h2[with_paired_h2["hydrogen_volume_mL"] > 0]

    # Empirical hydrogen consumption is only valid for paired charge/discharge
    # tests where the input gas volume and output energy belong together.
    output_per_h2 = with_paired_h2["output_energy_J"] / with_paired_h2["hydrogen_volume_mL"]
    h2_consumption = 1.0 / output_per_h2.replace(0, np.nan)

    if len(polarization_charge_summary) > 0:
        polarization_row = polarization_charge_summary.iloc[0]
        hydrogen_coulomb_efficiency = float(polarization_row["hydrogen_coulomb_efficiency"])
        theoretical_hydrogen_production_ml_per_c = float(
            polarization_row["theoretical_hydrogen_production_mL_per_C"]
        )
        hydrogen_production_ml_per_input_j = float(polarization_row["measured_hydrogen_per_input_J"])
    else:
        warn("Hydrogen production constants could not be derived from polarization charge test")
        hydrogen_coulomb_efficiency = np.nan
        theoretical_hydrogen_production_ml_per_c = np.nan
        hydrogen_production_ml_per_input_j = np.nan

    max_discharge_current_a, max_discharge_power_w = get_polarization_limit(polarization_summary)

    if pd.isna(max_discharge_current_a):
        warn("maximum_usable_discharge_current_A could not be derived from stable polarization steps")

    if pd.isna(max_discharge_power_w):
        warn("maximum_usable_discharge_power_W could not be derived from stable polarization steps")

    stable_charge_tests = summary[
        (summary["hydrogen_volume_mL"] > 0)
        & (summary["input_charge_C"] > 0)
        & (summary["avg_charge_current_A"] > 0)
    ]
    if len(stable_charge_tests) > 0:
        max_electrolysis_current_a = float(stable_charge_tests["charge_current_setpoint_A"].max())
    elif not pd.isna(FALLBACK_MAX_ELECTROLYSIS_CURRENT_A):
        max_electrolysis_current_a = FALLBACK_MAX_ELECTROLYSIS_CURRENT_A
        warn("Using named fallback maximum electrolysis current because no stable charge tests were found")
    else:
        max_electrolysis_current_a = np.nan
        warn("maximum_electrolysis_current_A could not be justified from available tests")

    return pd.DataFrame([
        {
            "minimum_usable_fuel_cell_voltage_V": minimum_usable_voltage_v,
            "maximum_usable_discharge_current_A": max_discharge_current_a,
            "maximum_usable_discharge_power_W": max_discharge_power_w,
            "maximum_electrolysis_current_A": max_electrolysis_current_a,
            "minimum_charge_time_before_useful_discharge_s": float(usable["charge_duration_setpoint_s"].min()) if len(usable) > 0 else np.nan,
            "minimum_wait_after_switching_to_fuel_cell_s": float(full_cycle_summary.iloc[0]["minimum_wait_after_switching_to_fuel_cell_s"]),
            "minimum_wait_after_switching_to_electrolysis_s": minimum_wait_after_switching_to_electrolysis(summary),
            "measured_full_hydrogen_capacity_mL": POLARIZATION_MEASURED_HYDROGEN_ML,
            "hydrogen_coulomb_efficiency": hydrogen_coulomb_efficiency,
            "theoretical_hydrogen_production_mL_per_C": theoretical_hydrogen_production_ml_per_c,
            "hydrogen_production_mL_per_input_J": hydrogen_production_ml_per_input_j,
            "hydrogen_consumption_mL_per_output_J": float(h2_consumption.median()) if len(h2_consumption.dropna()) > 0 else np.nan,
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
        charge, discharge = split_charge_discharge(df, duration_s, current_a)
        if len(charge) > 1 and len(discharge) > 1:
            curves.append((current_a, duration_s, charge, discharge))

    return sorted(curves, key=lambda item: (item[0], item[1]))


def plot_charge_discharge(minimum_usable_voltage_v):
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

    minimum_voltage_handle = None
    if not pd.isna(minimum_usable_voltage_v):
        minimum_voltage_handle = discharge_ax.axhline(
            minimum_usable_voltage_v,
            color="#4A4A4A",
            linestyle="--",
            linewidth=1.8,
            label=f"Minimum usable: {minimum_usable_voltage_v:.3f} V",
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
        handles=legend_handles + ([minimum_voltage_handle] if minimum_voltage_handle else []) + [blank, blank],
        loc="upper center",
        bbox_to_anchor=(0.5, 0.03),
        ncol=4,
        frameon=False,
    )
    fig.subplots_adjust(left=0.07, right=0.98, bottom=0.30, wspace=0.28)
    fig.savefig(PLOT_DIR / "pem_charge_discharge_subplot.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def plot_discharge_collapse_diagnostics(collapse_points, minimum_usable_voltage_v):
    if len(collapse_points) == 0:
        return

    set_report_style()
    fig, ax = plt.subplots(figsize=(8.6, 5.2))

    for file_path in sorted(CHARGE_DISCHARGE_DIR.glob("*.csv")):
        current_a, duration_s, _ = extract_test_info(file_path)
        if pd.isna(current_a) or pd.isna(duration_s):
            continue

        df = read_log(file_path)
        _, discharge = split_charge_discharge(df, duration_s, current_a)
        if len(discharge) < 2:
            continue

        label = f"{int(current_a * 1000)} mA, {duration_s:.0f} s"
        color = test_color(current_a)
        alpha = duration_alpha(duration_s)
        ax.plot(
            discharge["local_time_s"],
            discharge["pem_voltage_V"],
            color=color,
            alpha=alpha,
            linewidth=1.5,
            label=label,
        )

        match = collapse_points[collapse_points["file"] == file_path.name]
        if len(match) > 0:
            row = match.iloc[0]
            ax.scatter(
                row["collapse_time_s"],
                row["collapse_voltage_V"],
                s=48,
                color=color,
                edgecolors="white",
                linewidth=0.9,
                zorder=5,
            )

    if not pd.isna(minimum_usable_voltage_v):
        ax.axhline(
            minimum_usable_voltage_v,
            color="#4A4A4A",
            linestyle="--",
            linewidth=1.6,
            label=f"Median collapse onset: {minimum_usable_voltage_v:.3f} V",
        )

    ax.set_xlabel("Discharge time [s]")
    ax.set_ylabel("Fuel cell voltage [V]")
    ax.set_title("PEM Discharge Collapse Detection")
    ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1.0), borderaxespad=0)
    polish_axes(ax)
    fig.tight_layout(rect=(0, 0, 0.78, 1))
    fig.savefig(PLOT_DIR / "pem_discharge_collapse_detection.png", bbox_inches="tight", facecolor="white")
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


def summarize_polarization_curve(minimum_usable_voltage_v=None):
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

        is_above_minimum_voltage = (
            voltage_v >= minimum_usable_voltage_v
            if minimum_usable_voltage_v is not None and not pd.isna(minimum_usable_voltage_v)
            else np.nan
        )
        is_usable_step = (
            (not pd.isna(is_above_minimum_voltage))
            and bool(is_above_minimum_voltage)
            and current_a >= previous_current_a
            and power_w > 0
        )

        rows.append({
            "step_index": int(step_index),
            "current_A": current_a,
            "current_mA": current_a * 1000,
            "voltage_V": voltage_v,
            "power_W": power_w,
            "power_mW": power_w * 1000,
            "is_above_minimum_usable_voltage": is_above_minimum_voltage,
            "is_increasing_current": current_a >= previous_current_a,
            "is_usable_step": is_usable_step,
        })

        previous_current_a = current_a

    return pd.DataFrame(rows)


def summarize_polarization_charge():
    if not POLARIZATION_FILE.exists():
        return pd.DataFrame()

    df = read_log(POLARIZATION_FILE)
    charge, _ = split_charge_discharge(df)

    if len(charge) < 2:
        return pd.DataFrame()

    charge_current = np.maximum(charge["pem_current_A"], 0)
    charge_power = np.maximum(charge["pem_power_W"], 0)
    input_charge_c = integrate(charge["local_time_s"], charge_current)
    input_energy_j = integrate(charge["local_time_s"], charge_power)
    coulomb_h2_ml = h2_from_charge_mL(input_charge_c)
    measured_h2_ml = POLARIZATION_MEASURED_HYDROGEN_ML
    hydrogen_coulomb_efficiency = (
        measured_h2_ml / coulomb_h2_ml
        if coulomb_h2_ml > 0
        else np.nan
    )

    return pd.DataFrame([
        {
            "file": POLARIZATION_FILE.name,
            "measured_hydrogen_mL": measured_h2_ml,
            "charge_duration_s": float(charge["local_time_s"].iloc[-1]),
            "avg_charge_current_A": float(charge_current.mean()),
            "input_charge_C": input_charge_c,
            "input_energy_J": input_energy_j,
            "coulomb_counted_hydrogen_mL": coulomb_h2_ml,
            # The EMS estimates hydrogen from logged charge input; it does not
            # directly measure the gas volume during operation.
            "hydrogen_coulomb_efficiency": hydrogen_coulomb_efficiency,
            "theoretical_hydrogen_production_mL_per_C": theoretical_h2_mL_per_C(),
            "hydrogen_error_mL": coulomb_h2_ml - measured_h2_ml,
            "hydrogen_error_pct": (
                100.0 * (coulomb_h2_ml - measured_h2_ml) / measured_h2_ml
                if measured_h2_ml > 0
                else np.nan
            ),
            "faradaic_efficiency_pct": (
                100.0 * measured_h2_ml / coulomb_h2_ml
                if coulomb_h2_ml > 0
                else np.nan
            ),
            "measured_hydrogen_per_input_J": (
                measured_h2_ml / input_energy_j
                if input_energy_j > 0
                else np.nan
            ),
        }
    ])


def plot_polarization_curve(minimum_usable_voltage_v, polarization=None):
    if polarization is None:
        polarization = summarize_polarization_curve(minimum_usable_voltage_v)
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

    if not pd.isna(minimum_usable_voltage_v):
        ax.axhline(
            minimum_usable_voltage_v,
            color="#4A4A4A",
            linestyle="--",
            linewidth=1.6,
            label=f"Minimum usable: {minimum_usable_voltage_v:.3f} V",
        )

    ax.set_xlabel("Current [A]")
    ax.set_ylabel("Voltage [V]")
    ax.set_title("PEM Fuel Cell Polarization Curve")
    ax.legend(loc="best")
    polish_axes(ax)
    save_report_figure(fig, PLOT_DIR / "pem_polarization_curve.png")

    return polarization


def plot_polarization_power_curve(minimum_usable_voltage_v, polarization=None):
    if polarization is None:
        polarization = summarize_polarization_curve(minimum_usable_voltage_v)
    if len(polarization) == 0:
        return

    increasing = polarization[polarization["is_usable_step"]].copy()

    if len(increasing) == 0:
        return

    max_power_idx = increasing["power_W"].idxmax()
    max_power_step = increasing.loc[max_power_idx]

    set_report_style()
    fig, voltage_ax = plt.subplots(figsize=(8.4, 5.0))
    power_ax = voltage_ax.twinx()

    voltage_line = voltage_ax.plot(
        increasing["current_A"],
        increasing["voltage_V"],
        marker="o",
        color=BLUE,
        linewidth=1.8,
        label="Voltage",
    )[0]
    power_line = power_ax.plot(
        increasing["current_A"],
        increasing["power_mW"],
        marker="s",
        color=PURPLE,
        linewidth=1.8,
        label="Power",
    )[0]

    voltage_limit = voltage_ax.scatter(
        max_power_step["current_A"],
        max_power_step["voltage_V"],
        s=105,
        color=GREEN,
        edgecolors="white",
        linewidth=1.4,
        zorder=5,
        label="Maximum stable averaged power voltage",
    )
    power_limit = power_ax.scatter(
        max_power_step["current_A"],
        max_power_step["power_mW"],
        s=105,
        color=GREEN,
        edgecolors="white",
        linewidth=1.4,
        marker="s",
        zorder=5,
        label=(
            f"Max stable avg: {max_power_step['current_mA']:.1f} mA, "
            f"{max_power_step['voltage_V']:.3f} V, "
            f"{max_power_step['power_mW']:.1f} mW"
        ),
    )
    voltage_ax.axvline(
        max_power_step["current_A"],
        color=GREEN,
        linestyle="--",
        linewidth=1.5,
        alpha=0.75,
    )
    if not pd.isna(minimum_usable_voltage_v):
        voltage_ax.axhline(
            minimum_usable_voltage_v,
            color="#4A4A4A",
            linestyle="--",
            linewidth=1.5,
            alpha=0.85,
            label=f"Minimum usable voltage: {minimum_usable_voltage_v:.3f} V",
        )

    voltage_ax.set_xlabel("Current [A]")
    voltage_ax.set_ylabel("Voltage [V]")
    power_ax.set_ylabel("Power [mW]")
    voltage_ax.set_title("PEM Polarization Stable Averaged Limits")

    minimum_voltage_handle = voltage_ax.get_lines()[-1]
    handles = [voltage_line, power_line, voltage_limit, power_limit, minimum_voltage_handle]
    labels = [
        "Voltage",
        "Power",
        "Voltage at max stable average",
        (
            f"Max stable avg: {max_power_step['current_mA']:.1f} mA, "
            f"{max_power_step['voltage_V']:.3f} V, "
            f"{max_power_step['power_mW']:.1f} mW"
        ),
        f"Minimum usable voltage: {minimum_usable_voltage_v:.3f} V",
    ]
    fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.02),
        ncol=2,
        frameon=False,
    )

    polish_axes(voltage_ax)
    power_ax.grid(False)
    fig.subplots_adjust(bottom=0.28)
    fig.savefig(PLOT_DIR / "pem_polarization_power_curve.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def remove_obsolete_outputs():
    for path in OBSOLETE_OUTPUTS:
        if path.exists():
            path.unlink()


def save_outputs(
    charge_summary,
    full_cycle_summary,
    control_parameters,
    polarization_summary,
    collapse_points,
    polarization_charge_summary,
):
    control_parameters.to_csv(OUTPUT_DIR / "pem_control_parameters.csv", index=False)

    # Optional analysis tables support plots/debugging. They are not EMS control
    # files and should not be used as direct state tables.
    charge_summary.to_csv(OUTPUT_DIR / "pem_analysis_charge_discharge_summary.csv", index=False)
    full_cycle_summary.to_csv(OUTPUT_DIR / "pem_analysis_full_cycle_summary.csv", index=False)
    collapse_points.to_csv(OUTPUT_DIR / "pem_analysis_collapse_points.csv", index=False)
    polarization_charge_summary.to_csv(OUTPUT_DIR / "pem_analysis_polarization_charge_summary.csv", index=False)

    if len(polarization_summary) > 0:
        polarization_summary.to_csv(OUTPUT_DIR / "pem_analysis_polarization_summary.csv", index=False)


def make_plots(charge_summary, minimum_usable_voltage_v, polarization_summary, collapse_points):
    plot_charge_discharge(minimum_usable_voltage_v)
    plot_discharge_collapse_diagnostics(collapse_points, minimum_usable_voltage_v)
    plot_summary_lines(
        charge_summary,
        "charge_duration_setpoint_s",
        "hydrogen_volume_mL",
        "Hydrogen volume [mL]",
        "Hydrogen Production During PEM Charging",
        "pem_hydrogen_volume_vs_charge_time.png",
    )
    plot_polarization_curve(minimum_usable_voltage_v, polarization_summary)
    plot_polarization_power_curve(minimum_usable_voltage_v, polarization_summary)

    return polarization_summary


def main():
    remove_obsolete_outputs()
    volume_data = load_volume_data()
    collapse_points = collect_discharge_collapse_points()
    minimum_usable_voltage_v = minimum_usable_voltage_from_collapse(collapse_points)

    polarization_summary = summarize_polarization_curve(minimum_usable_voltage_v)
    polarization_charge_summary = summarize_polarization_charge()

    charge_summary = summarize_charge_discharge_tests(volume_data, minimum_usable_voltage_v)
    full_cycle_summary, _, _ = summarize_full_cycle(minimum_usable_voltage_v)
    control_parameters = make_control_parameters(
        charge_summary,
        minimum_usable_voltage_v,
        full_cycle_summary,
        polarization_summary,
        polarization_charge_summary,
    )

    save_outputs(
        charge_summary,
        full_cycle_summary,
        control_parameters,
        polarization_summary,
        collapse_points,
        polarization_charge_summary,
    )
    make_plots(charge_summary, minimum_usable_voltage_v, polarization_summary, collapse_points)

    print("\nPEM control parameters:")
    print(control_parameters)
    print("\nPEM analysis full cycle summary:")
    print(full_cycle_summary)
    print("\nPEM analysis collapse points:")
    print(collapse_points)
    print("\nPEM analysis polarization summary:")
    print(polarization_summary)
    print("\nPEM analysis polarization charge summary:")
    print(polarization_charge_summary)
    print("\nSaved output files in:")
    print(OUTPUT_DIR)
    print("\nSaved plots in:")
    print(PLOT_DIR)


if __name__ == "__main__":
    main()
