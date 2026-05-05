# This file creates a typical May load profile with 96 values.
# The output matches 15 minute electricity price data.

from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt


SCRIPT_DIR = Path(__file__).parent

INPUT_FILES = [
    SCRIPT_DIR / "maj2024.csv",
    SCRIPT_DIR / "maj2025.csv",
]

OUTPUT_FILE = SCRIPT_DIR / "typical_may_load_profile_15min.csv"

# threshholds for scaling the load profile to a realistic range for the EMS
MIN_POWER_MW = 20
MAX_POWER_MW = 150

SCALED_OUTPUT_FILE = SCRIPT_DIR / "scaled_may_power_profile_15min.csv"
SCALED_PLOT_FILE = SCRIPT_DIR / "scaled_may_power_profile_15min.png"

TIME_COLUMN = "TimeDK"
LOAD_COLUMN = "ConsumptionkWh"


def read_load_file(file_name):
    file_path = Path(file_name)

    if not file_path.exists():
        raise FileNotFoundError(f"Could not find {file_name}")

    data = pd.read_csv(
        file_path,
        sep=";",
        decimal=","
    )

    data[TIME_COLUMN] = pd.to_datetime(data[TIME_COLUMN])
    data[LOAD_COLUMN] = pd.to_numeric(data[LOAD_COLUMN], errors="coerce")

    data = data[[TIME_COLUMN, LOAD_COLUMN]].dropna()

    return data


def create_hourly_typical_profile(data):
    data = data.copy()
    data["hour"] = data[TIME_COLUMN].dt.hour

    hourly_profile = (
        data
        .groupby("hour")[LOAD_COLUMN]
        .mean()
        .sort_index()
    )

    if len(hourly_profile) != 24:
        raise RuntimeError(
            f"Expected 24 hourly load values, got {len(hourly_profile)}"
        )

    return hourly_profile


def interpolate_to_15min(hourly_profile):
    hourly_time_index = pd.date_range(
        "2024-01-01 00:00",
        periods=24,
        freq="h"
    )

    hourly_data = pd.DataFrame(
        {
            "load_kWh_per_hour": hourly_profile.values
        },
        index=hourly_time_index
    )

    next_midnight = pd.Timestamp("2024-01-02 00:00")
    hourly_data.loc[next_midnight] = hourly_data.iloc[0]

    load_15min = (
        hourly_data
        .resample("15min")
        .interpolate(method="linear")
        .iloc[:-1]
    )

    load_15min["load_kWh_per_15min"] = (
        load_15min["load_kWh_per_hour"] / 4
    )

    load_15min = load_15min.reset_index()
    load_15min = load_15min.rename(columns={"index": "time"})

    load_15min["time_slot"] = range(1, len(load_15min) + 1)
    load_15min["time_of_day"] = load_15min["time"].dt.strftime("%H:%M")

    return load_15min[
        [
            "time_slot",
            "time_of_day",
            "load_kWh_per_15min",
        ]
    ]



def create_typical_may_load_profile():
    all_data = []

    for file_name in INPUT_FILES:
        data = read_load_file(file_name)
        all_data.append(data)

    combined_data = pd.concat(all_data, ignore_index=True)

    hourly_profile = create_hourly_typical_profile(combined_data)
    load_profile_15min = interpolate_to_15min(hourly_profile)

    if len(load_profile_15min) != 96:
        raise RuntimeError(
            f"Expected 96 load values, got {len(load_profile_15min)}"
        )

    load_profile_15min.to_csv(OUTPUT_FILE, index=False)

    return load_profile_15min


def get_load_values_for_ems():
    load_profile = create_typical_may_load_profile()

    return load_profile["load_kWh_per_15min"].tolist()


def plot_load_profile(load_profile):
    plot_file = SCRIPT_DIR / "typical_may_load_profile_15min.png"

    plt.figure(figsize=(10, 5))
    plt.plot(
        load_profile["time_of_day"],
        load_profile["load_kWh_per_15min"]
    )

    plt.xticks(load_profile["time_of_day"][::8], rotation=45)
    plt.xlabel("Time of day")
    plt.ylabel("Load energy per 15 min [kWh]")
    plt.title("Typical May load profile")
    plt.tight_layout()
    plt.savefig(plot_file, dpi=300)
    plt.show()

    print(f"Saved plot to {plot_file}")


def scale_load_to_power(load_profile):
    scaled = load_profile.copy()

    load_min = scaled["load_kWh_per_15min"].min()
    load_max = scaled["load_kWh_per_15min"].max()

    if load_max == load_min:
        raise RuntimeError("Cannot scale profile with constant values")

    scaled["power_mW"] = (
        MIN_POWER_MW
        + (
            (scaled["load_kWh_per_15min"] - load_min)
            / (load_max - load_min)
        )
        * (MAX_POWER_MW - MIN_POWER_MW)
    )

    return scaled[
        [
            "time_slot",
            "time_of_day",
            "power_mW",
        ]
    ]


def plot_scaled_power_profile(scaled_profile):
    plt.figure(figsize=(10, 5))
    plt.plot(
        scaled_profile["time_of_day"],
        scaled_profile["power_mW"]
    )

    plt.xticks(scaled_profile["time_of_day"][::8], rotation=45)
    plt.xlabel("Time of day")
    plt.ylabel("Power [mW]")
    plt.title(f"Scaled May demand profile ({MIN_POWER_MW}-{MAX_POWER_MW} mW)")
    plt.tight_layout()
    plt.savefig(SCALED_PLOT_FILE, dpi=300)
    plt.show()

    print(f"Saved scaled plot to {SCALED_PLOT_FILE}")
    


def main():
    load_profile = create_typical_may_load_profile()
    scaled_profile = scale_load_to_power(load_profile)

    scaled_profile.to_csv(SCALED_OUTPUT_FILE, index=False)

    plot_load_profile(load_profile)
    plot_scaled_power_profile(scaled_profile)

    print(load_profile.head())
    print()
    print(scaled_profile.head())
    print()
    print(f"Saved load profile to {OUTPUT_FILE}")
    print(f"Saved scaled profile to {SCALED_OUTPUT_FILE}")
    print(f"Number of values: {len(scaled_profile)}")

if __name__ == "__main__":
    main()

