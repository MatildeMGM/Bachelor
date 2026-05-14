from __future__ import annotations

import csv
from pathlib import Path

from ems_limits import EMS_LIMITS


DEMAND_FILE = Path(__file__).resolve().parent / "scaled_may_power_profile_15min.csv"


def load_demand_profile():
    if not DEMAND_FILE.exists():
        return [EMS_LIMITS.demand.min_demand_power_mW] * 96

    values = []

    with DEMAND_FILE.open("r", newline="", encoding="utf-8-sig") as file:
        sample = file.read(2048)
        file.seek(0)

        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;")
        except csv.Error:
            dialect = csv.excel

        reader = csv.DictReader(file, dialect=dialect)

        for row in reader:
            value = None

            for key in ("power_mW", "demand_mW", "load_mW", "power"):
                if key in row:
                    value = row[key]
                    break

            if value is None and row:
                first_key = next(iter(row))
                value = row[first_key]

            try:
                values.append(float(str(value).replace(",", ".")))
            except (TypeError, ValueError):
                continue

    if not values:
        return [EMS_LIMITS.demand.min_demand_power_mW] * 96

    values = values[:96]

    while len(values) < 96:
        values.append(values[-1])

    return values