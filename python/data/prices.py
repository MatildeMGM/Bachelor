# This file contains the function that fetches and cleans day ahead price data.

from datetime import datetime, timedelta

import requests

from config import BASE_URL, DK_TZ, PRICE_REQUEST_TIMEOUT, VALID_PRICE_ZONES


def fetch_prices_for_today(zone="DK2"):
    zone = str(zone).upper()
    if zone not in VALID_PRICE_ZONES:
        raise ValueError("zone must be 'DK1' or 'DK2'")

    now_dk = datetime.now(DK_TZ)
    today_dk = now_dk.date()
    tomorrow_dk = today_dk + timedelta(days=1)

    # Fetch a wider window to stay robust around UTC and DK date boundaries
    start_date = today_dk - timedelta(days=1)
    end_date = tomorrow_dk + timedelta(days=1)

    params = {
        "start": "{}T00:00".format(start_date),
        "end": "{}T00:00".format(end_date),
        "filter": '{{"PriceArea":["{}"]}}'.format(zone),
        "sort": "TimeUTC",
    }

    response = requests.get(BASE_URL, params=params, timeout=PRICE_REQUEST_TIMEOUT)
    response.raise_for_status()

    payload = response.json()
    records = payload.get("records", [])

    cleaned = []

    for record in records:
        if record.get("PriceArea") != zone:
            continue

        time_dk_raw = record.get("TimeDK")
        price_dkk_mwh = record.get("DayAheadPriceDKK")

        if time_dk_raw is None or price_dkk_mwh is None:
            continue

        try:
            time_dk = datetime.fromisoformat(time_dk_raw)
            price_dkk_kwh = float(price_dkk_mwh) / 1000.0
        except (ValueError, TypeError):
            continue

        if time_dk.date() == today_dk:
            cleaned.append((time_dk, price_dkk_kwh))

    cleaned.sort(key=lambda x: x[0])

    prices = [price for _, price in cleaned]

    if not prices:
        raise RuntimeError(
            "No price records found for {} on {}.".format(zone, today_dk.isoformat())
        )

    return prices