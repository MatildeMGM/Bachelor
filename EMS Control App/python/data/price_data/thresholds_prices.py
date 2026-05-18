"""
File: thresholds_prices.py

Description:
    This script is part of the bachelor project:
    "Investigation of reversible electrolyzers and implementation of energy
    management control strategies through IoT embedded microcontroller".

    This script analyses historical spot price data and calculates the price
    threshold used to classify EMS operation into low-price and high-price
    periods. The resulting threshold supports the scheduler configuration in
    the EMS application.

Authors:
    Jacob Norman Sorensen
    Matilde Marie Gronkjaer Matell

Institution:
    Technical University of Denmark (DTU)

Date:
    2026-05-18
"""

from pathlib import Path

import pandas as pd

CSV_PATH = Path(__file__).parent / "Elspotprices.csv"

data = pd.read_csv(CSV_PATH, sep=";")

PRICE_COLUMN = "SpotPriceDKK"


def load_spot_prices(csv_path, price_column):
    """
    Loads spot prices from the historical CSV file and converts DKK/MWh to DKK/kWh.
    """

    data = pd.read_csv(csv_path, sep=";")

    if price_column not in data.columns:
        raise ValueError(
            f"Column '{price_column}' was not found. "
            f"Available columns are: {list(data.columns)}"
        )

    prices_dkk_mwh = (
        data[price_column]
        .astype(str)
        .str.replace(",", ".", regex=False)
        .astype(float)
    )

    prices_dkk_kwh = prices_dkk_mwh / 1000

    return prices_dkk_kwh


prices_dkk_kwh = load_spot_prices(CSV_PATH, PRICE_COLUMN)

price_min = prices_dkk_kwh.min()
price_max = prices_dkk_kwh.max()
price_threshold = prices_dkk_kwh.quantile(0.50)


thresholds = {
    "low": {
        "min": price_min,
        "max": price_threshold,
    },
    "high": {
        "min": price_threshold,
        "max": price_max,
    },
}

print("Spot price analysis based on one year of data")
print(f"Minimum price: {price_min:.4f} DKK/kWh")
print(f"Maximum price: {price_max:.4f} DKK/kWh")
print()
print("Electricity price thresholds")
print(f"Single threshold: {price_threshold:.4f} DKK/kWh")
print(f"Low price mode:   below {price_threshold:.4f} DKK/kWh")
print(f"High price mode:  {price_threshold:.4f} DKK/kWh and above")

thresholds
# Electricity price thresholds
# Low price mode:   < PRICE_LIMITS.high_price_min_DKK_per_kWh
# High price mode:  >= PRICE_LIMITS.high_price_min_DKK_per_kWh

