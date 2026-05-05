"""
PV Panel Analysis Script
Analyzes PV test data from different light intensities (distances)
Extracts operating thresholds and creates PV state characterization
"""

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def find_bachelor_dir():
    """Locate the bachelor project root directory"""
    script_dir = Path(__file__).resolve().parent
    for parent in [script_dir] + list(script_dir.parents):
        if (parent / "data").exists() and (parent / "data_treatment").exists():
            return parent
    raise FileNotFoundError("Could not find bachelor folder")


BACHELOR_DIR = find_bachelor_dir()
DATA_DIR = BACHELOR_DIR / "data" / "PV_test" / "New_test"
OUTPUT_DIR = BACHELOR_DIR / "data_treatment" / "processed_PV"
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


def extract_distance_from_filename(file_path):
    """Extract distance in cm from filename (e.g., 'PV_01cm_ramp.csv' -> 1)"""
    name = file_path.stem.lower()
    if "01cm" in name:
        return 1
    elif "05cm" in name:
        return 5
    elif "10cm" in name:
        return 10
    elif "15cm" in name:
        return 15
    elif "20cm" in name:
        return 20
    return None


def read_pv_log(file_path):
    """
    Read PV test log file and extract relevant sensor data.
    ina2 is the PV panel (based on voltage 4.2-4.6V and positive current).
    Uses raw data without calibration to avoid systematic errors.
    """
    df = pd.read_csv(file_path)
    df.columns = df.columns.str.strip()
    
    # Parse timestamp
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["time_s"] = (df["timestamp"] - df["timestamp"].iloc[0]).dt.total_seconds()
    
    # Extract PV sensor data (ina2 - voltage 4.2-4.6V, positive current = supply)
    # Use raw data without calibration since calibration constants may be for different sensor
    df["pv_voltage_V"] = pd.to_numeric(df["ina2_bus_V"], errors="coerce")
    df["pv_current_A"] = pd.to_numeric(df["ina2_current_mA"], errors="coerce") / 1000
    
    # Calculate power (positive = sourcing from PV)
    df["pv_power_mW"] = df["pv_voltage_V"] * df["pv_current_A"] * 1000
    
    # Clean data - remove non-physical values
    df = df.dropna(subset=["time_s", "pv_voltage_V", "pv_current_A", "pv_power_mW"])
    df = df[df["pv_voltage_V"] > 2.0]  # Filter out noise at low voltages
    df = df[df["pv_current_A"] > -0.1]  # Filter out large negative currents
    
    return df[["timestamp", "time_s", "pv_voltage_V", "pv_current_A", "pv_power_mW"]].copy()


def identify_ramp_start(df, threshold_A=0.05):
    """
    Identify where the current ramp actually starts (above noise).
    Useful for handling startup transients.
    """
    current = df["pv_current_A"].to_numpy()
    candidates = np.where(current > threshold_A)[0]
    
    if len(candidates) > 0:
        return candidates[0]
    return 0


def extract_steady_state_metrics(df, start_idx=0):
    """
    Extract steady-state metrics from the test data.
    Assumes data ramped to maximum and held briefly.
    """
    if start_idx > 0 and start_idx < len(df):
        df = df.iloc[start_idx:].copy()
    
    if len(df) < 2:
        return None
    
    metrics = {
        "ramp_duration_s": df["time_s"].iloc[-1] - df["time_s"].iloc[0],
        "min_voltage_V": df["pv_voltage_V"].min(),
        "max_voltage_V": df["pv_voltage_V"].max(),
        "avg_voltage_V": df["pv_voltage_V"].mean(),
        "min_current_A": df["pv_current_A"].min(),
        "max_current_A": df["pv_current_A"].max(),
        "avg_current_A": df["pv_current_A"].mean(),
        "min_power_mW": df["pv_power_mW"].min(),
        "max_power_mW": df["pv_power_mW"].max(),
        "avg_power_mW": df["pv_power_mW"].mean(),
    }
    
    # Estimate steady-state (last 20% of ramp)
    ss_start = int(0.8 * len(df))
    if ss_start < len(df):
        ss_data = df.iloc[ss_start:]
        metrics.update({
            "ss_avg_voltage_V": ss_data["pv_voltage_V"].mean(),
            "ss_avg_current_A": ss_data["pv_current_A"].mean(),
            "ss_avg_power_mW": ss_data["pv_power_mW"].mean(),
            "ss_min_power_mW": ss_data["pv_power_mW"].min(),
            "ss_max_power_mW": ss_data["pv_power_mW"].max(),
        })
    
    return metrics


