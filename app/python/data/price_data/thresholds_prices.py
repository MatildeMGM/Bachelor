from pathlib import Path

import pandas as pd

from pathlib import Path

CSV_PATH = Path(__file__).parent / "Elspotprices.csv"

data = pd.read_csv(CSV_PATH, sep=";")

PRICE_COLUMN = "SpotPriceDKK"


def load_spot_prices(csv_path, price_column):
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
price_range = price_max - price_min

low_threshold = prices_dkk_kwh.quantile(0.25)
high_threshold = prices_dkk_kwh.quantile(0.75)


thresholds = {
    "low": {
        "min": price_min,
        "max": low_threshold,
    },
    "medium": {
        "min": low_threshold,
        "max": high_threshold,
    },
    "high": {
        "min": high_threshold,
        "max": price_max,
    },
}

print("Spot price analysis based on one year of data")
print(f"Minimum price: {price_min:.4f} DKK/kWh")
print(f"Maximum price: {price_max:.4f} DKK/kWh")
print()
print("Electricity price thresholds")
print(f"Low price:    {price_min:.4f} to {low_threshold:.4f} DKK/kWh")
print(f"Medium price: {low_threshold:.4f} to {high_threshold:.4f} DKK/kWh")
print(f"High price:   {high_threshold:.4f} to {price_max:.4f} DKK/kWh")

thresholds
# Electricity price thresholds
# Low price:    <0.2857 DKK/kWh
# Medium price: 0.2857 to 0.8308 DKK/kWh
# High price:   0.8308< DKK/kWh

