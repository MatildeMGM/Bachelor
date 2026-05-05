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

from data_treatment.plots.plot_style import DISTANCE_COLORS, PURPLE, BLUE, polish_axes, save_report_figure, set_report_style

DATA_DIR = BACHELOR_DIR / "data" / "PV_test" / "New_test"
OUTPUT_DIR = BACHELOR_DIR / "app" / "python" / "data" / "processed_PV"
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


def voltage_at_power_threshold(df, threshold_mW):
    """Return the lowest voltage where corrected PV power reaches a threshold."""
    candidates = df[df["pv_power_mW"] >= threshold_mW]
    if candidates.empty:
        return np.nan
    return candidates["pv_voltage_V"].min()


def extract_threshold_metrics(df):
    """Extract only the corrected PV values needed for EMS threshold selection."""
    if len(df) < 2:
        return None

    # MPP values characterize PV capability at each lamp distance.
    mpp_idx = df["pv_power_mW"].idxmax()
    mpp_row = df.loc[mpp_idx]

    # Voltage at fixed power thresholds is used for EMS control design.
    return {
        "mpp_voltage_V": mpp_row["pv_voltage_V"],
        "mpp_current_A": mpp_row["pv_current_A"],
        "mpp_power_mW": mpp_row["pv_power_mW"],
        "min_voltage_for_20mW": voltage_at_power_threshold(df, 20),
        "min_voltage_for_50mW": voltage_at_power_threshold(df, 50),
        "max_voltage_V": df["pv_voltage_V"].max(),
        "max_current_A": df["pv_current_A"].max(),
        "max_power_mW": df["pv_power_mW"].max(),
    }


def analyze_all_tests():
    """Main analysis function: process all distance files"""
    results = []
    
    distance_files = sorted(DATA_DIR.glob("PV_*cm_ramp.csv"))
    
    for file_path in distance_files:
        distance_cm = extract_distance_from_filename(file_path)
        
        print(f"Processing {file_path.name} (distance: {distance_cm} cm)...")
        
        try:
            df = apply_inspected_test_window(read_pv_log(file_path), distance_cm)
            metrics = extract_threshold_metrics(df)
            
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
        "mpp_voltage_V",
        "mpp_current_A",
        "mpp_power_mW",
        "min_voltage_for_20mW",
        "min_voltage_for_50mW",
        "max_voltage_V",
        "max_current_A",
        "max_power_mW",
    ]
    return pd.DataFrame(results).reindex(columns=columns)


def create_operating_thresholds(summary_df):
    """
    Create final EMS control parameters from corrected, windowed PV data.
    """
    thresholds = {
        "min_pv_voltage_for_charging_V": [summary_df["min_voltage_for_20mW"].min()],
        "min_pv_voltage_for_load_V": [summary_df["min_voltage_for_50mW"].min()],
        "max_pv_voltage_V": [summary_df["max_voltage_V"].max()],
        "max_available_current_A": [summary_df["max_current_A"].max()],
        "max_available_power_mW": [summary_df["max_power_mW"].max()],
        "min_usable_power_for_charging_mW": [20],
        "min_usable_power_for_load_mW": [50],
    }
    
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
    
    # Analyze all test files
    summary_df = analyze_all_tests()
    
    if len(summary_df) == 0:
        print("ERROR: No test files processed successfully!")
        return
    
    print(f"\nProcessed {len(summary_df)} test files")
    
    # Create operating thresholds
    thresholds = create_operating_thresholds(summary_df)
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
