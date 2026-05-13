# This file fetches hourly weather forecast data for today
# using the Open Meteo API and returns only the variables
# needed for PV estimation.

from datetime import datetime, timedelta

import requests

from Bachelor.Old_Arduino_Apps.app.python.config import DK_TZ, LATITUDE, LONGITUDE

REQUEST_TIMEOUT = 10


def fetch_weather_forecast_for_today():
    now_dk = datetime.now(DK_TZ)
    today_dk = now_dk.date()
    tomorrow_dk = today_dk + timedelta(days=1)

    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": "shortwave_radiation,temperature_2m",
        "timezone": "Europe/Copenhagen",
        "start_date": today_dk.isoformat(),
        "end_date": tomorrow_dk.isoformat(),
    }

    response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params=params,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()

    data = response.json()

    hourly = data.get("hourly", {})

    times = hourly.get("time", [])
    radiation = hourly.get("shortwave_radiation", [])
    temperature = hourly.get("temperature_2m", [])

    if not times or not radiation:
        raise RuntimeError("Weather forecast data is incomplete.")

    rows = []

    for t, rad, temp in zip(times, radiation, temperature):
        try:
            time_dk = datetime.fromisoformat(t)
        except ValueError:
            continue

        if time_dk.date() != today_dk:
            continue

        try:
            rad = float(rad)
            temp = float(temp)
        except (TypeError, ValueError):
            continue

        rows.append((time_dk, rad, temp))

    rows.sort(key=lambda x: x[0])

    if not rows:
        raise RuntimeError("No valid weather forecast data for today.")

    return rows

if __name__ == "__main__":
    rows = fetch_weather_forecast_for_today()
    print("Rows:", len(rows))
    print("First 2:", rows[:2])