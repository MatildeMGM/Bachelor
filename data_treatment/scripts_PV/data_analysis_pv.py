"""
PV Panel Analysis Script
Analyzes PV test data from different light intensities (distances)
Extracts operating thresholds and creates PV state characterization
"""

from pathlib import Path
import sys
import re
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def find_bachelor_dir():
    """Locate the bachelor project root directory"""
    script_dir = Path(__file__).resolve().parent
    for parent in [script_dir] + list(script_dir.parents):
        if (parent / "data").exists() and (parent / "data_treatment").exists():
            return parent
    raise FileNotFoundError("Could not find bachelor folder")


BACHELOR_DIR = find_bachelor_dir()
sys.path.append(str(BACHELOR_DIR))

from control_parameters_new.plot_style import DISTANCE_COLORS, PURPLE, BLUE, polish_axes, save_report_figure, set_report_style

DATA_DIR = BACHELOR_DIR / "data" / "PV_test" / "New_test"
OUTPUT_DIR = BACHELOR_DIR / "app" / "python" / "data" / "processed_PV"
PROCESSED_BATTERY_DIR = BACHELOR_DIR / "app" / "python" / "data" / "processed_Battery"
PROCESSED_PEM_DIR = BACHELOR_DIR / "app" / "python" / "data" / "processed_PEM"
LOAD_DEMAND_DIR = BACHELOR_DIR / "app" / "python" / "data" / "variable_load_signal"
PLOT_DIR = BACHELOR_DIR / "data_treatment" / "plots" / "pv_plots"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
PLOT_DIR.mkdir(parents=True, exist_ok=True)

# Sensor calibration for INA226 sensors (from sketch constants)
# Address mapping: 0x40=Battery(ina1), 0x41=Load(ina2), 0x44=PV(ina3), 0x45=PEM(ina4)
PV_SENSOR = 0x44  # PV panel INA226 address (ina3)
VOLTAGE_CORRECTION = {
    0x40: lambda v: v - 0.068,  # Battery (ina1)
    0x41: lambda v: v - 0.066,  # Load (ina2)
    0x44: lambda v: v - 0.180,  # PV (ina3)
    0x45: lambda v: v - 0.064,  # PEM (ina4)
}

CURRENT_CORRECTION = {
    0x40: lambda i: i + 0.000563,  # Battery (ina1)
    0x41: lambda i: i - 0.000033,  # Load (ina2)
    0x44: lambda i: i + 0.000138,  # PV (ina3)
    0x45: lambda i: 0.843 * i + 0.001,  # PEM (ina4)
}

# Manually inspected windows from the full corrected time-series plot.
# These remove only the clearly delayed stopped-log tails after the sweep has
# collapsed, while keeping the open-circuit/startup and short-circuit behavior.
PV_TEST_WINDOWS_S = {
    1: (0, 141),
    5: (0, 120),
    10: (0, 115),
    15: (0, 98),
    20: (0, 69),
}

OBSOLETE_OUTPUTS = [
    OUTPUT_DIR / "pv_test_summary.csv",
    OUTPUT_DIR / "pv_state_table.csv",
    PLOT_DIR / "pv_analysis_summary.png",
    PLOT_DIR / "pv_full_corrected_series.png",
    PLOT_DIR / "pv_operating_states.png",
    PLOT_DIR / "pv_voltage_vs_distance.png",
]

TASKS = {
    "battery_charging": {
        "label": "Battery charging",
        "power_column": "min_pv_power_for_battery_charging_mW",
        "voltage_column": "min_pv_voltage_for_battery_charging_V",
        "summary_column": "min_voltage_for_battery_charging_V",
        "color": "#2E8B57",
    },
    "pem_charging": {
        "label": "PEM charging",
        "power_column": "min_pv_power_for_pem_charging_mW",
        "voltage_column": "min_pv_voltage_for_pem_charging_V",
        "summary_column": "min_voltage_for_pem_charging_V",
        "color": "#7B4FA3",
    },
    "load_supply": {
        "label": "Load supply",
        "power_column": "min_pv_power_for_load_supply_mW",
        "voltage_column": "min_pv_voltage_for_load_supply_V",
        "summary_column": "min_voltage_for_load_supply_V",
        "color": "#C27C2C",
    },
}


def warn(message):
    print(f"WARNING: {message}")


