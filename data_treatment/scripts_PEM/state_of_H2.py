from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Folder structure

BASE_DIR = Path(__file__).resolve().parent.parent.parent

DATA_DIR = BASE_DIR / "data"

SWEEP_DIR = DATA_DIR / "PEM_test" / "current_sweep"

POLARIZATION_FILE = SWEEP_DIR / "PEM_polarization_characteristics.csv"

print(POLARIZATION_FILE)

# Physical constants

F = 96485.3329          # Faraday constant [C/mol]

Z_H2 = 2                # Two electrons are needed per H2 molecule

ETA_EL = 1.0            # Electrolysis efficiency

ETA_FC = 1.0            # Fuel cell efficiency

CURRENT_DEADBAND_MA = 10.0

# Load csv file

df = pd.read_csv(POLARIZATION_FILE)

print("\nAvailable columns:")
print(df.columns)

# Select columns

time_col = "timestamp"

# ina4 is the current measurement channel for the fuel cell test
current_col = "ina4_current_mA"

# Convert timestamp to datetime

time = pd.to_datetime(df[time_col])

# Convert time to seconds from beginning of test

time_s = (time - time.iloc[0]).dt.total_seconds().to_numpy()

# Get current

current_mA = df[current_col].to_numpy()

current_A = current_mA / 1000

# Calculate timestep

dt = np.diff(time_s, prepend=time_s[0])

dt[0] = 0

# Detect operating mode

mode = np.full(len(current_A), "idle", dtype=object)

mode[current_mA > CURRENT_DEADBAND_MA] = "electrolysis"

mode[current_mA < -CURRENT_DEADBAND_MA] = "fuel cell"

# Faraday based hydrogen calculation
#
# Electrolysis:
# Hydrogen storage increases
#
# Fuel cell:
# Hydrogen storage decreases

dn_produced = np.zeros(len(current_A))

dn_consumed = np.zeros(len(current_A))

el_mask = mode == "electrolysis"

fc_mask = mode == "fuel cell"

dn_produced[el_mask] = (
    ETA_EL
    * current_A[el_mask]
    * dt[el_mask]
    / (Z_H2 * F)
)

dn_consumed[fc_mask] = (
    abs(current_A[fc_mask])
    * dt[fc_mask]
    / (Z_H2 * F * ETA_FC)
)

# Integrate hydrogen amount

n_produced = np.cumsum(dn_produced)

n_consumed = np.cumsum(dn_consumed)

# Estimate usable hydrogen capacity
#
# Full electrolysis cycle defines maximum capacity

n_H2_max = n_produced.max()

if n_H2_max <= 0:
    raise ValueError(
        "No electrolysis charging period detected. "
        "Check current sign and INA channel."
    )

# Calculate hydrogen state

soc_electrolysis = 100 * n_produced / n_H2_max

soc_fuel_cell = 100 * (1 - n_consumed / n_H2_max)

# Limit values between 0 and 100 %

soc_electrolysis = np.clip(soc_electrolysis, 0, 100)

soc_fuel_cell = np.clip(soc_fuel_cell, 0, 100)

# Only plot relevant regions

soc_electrolysis_plot = np.where(
    el_mask,
    soc_electrolysis,
    np.nan
)

soc_fuel_cell_plot = np.where(
    fc_mask,
    soc_fuel_cell,
    np.nan
)

# Summary values

total_charge_C = np.sum(
    current_A[el_mask] * dt[el_mask]
)

total_discharge_C = np.sum(
    abs(current_A[fc_mask]) * dt[fc_mask]
)

total_H2_produced_mol = np.sum(dn_produced)

total_H2_consumed_mol = np.sum(dn_consumed)

print("\nSummary")

print(
    f"Total charge during electrolysis: "
    f"{total_charge_C:.2f} C"
)

print(
    f"Total charge during fuel cell mode: "
    f"{total_discharge_C:.2f} C"
)

print(
    f"Estimated hydrogen produced: "
    f"{total_H2_produced_mol:.6e} mol"
)

print(
    f"Estimated hydrogen consumed: "
    f"{total_H2_consumed_mol:.6e} mol"
)

print(
    f"Estimated usable hydrogen capacity: "
    f"{n_H2_max:.6e} mol"
)

# Plot hydrogen state

plt.figure(figsize=(10, 5))

plt.plot(
    time_s,
    soc_electrolysis_plot,
    label="Electrolysis mode"
)

plt.plot(
    time_s,
    soc_fuel_cell_plot,
    label="Fuel cell mode"
)

plt.xlabel("Time [s]")

plt.ylabel("Hydrogen state [%]")

plt.title("Estimated hydrogen state from current integration")

plt.ylim(-5, 105)

plt.grid(True)

plt.legend()

plt.tight_layout()

plt.show()