def analyze_all_tests():
    """Main analysis function: process all distance files"""
    results = []
    
    distance_files = sorted(DATA_DIR.glob("PV_*cm_ramp.csv"))
    
    for file_path in distance_files:
        distance_cm = extract_distance_from_filename(file_path)
        
        print(f"Processing {file_path.name} (distance: {distance_cm} cm)...")
        
        try:
            df = read_pv_log(file_path)
            start_idx = identify_ramp_start(df)
            metrics = extract_steady_state_metrics(df, start_idx)
            
            if metrics:
                metrics["distance_cm"] = distance_cm
                metrics["file"] = file_path.name
                results.append(metrics)
                
                print(f"  Max Power: {metrics['ss_avg_power_mW']:.2f} mW @ {distance_cm} cm")
                print(f"  Max Current: {metrics['ss_avg_current_A']:.3f} A")
                
        except Exception as e:
            print(f"  ERROR: {e}")
    
    return pd.DataFrame(results)


def create_pv_state_table(summary_df):
    """
    Create a PV state table categorizing light intensity levels
    based on power output and voltage characteristics.
    """
    # Sort by distance (closer = higher intensity)
    summary_df = summary_df.sort_values("distance_cm")
    
    # Define light intensity states based on power output
    # Using quartiles of available power as state boundaries
    power_values = summary_df["ss_avg_power_mW"].values
    
    # Define state boundaries
    states = []
    
    # Very low/dim light
    states.append({
        "light_state": "DIM",
        "distance_cm": 20,
        "min_distance_cm": 17,
        "max_distance_cm": 20,
        "avg_voltage_V": summary_df[summary_df["distance_cm"] == 20]["ss_avg_voltage_V"].values[0],
        "avg_power_mW": summary_df[summary_df["distance_cm"] == 20]["ss_avg_power_mW"].values[0],
        "max_current_A": summary_df[summary_df["distance_cm"] == 20]["ss_avg_current_A"].values[0],
    })
    
    # Low light
    if (summary_df["distance_cm"] == 15).any():
        states.append({
            "light_state": "LOW",
            "distance_cm": 15,
            "min_distance_cm": 12,
            "max_distance_cm": 18,
            "avg_voltage_V": summary_df[summary_df["distance_cm"] == 15]["ss_avg_voltage_V"].values[0],
            "avg_power_mW": summary_df[summary_df["distance_cm"] == 15]["ss_avg_power_mW"].values[0],
            "max_current_A": summary_df[summary_df["distance_cm"] == 15]["ss_avg_current_A"].values[0],
        })
    
    # Medium light
    if (summary_df["distance_cm"] == 10).any():
        states.append({
            "light_state": "MEDIUM",
            "distance_cm": 10,
            "min_distance_cm": 8,
            "max_distance_cm": 12,
            "avg_voltage_V": summary_df[summary_df["distance_cm"] == 10]["ss_avg_voltage_V"].values[0],
            "avg_power_mW": summary_df[summary_df["distance_cm"] == 10]["ss_avg_power_mW"].values[0],
            "max_current_A": summary_df[summary_df["distance_cm"] == 10]["ss_avg_current_A"].values[0],
        })
    
    # High light
    if (summary_df["distance_cm"] == 5).any():
        states.append({
            "light_state": "HIGH",
            "distance_cm": 5,
            "min_distance_cm": 3,
            "max_distance_cm": 8,
            "avg_voltage_V": summary_df[summary_df["distance_cm"] == 5]["ss_avg_voltage_V"].values[0],
            "avg_power_mW": summary_df[summary_df["distance_cm"] == 5]["ss_avg_power_mW"].values[0],
            "max_current_A": summary_df[summary_df["distance_cm"] == 5]["ss_avg_current_A"].values[0],
        })
    
    # Very high/bright light
    if (summary_df["distance_cm"] == 1).any():
        states.append({
            "light_state": "BRIGHT",
            "distance_cm": 1,
            "min_distance_cm": 0,
            "max_distance_cm": 3,
            "avg_voltage_V": summary_df[summary_df["distance_cm"] == 1]["ss_avg_voltage_V"].values[0],
            "avg_power_mW": summary_df[summary_df["distance_cm"] == 1]["ss_avg_power_mW"].values[0],
            "max_current_A": summary_df[summary_df["distance_cm"] == 1]["ss_avg_current_A"].values[0],
        })
    
    return pd.DataFrame(states)