def extract_distance_from_filename(file_path):
    """Extract distance in cm from filenames like PV_01cm_ramp.csv or PV_1cm_ramp.csv."""
    match = re.search(r"pv_0?(\d+)cm", file_path.stem.lower())
    return int(match.group(1)) if match else None


def read_pv_log(file_path):
    """
    Read PV test log file and extract relevant sensor data.
    ina3 is the PV panel in the EMS logger.
    Applies the INA226 calibration corrections before calculating PV power.
    """
    df = pd.read_csv(file_path)
    df.columns = df.columns.str.strip()
    
    # Parse timestamp
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["time_s"] = (df["timestamp"] - df["timestamp"].iloc[0]).dt.total_seconds()
    
    # Extract and correct PV sensor data (ina3 / 0x44).
    raw_voltage_V = pd.to_numeric(df["ina3_bus_V"], errors="coerce")
    raw_current_A = pd.to_numeric(df["ina3_current_mA"], errors="coerce") / 1000

    df["pv_voltage_V"] = VOLTAGE_CORRECTION[PV_SENSOR](raw_voltage_V)
    df["pv_current_A"] = CURRENT_CORRECTION[PV_SENSOR](raw_current_A)
    
    # Calculate corrected power (positive = sourcing from PV)
    df["pv_power_mW"] = df["pv_voltage_V"] * df["pv_current_A"] * 1000
    
    # Clean data - remove only missing values. Keep the corrected measurement
    # behavior, including low voltage and reverse-current regions.
    df = df.dropna(subset=["time_s", "pv_voltage_V", "pv_current_A", "pv_power_mW"])
    
    return df[["timestamp", "time_s", "pv_voltage_V", "pv_current_A", "pv_power_mW"]].copy()


def apply_inspected_test_window(df, distance_cm):
    """Trim only visually inspected stopped-log tails from the corrected data."""
    if distance_cm not in PV_TEST_WINDOWS_S:
        return df.copy()

    start_s, end_s = PV_TEST_WINDOWS_S[distance_cm]
    return df[(df["time_s"] >= start_s) & (df["time_s"] <= end_s)].copy()


