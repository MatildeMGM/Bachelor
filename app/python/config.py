# This file contains shared settings and constants used across the Python app.

from zoneinfo import ZoneInfo

DK_TZ = ZoneInfo("Europe/Copenhagen")

PRICE_SOURCE = "api.energidataservice.dk"
BASE_URL = "https://api.energidataservice.dk/dataset/DayAheadPrices"

DEFAULT_PRICE_ZONE = "DK2"
VALID_PRICE_ZONES = ("DK1", "DK2")

BRIDGE_TIMEOUT = 5
PRICE_REQUEST_TIMEOUT = 15
LOOP_SLEEP_SECONDS = 2


LATITUDE = 55.686
LONGITUDE = 12.101