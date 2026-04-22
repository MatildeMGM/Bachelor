from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

# Paths
BASE_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = BASE_DIR / "data" / "PEM_tests"
PLOT_DIR = BASE_DIR / "data_treatment" / "hardware_tests" / "plots"
PLOT_DIR.mkdir(parents=True, exist_ok=True)

# Hvis du vil bruge den sammenslåede fil:
# df1 = pd.read_csv(DATA_DIR / "PEM_ina226_log_20260422_142001.csv")
# df2 = pd.read_csv(DATA_DIR / "PEM_ina226_log_20260422_145623.csv")
# df_combined = pd.concat([df1, df2], ignore_index=True)
# df_combined.to_csv(DATA_DIR / "PEM_charging.csv", index=False)
# file_path = DATA_DIR / "PEM_charging.csv"

# Brug denne fil til analyse
file_path = DATA_DIR / "PEM_ina226_log_20260422_161423.csv"

# Load data
df = pd.read_csv(file_path)

# Convert relevant columns to numeric
numeric_cols = ["bus_V", "current_mA", "power_mW", "shunt_mV", "elapsed_s"]
for col in numeric_cols:
    df[col] = pd.to_numeric(df[col], errors="coerce")

# Remove NaNs in critical columns
df = df.dropna(subset=["bus_V", "current_mA"])

# Remove non-operating / noisy region
df = df[df["current_mA"] > 0]
df = df[df["bus_V"] > 0.9]

# Sort by voltage
df = df.sort_values("bus_V")

# Average repeated voltage points
df = df.groupby("bus_V", as_index=False)[["current_mA", "shunt_mV"]].mean()

# Recalculate power from V * I
# V * mA = mW, so units are already correct
df["power_mW"] = df["bus_V"] * df["current_mA"]

# I–V plot 
plt.figure()
plt.plot(df["current_mA"], df["bus_V"], marker="o")
plt.xlabel("Current [mA]")
plt.ylabel("Voltage [V]")
plt.title("I–V Curve (PEM Electrolyzer)")
plt.grid(True)
plt.tight_layout()
plt.savefig(PLOT_DIR / "IV_curve_PEM_EL_mode.png", dpi=300)
plt.close()

# P–V plot
plt.figure()
plt.plot(df["bus_V"], df["power_mW"], marker="o")
plt.xlabel("Voltage [V]")
plt.ylabel("Power [mW]")
plt.title("P–V Curve (PEM Electrolyzer)")
plt.grid(True)
plt.tight_layout()
plt.savefig(PLOT_DIR / "PV_curve_PEM_EL_mode.png", dpi=300)
plt.close()