def create_operating_thresholds(summary_df, state_table):
    """
    Create a control parameters table with key thresholds for algorithm.
    """
    # Find minimum usable voltage (lowest voltage with meaningful power)
    min_voltage = summary_df["ss_avg_voltage_V"].min()
    max_voltage = summary_df["ss_avg_voltage_V"].max()
    
    # Find maximum available current
    max_current = summary_df["ss_avg_current_A"].max()
    
    # Find power levels for decision thresholds
    max_power = summary_df["ss_avg_power_mW"].max()
    min_usable_power = summary_df["ss_avg_power_mW"].min() * 0.5  # Conservative estimate
    
    thresholds = {
        "min_pv_voltage_V": [max(min_voltage - 0.1, 2.0)],  # Minimum voltage to expect PV
        "max_pv_voltage_V": [max_voltage + 0.2],
        "max_available_current_A": [max_current],
        "max_available_power_mW": [max_power],
        "min_usable_power_for_charging_mW": [max(min_usable_power, 20)],  # Threshold to start charging
        "min_usable_power_for_load_mW": [max(min_usable_power, 50)],  # Threshold for direct load supply
    }
    
    return pd.DataFrame(thresholds)


def generate_plots(summary_df, state_table):
    """Generate visualization plots"""
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    
    # Plot 1: Power vs Distance
    ax = axes[0, 0]
    ax.plot(summary_df["distance_cm"], summary_df["ss_avg_power_mW"], 'bo-', label='Avg Power')
    ax.fill_between(summary_df["distance_cm"], 
                     summary_df["ss_min_power_mW"],
                     summary_df["ss_max_power_mW"],
                     alpha=0.3, label='Min-Max Range')
    ax.set_xlabel('Distance (cm)')
    ax.set_ylabel('Power (mW)')
    ax.set_title('PV Power Output vs Light Intensity (Distance)')
    ax.grid(True, alpha=0.3)
    ax.legend()
    
    # Plot 2: Voltage vs Distance
    ax = axes[0, 1]
    ax.plot(summary_df["distance_cm"], summary_df["ss_avg_voltage_V"], 'go-')
    ax.set_xlabel('Distance (cm)')
    ax.set_ylabel('Voltage (V)')
    ax.set_title('PV Voltage vs Light Intensity')
    ax.grid(True, alpha=0.3)
    
    # Plot 3: Current vs Distance
    ax = axes[1, 0]
    ax.plot(summary_df["distance_cm"], summary_df["ss_avg_current_A"], 'ro-')
    ax.set_xlabel('Distance (cm)')
    ax.set_ylabel('Current (A)')
    ax.set_title('PV Current vs Light Intensity')
    ax.grid(True, alpha=0.3)
    
    # Plot 4: State Table Summary
    ax = axes[1, 1]
    ax.axis('off')
    state_text = "PV Light States:\n\n"
    for idx, row in state_table.iterrows():
        state_text += f"{row['light_state']}:\n"
        state_text += f"  Dist: {row['distance_cm']} cm\n"
        state_text += f"  Power: {row['avg_power_mW']:.1f} mW\n"
        state_text += f"  Voltage: {row['avg_voltage_V']:.2f} V\n\n"
    ax.text(0.1, 0.5, state_text, fontsize=10, family='monospace',
            verticalalignment='center')
    
    plt.tight_layout()
    plt.savefig(PLOT_DIR / "pv_analysis_summary.png", dpi=150)
    print(f"Saved plot to {PLOT_DIR / 'pv_analysis_summary.png'}")
    plt.close()


def main():
    """Main execution"""
    print("=" * 60)
    print("PV Panel Analysis")
    print("=" * 60)
    
    # Analyze all test files
    summary_df = analyze_all_tests()
    
    if len(summary_df) == 0:
        print("ERROR: No test files processed successfully!")
        return
    
    print(f"\nProcessed {len(summary_df)} test files")
    
    # Create state table
    state_table = create_pv_state_table(summary_df)
    print(f"\nCreated PV state table with {len(state_table)} states")
    
    # Create operating thresholds
    thresholds = create_operating_thresholds(summary_df, state_table)
    print("Created operating thresholds")
    
    # Save outputs
    summary_df.to_csv(OUTPUT_DIR / "pv_test_summary.csv", index=False)
    state_table.to_csv(OUTPUT_DIR / "pv_state_table.csv", index=False)
    thresholds.to_csv(OUTPUT_DIR / "pv_control_parameters.csv", index=False)
    
    print(f"\nOutputs saved to {OUTPUT_DIR}")
    
    # Generate plots
    generate_plots(summary_df, state_table)
    
    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("\nPV Test Summary:")
    print(summary_df.to_string())
    
    print("\n\nPV State Table:")
    print(state_table.to_string())
    
    print("\n\nOperating Thresholds:")
    print(thresholds.to_string())


if __name__ == "__main__":
    main()
