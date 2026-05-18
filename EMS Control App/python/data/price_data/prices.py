"""
File: prices.py

Description:
    This script is part of the bachelor project:
    "Investigation of reversible electrolyzers and implementation of energy
    management control strategies through IoT embedded microcontroller".

    This script fetches day-ahead electricity prices for the selected Danish
    price area and converts the returned DKK/MWh values to DKK/kWh. The EMS
    application uses the resulting 96 quarter-hour values as the price input
    for the scheduler and dashboard.

Authors:
    Jacob Norman Sorensen
    Matilde Marie Gronkjaer Matell

Institution:
    Technical University of Denmark (DTU)

Date:
    2026-05-18
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from urllib.parse import urlencode
from urllib.request import urlopen

from config import BASE_URL, DK_TZ, PRICE_REQUEST_TIMEOUT, VALID_PRICE_ZONES


def _parse_target_date(target_date=None):
    """
    Converts the requested date input to a Danish local date.
    """

    if target_date is None or str(target_date).strip() == "":
        return datetime.now(DK_TZ).date()

    if isinstance(target_date, date) and not isinstance(target_date, datetime):
        return target_date

    if isinstance(target_date, datetime):
        return target_date.astimezone(DK_TZ).date()

    return date.fromisoformat(str(target_date).strip())


def _first_present(record, keys):
    """
    Returns the first non-empty value from a list of possible API field names.
    """

    for key in keys:
        value = record.get(key)
        if value is not None:
            return value
    return None


def _expand_hourly_to_quarter_hourly(prices):
    """
    Expands 24 hourly price values to 96 quarter-hour values.
    """

    expanded = []

    for price in prices:
        expanded.extend([price] * 4)

    return expanded


def fetch_prices_for_date(zone="DK2", target_date=None):
    """
    Fetches and returns quarter-hour electricity prices for one date and price zone.
    """

    zone = str(zone).upper()

    if zone not in VALID_PRICE_ZONES:
        raise ValueError("zone must be 'DK1' or 'DK2'")

    selected_date = _parse_target_date(target_date)

    # Fetch a wider window to stay robust around UTC and DK date boundaries.
    start_date = selected_date - timedelta(days=1)
    end_date = selected_date + timedelta(days=2)

    params = {
        "start": f"{start_date}T00:00",
        "end": f"{end_date}T00:00",
        "filter": json.dumps({"PriceArea": [zone]}),
        "sort": "TimeUTC",
    }

    url = BASE_URL + "?" + urlencode(params)

    with urlopen(url, timeout=PRICE_REQUEST_TIMEOUT) as response:
        payload = json.loads(response.read().decode("utf-8"))

    records = payload.get("records", [])
    cleaned = []

    for record in records:
        if record.get("PriceArea") != zone:
            continue

        time_dk_raw = _first_present(record, ("TimeDK", "HourDK"))
        price_dkk_mwh = _first_present(
            record,
            ("DayAheadPriceDKK", "SpotPriceDKK", "PriceDKK"),
        )

        if time_dk_raw is None or price_dkk_mwh is None:
            continue

        try:
            time_dk = datetime.fromisoformat(str(time_dk_raw))
            price_dkk_kwh = float(price_dkk_mwh) / 1000.0
        except (ValueError, TypeError):
            continue

        if time_dk.date() == selected_date:
            cleaned.append((time_dk, price_dkk_kwh))

    cleaned.sort(key=lambda item: item[0])

    prices = [price for _, price in cleaned]

    if not prices:
        raise RuntimeError(
            f"No price records found for {zone} on {selected_date.isoformat()}."
        )

    if len(prices) == 24:
        prices = _expand_hourly_to_quarter_hourly(prices)

    if len(prices) != 96:
        raise RuntimeError(
            f"Expected 96 quarter-hour price values for {zone} "
            f"on {selected_date.isoformat()}, got {len(prices)}."
        )

    return prices


def fetch_prices_for_today(zone="DK2"):
    """
    Fetches the price profile for the current Danish date.
    """

    return fetch_prices_for_date(zone=zone, target_date=None)
