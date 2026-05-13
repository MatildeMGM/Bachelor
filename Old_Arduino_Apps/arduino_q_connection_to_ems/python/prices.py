from datetime import datetime
import requests


def fetch_prices_for_today(zone="DK2"):
    today = datetime.now()
    url = f"https://www.elprisenligenu.dk/api/v1/prices/{today:%Y}/{today:%m-%d}_{zone}.json"

    response = requests.get(url, timeout=15)
    response.raise_for_status()

    data = response.json()

    return [float(item["DKK_per_kWh"]) for item in data]