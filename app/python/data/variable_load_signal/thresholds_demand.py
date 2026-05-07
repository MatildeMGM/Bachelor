from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent

CSV_PATH = Path(__file__).parent / "scaled_may_power_profile_15min.csv"
DEMAND_COLUMN = "power_mW"


def load_demand(csv_path, demand_column):
    data = pd.read_csv(csv_path)

    if demand_column not in data.columns:
        raise ValueError(
            f"Column '{demand_column}' was not found. "
            f"Available columns are: {list(data.columns)}"
        )

    demand_w = (
        data[demand_column]
        .astype(str)
        .str.replace(",", ".", regex=False)
        .astype(float)
    )

    return demand_w


demand_w = load_demand(CSV_PATH, DEMAND_COLUMN)

demand_min = demand_w.min()
demand_max = demand_w.max()

low_threshold = demand_w.quantile(0.25)
high_threshold = demand_w.quantile(0.75)

thresholds = {
    "low": {
        "min_W": demand_min,
        "max_W": low_threshold,
    },
    "medium": {
        "min_W": low_threshold,
        "max_W": high_threshold,
    },
    "high": {
        "min_W": high_threshold,
        "max_W": demand_max,
    },
}

print("Demand analysis based on the load profile")
print(f"Minimum demand: {demand_min:.2f} mW")
print(f"Minimun demand: "<" {demand_max:.2f} mW")
print()
print("Demand thresholds")
print(f"Low demand:    {demand_min:.2f} to {low_threshold:.2f} mW")
print(f"Medium demand: {low_threshold:.2f} to {high_threshold:.2f} mW")
print(f"High demand:   {high_threshold:.2f} to {demand_max:.2f} mW")

print()
print("Threshold dictionary")
print(thresholds)

# Demand thresholds
# Low demand:    <43.31 mW
# Medium demand: 43.31 to 66.01 mW
# High demand:   66.01< mW

