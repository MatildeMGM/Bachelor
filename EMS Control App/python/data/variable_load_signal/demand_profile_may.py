"""
File: demand_profile_may.py

Description:
    This script is part of the bachelor project:
    "Investigation of reversible electrolyzers and implementation of energy
    management control strategies through IoT embedded microcontroller".

    This script loads the 15-minute demand profile used by the EMS control
    application. The profile is stored as a scaled CSV file and is converted
    to the configured EMS demand limits before it is used by the scheduler.

Authors:
    Jacob Norman Sorensen
    Matilde Marie Gronkjaer Matell

Institution:
    Technical University of Denmark (DTU)

Date:
    2026-05-18
"""

from __future__ import annotations

import csv
from pathlib import Path
import sys

# Allows this data module to import the shared EMS limits when run directly.
PYTHON_DIR = Path(__file__).resolve().parents[2]
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from ems_limits import EMS_LIMITS


DEMAND_FILE = Path(__file__).resolve().parent / "scaled_may_power_profile_15min.csv"


CSV_FIELDS = ["time_slot", "time_of_day", "power_mW"]


def scale_values(values, new_min, new_max):
    """
    Scales a list of numeric values linearly to a new minimum and maximum range.
    """

    old_min = min(values)
    old_max = max(values)

    if old_max == old_min:
        raise RuntimeError(
            "Cannot scale demand profile because all power_mW values are identical. "
            "Restore the original CSV first."
        )

    return [
        new_min + (value - old_min) * (new_max - new_min) / (old_max - old_min)
        for value in values
    ]


def read_demand_rows():
    """
    Reads the scaled demand CSV file and returns each row as a dictionary.
    """

    if not DEMAND_FILE.exists():
        return []

    rows = []

    with DEMAND_FILE.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        for row in reader:
            rows.append(row)

    return rows


def load_demand_profile():
    """
    Loads the 96-step demand profile used by the EMS scheduler.

    Invalid values are skipped, short profiles are extended with the last
    available value, and the final profile is scaled to the demand limits
    defined in ems_limits.py.
    """

    rows = read_demand_rows()

    if not rows:
        return [EMS_LIMITS.demand.min_demand_power_mW] * 96

    values = []

    for row in rows:
        try:
            values.append(float(str(row["power_mW"]).replace(",", ".")))
        except (KeyError, TypeError, ValueError):
            continue

    if not values:
        return [EMS_LIMITS.demand.min_demand_power_mW] * 96

    values = values[:96]

    while len(values) < 96:
        values.append(values[-1])

    values = scale_values(
        values,
        EMS_LIMITS.demand.min_demand_power_mW,
        EMS_LIMITS.demand.max_demand_power_mW,
    )

    return values


def write_scaled_demand_profile():
    """
    Rewrites the demand CSV file after scaling the current values to EMS limits.

    This helper is used when the file is executed directly, for example after
    updating the demand CSV values.
    """

    rows = read_demand_rows()

    if not rows:
        raise RuntimeError("No rows found in demand CSV.")

    values = []

    for row in rows:
        values.append(float(str(row["power_mW"]).replace(",", ".")))

    scaled_values = scale_values(
        values,
        EMS_LIMITS.demand.min_demand_power_mW,
        EMS_LIMITS.demand.max_demand_power_mW,
    )

    for row, scaled_value in zip(rows, scaled_values):
        row["power_mW"] = round(scaled_value, 6)

    with DEMAND_FILE.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
        writer.writeheader()

        for row in rows:
            writer.writerow(
                {
                    "time_slot": row["time_slot"],
                    "time_of_day": row["time_of_day"],
                    "power_mW": row["power_mW"],
                }
            )

    print(f"Wrote {len(rows)} rows to {DEMAND_FILE}")
    print(f"min = {min(scaled_values):.3f} mW")
    print(f"max = {max(scaled_values):.3f} mW")


if __name__ == "__main__":
    write_scaled_demand_profile()