def finite_float(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return np.nan

    return value if np.isfinite(value) else np.nan


def load_single_row_csv(path, source_name):
    if not path.exists():
        warn(f"{source_name} not found: {path}")
        return None

    df = pd.read_csv(path)
    if len(df) == 0:
        warn(f"{source_name} is empty: {path}")
        return None

    return df.iloc[0]


def load_positive_column_value(path, column, source_name, *, aggregation="max"):
    if not path.exists():
        warn(f"{source_name} not found: {path}")
        return np.nan

    df = pd.read_csv(path)
    if column not in df.columns:
        warn(f"{source_name} has no '{column}' column")
        return np.nan

    values = pd.to_numeric(df[column], errors="coerce")
    values = values[np.isfinite(values) & (values > 0)]
    if len(values) == 0:
        warn(f"{source_name} contains no positive values in '{column}'")
        return np.nan

    if aggregation == "median":
        return float(values.median())

    return float(values.max())


def load_battery_charging_power_mW():
    """
    Use the measured battery charge power as the PV-to-battery task requirement.
    The maximum observed charge power is conservative for EMS switching.
    """
    row = load_single_row_csv(
        PROCESSED_BATTERY_DIR / "battery_charge_summary.csv",
        "processed battery charge summary",
    )
    if row is None or "max_power_W" not in row.index:
        warn("Battery charging power threshold could not be derived from processed battery data")
        return np.nan

    power_w = finite_float(row["max_power_W"])
    if pd.isna(power_w) or power_w <= 0:
        warn("Battery charging power threshold is missing or non-positive in processed battery data")
        return np.nan

    return power_w * 1000


def load_pem_charging_power_mW():
    """
    Use measured electrolysis input power as the PV-to-PEM task requirement.
    The largest stable charge-test average is used as a defensible conservative
    requirement instead of inventing a nominal value.
    """
    charge_power_mw = load_positive_column_value(
        PROCESSED_PEM_DIR / "pem_analysis_charge_discharge_summary.csv",
        "avg_charge_power_W",
        "processed PEM charge/discharge analysis",
        aggregation="max",
    )
    if not pd.isna(charge_power_mw):
        return charge_power_mw * 1000

    row = load_single_row_csv(
        PROCESSED_PEM_DIR / "pem_analysis_polarization_charge_summary.csv",
        "processed PEM polarization charge analysis",
    )
    if row is None or "input_energy_J" not in row.index or "charge_duration_s" not in row.index:
        warn("PEM charging power threshold could not be derived from processed PEM data")
        return np.nan

    input_energy_j = finite_float(row["input_energy_J"])
    charge_duration_s = finite_float(row["charge_duration_s"])
    if (
        pd.isna(input_energy_j)
        or pd.isna(charge_duration_s)
        or input_energy_j <= 0
        or charge_duration_s <= 0
    ):
        warn("PEM charging power threshold is missing or non-positive in processed PEM data")
        return np.nan

    return 1000 * input_energy_j / charge_duration_s


def load_load_supply_power_mW():
    """
    Use the processed demand profile as the PV-to-load supply requirement.
    Maximum demand is the conservative value for direct load supply.
    """
    return load_positive_column_value(
        LOAD_DEMAND_DIR / "scaled_may_power_profile_15min.csv",
        "power_mW",
        "processed scaled load demand profile",
        aggregation="max",
    )


def load_task_power_requirements():
    # Task thresholds come from component or demand data. If a threshold cannot
    # be justified from processed data, it stays NaN so the exported EMS file
    # does not silently contain an invented switching value.
    requirements = {
        "battery_charging": load_battery_charging_power_mW(),
        "pem_charging": load_pem_charging_power_mW(),
        "load_supply": load_load_supply_power_mW(),
    }

    for task, power_mw in requirements.items():
        if pd.isna(power_mw):
            warn(f"{TASKS[task]['label']} PV power requirement is NaN")
        else:
            print(f"{TASKS[task]['label']} power requirement: {power_mw:.2f} mW")

    return requirements


def voltage_at_power_threshold(df, threshold_mW):
    """
    Return the ramp voltage where corrected PV power first reaches a task load.

    PV power is P = V * I using the corrected INA226 PV voltage and current.
    Open-circuit voltage by itself cannot prove usable power, so EMS thresholds
    are derived from the measured power-voltage ramp instead.
    """
    if pd.isna(threshold_mW) or threshold_mW <= 0:
        return np.nan

    ramp = df.sort_values("time_s")
    candidates = ramp[ramp["pv_power_mW"] >= threshold_mW]
    if candidates.empty:
        return np.nan
    return float(candidates.iloc[0]["pv_voltage_V"])


def extract_threshold_metrics(df, task_power_requirements):
    """Extract only the corrected PV values needed for EMS threshold selection."""
    if len(df) < 2:
        return None

    # MPP values characterize the PV panel at each lamp distance. They are not
    # used directly as EMS switching thresholds because EMS tasks depend on the
    # power required by the battery, PEM electrolyser, or load.
    mpp_idx = df["pv_power_mW"].idxmax()
    mpp_row = df.loc[mpp_idx]

    # Voltage thresholds are found where corrected PV power first exceeds each
    # component task requirement in the ramp data.
    metrics = {
        "mpp_time_s": mpp_row["time_s"],
        "mpp_voltage_V": mpp_row["pv_voltage_V"],
        "mpp_current_A": mpp_row["pv_current_A"],
        "mpp_power_mW": mpp_row["pv_power_mW"],
        "max_voltage_V": df["pv_voltage_V"].max(),
        "max_current_A": df["pv_current_A"].max(),
        "max_power_mW": df["pv_power_mW"].max(),
    }

    for task, threshold_mw in task_power_requirements.items():
        metrics[TASKS[task]["summary_column"]] = voltage_at_power_threshold(df, threshold_mw)

    return metrics


def analyze_all_tests(task_power_requirements):
    """Main analysis function: process all distance files"""
    results = []
    
    distance_files = sorted(DATA_DIR.glob("PV_*cm_ramp.csv"))
    
    for file_path in distance_files:
        distance_cm = extract_distance_from_filename(file_path)
        
        print(f"Processing {file_path.name} (distance: {distance_cm} cm)...")
        
        try:
            df = apply_inspected_test_window(read_pv_log(file_path), distance_cm)
            metrics = extract_threshold_metrics(df, task_power_requirements)
            
            if metrics:
                metrics["distance_cm"] = distance_cm
                metrics["file"] = file_path.name
                results.append(metrics)
                
                print(f"  MPP Power: {metrics['mpp_power_mW']:.2f} mW @ {distance_cm} cm")
                print(f"  MPP Current: {metrics['mpp_current_A']:.3f} A")
                
        except Exception as e:
            print(f"  ERROR: {e}")
    
    columns = [
        "distance_cm",
        "file",
        "mpp_time_s",
        "mpp_voltage_V",
        "mpp_current_A",
        "mpp_power_mW",
        "max_voltage_V",
        "max_current_A",
        "max_power_mW",
    ] + [task["summary_column"] for task in TASKS.values()]
    return pd.DataFrame(results).reindex(columns=columns)


def conservative_voltage_threshold(summary_df, column):
    values = pd.to_numeric(summary_df[column], errors="coerce").dropna()
    if len(values) == 0:
        warn(f"No PV ramp reached '{column}', EMS voltage threshold is NaN")
        return np.nan

    median_value = float(values.median())
    conservative_value = float(values.max())
    print(
        f"{column}: median={median_value:.3f} V, "
        f"conservative EMS value={conservative_value:.3f} V"
    )
    return conservative_value


def create_operating_thresholds(summary_df, task_power_requirements):
    """
    Create final EMS control parameters from corrected, windowed PV data.

    Per-distance threshold voltages are aggregated conservatively with the
    maximum reached threshold voltage. This avoids an overly optimistic EMS
    threshold based on only the easiest lamp distance.
    """
    thresholds = {}
    for task, config in TASKS.items():
        thresholds[config["voltage_column"]] = [
            conservative_voltage_threshold(summary_df, config["summary_column"])
        ]
        thresholds[config["power_column"]] = [task_power_requirements[task]]

    # Maximum PV values are measured during the lamp ramp tests. They document
    # the observed test range, not guaranteed available current or power under
    # every EMS operating condition.
    thresholds.update({
        "max_measured_pv_voltage_V": [summary_df["max_voltage_V"].max()],
        "max_measured_pv_current_A": [summary_df["max_current_A"].max()],
        "max_measured_pv_power_mW": [summary_df["max_power_mW"].max()],
    })
    
    return pd.DataFrame(thresholds)


def generate_mpp_plots(summary_df):
    """Generate report-ready PV characterization plots."""
    set_report_style()
    summary_df = summary_df.sort_values("distance_cm")
    
    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    ax.plot(
        summary_df["distance_cm"],
        summary_df["mpp_power_mW"],
        marker="o",
        color=BLUE,
        label="Maximum power point",
    )
    ax.invert_xaxis()
    ax.set_xlabel("Lamp distance [cm]")
    ax.set_ylabel("PV power [mW]")
    ax.set_title("PV Maximum Power Under Different Illumination Levels")
    ax.legend(loc="upper right")
    polish_axes(ax)
    save_report_figure(fig, PLOT_DIR / "pv_power_vs_distance.png")
    
    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    ax.plot(
        summary_df["distance_cm"],
        summary_df["mpp_current_A"] * 1000,
        marker="o",
        color=PURPLE,
        label="Current at MPP",
    )
    ax.invert_xaxis()
    ax.set_xlabel("Lamp distance [cm]")
    ax.set_ylabel("PV current [mA]")
    ax.set_title("PV Current at Maximum Power")
    ax.legend(loc="best")
    polish_axes(ax)
    save_report_figure(fig, PLOT_DIR / "pv_current_vs_distance.png")


def generate_power_voltage_threshold_plot(summary_df, task_power_requirements):
    """Show how task power requirements are translated to PV voltage limits."""
    set_report_style()
    distance_files = sorted(DATA_DIR.glob("PV_*cm_ramp.csv"))

    fig, ax = plt.subplots(figsize=(9.4, 5.8))

    for file_path in distance_files:
        distance_cm = extract_distance_from_filename(file_path)
        df = apply_inspected_test_window(read_pv_log(file_path), distance_cm)
        color = DISTANCE_COLORS.get(distance_cm, BLUE)
        label = f"{distance_cm} cm"
        ax.plot(df["pv_voltage_V"], df["pv_power_mW"], color=color, alpha=0.85, label=label)

        match = summary_df[summary_df["distance_cm"] == distance_cm]
        if len(match) == 0:
            continue
        row = match.iloc[0]

        for task, config in TASKS.items():
            threshold_voltage = row[config["summary_column"]]
            threshold_power = task_power_requirements[task]
            if pd.isna(threshold_voltage) or pd.isna(threshold_power):
                continue
            ax.scatter(
                threshold_voltage,
                threshold_power,
                s=44,
                color=config["color"],
                edgecolors="white",
                linewidth=0.8,
                zorder=5,
            )

    for task, config in TASKS.items():
        threshold_power = task_power_requirements[task]
        if pd.isna(threshold_power):
            continue
        ax.axhline(
            threshold_power,
            color=config["color"],
            linestyle="--",
            linewidth=1.5,
            alpha=0.9,
            label=f"{config['label']}: {threshold_power:.1f} mW",
        )

    ax.set_xlabel("Corrected PV voltage [V]")
    ax.set_ylabel("Corrected PV power [mW]")
    ax.set_title("PV Task Power Thresholds from Ramp Tests")
    ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1.0), borderaxespad=0)
    polish_axes(ax)
    fig.tight_layout(rect=(0, 0, 0.78, 1))
    fig.savefig(PLOT_DIR / "pv_power_voltage_task_thresholds.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def generate_corrected_series_plot(windowed, filename, title):
    """
    Plot corrected PV voltage, current and power versus time.

    Before-window plots show sensor-corrected raw behavior. After-window plots
    show the manually inspected data used for EMS threshold calculations.
    """
    set_report_style()
    distance_files = sorted(DATA_DIR.glob("PV_*cm_ramp.csv"))

    fig, axes = plt.subplots(3, 1, figsize=(10.0, 10.0), sharex=True)
    voltage_ax, current_ax, power_ax = axes

    for file_path in distance_files:
        distance_cm = extract_distance_from_filename(file_path)
        df = read_pv_log(file_path)
        if windowed:
            df = apply_inspected_test_window(df, distance_cm)

        color = DISTANCE_COLORS.get(distance_cm, BLUE)
        label = f"{distance_cm} cm"

        voltage_ax.plot(df["time_s"], df["pv_voltage_V"], color=color, label=label)
        current_ax.plot(df["time_s"], df["pv_current_A"] * 1000, color=color, label=label)
        power_ax.plot(df["time_s"], df["pv_power_mW"], color=color, label=label)

    voltage_ax.set_ylabel("PV voltage [V]")
    current_ax.set_ylabel("PV current [mA]")
    power_ax.set_ylabel("PV power [mW]")
    power_ax.set_xlabel("Time [s]")

    voltage_ax.set_title(title)
    voltage_ax.legend(loc="best")

    for ax in axes:
        polish_axes(ax)

    save_report_figure(fig, PLOT_DIR / filename)


def remove_obsolete_outputs():
    """Remove old broad-summary outputs that are no longer part of PV treatment."""
    for path in OBSOLETE_OUTPUTS:
        if path.exists():
            path.unlink()


def main():
    """Main execution"""
    print("=" * 60)

    remove_obsolete_outputs()
    print("PV Panel Analysis")
    print("=" * 60)

    task_power_requirements = load_task_power_requirements()
    
    # Analyze all test files
    summary_df = analyze_all_tests(task_power_requirements)
    
    if len(summary_df) == 0:
        print("ERROR: No test files processed successfully!")
        return
    
    print(f"\nProcessed {len(summary_df)} test files")
    
    # Create operating thresholds
    thresholds = create_operating_thresholds(summary_df, task_power_requirements)
    print("Created operating thresholds")
    
    # Save outputs
    summary_df.to_csv(OUTPUT_DIR / "pv_threshold_summary.csv", index=False)
    thresholds.to_csv(OUTPUT_DIR / "pv_control_parameters.csv", index=False)
    
    print(f"\nOutputs saved to {OUTPUT_DIR}")
    
    # Generate plots
    generate_corrected_series_plot(
        windowed=False,
        filename="pv_corrected_series_before_windowing.png",
        title="Corrected PV Test Series Before Windowing",
    )
    generate_corrected_series_plot(
        windowed=True,
        filename="pv_corrected_series_after_windowing.png",
        title="Corrected PV Test Series After Windowing",
    )
    generate_mpp_plots(summary_df)
    generate_power_voltage_threshold_plot(summary_df, task_power_requirements)
    
    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("\nPV Threshold Summary:")
    print(summary_df.to_string())
    
    print("\n\nOperating Thresholds:")
    print(thresholds.to_string())


if __name__ == "__main__":
    main()
