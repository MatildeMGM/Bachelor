from datetime import datetime, timedelta
import requests


def fetch_prices_for_today(zone="DK2"):
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)

    url = "https://api.energidataservice.dk/dataset/DayAheadPrices"

    params = {
        "start": "{}T00:00".format(today),
        "end": "{}T00:00".format(tomorrow),
        "filter": '{{"PriceArea":["{}"]}}'.format(zone),
        "sort": "TimeUTC"
    }

    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()

    data = response.json()
    records = data.get("records", [])

    # Returnér i samme enhed som før: DKK/kWh
    prices = [float(record["DayAheadPriceDKK"]) / 1000.0 for record in records]

    return prices