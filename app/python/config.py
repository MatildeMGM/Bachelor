# This file contains shared settings and constants used across the Python app.

from zoneinfo import ZoneInfo

DK_TZ = ZoneInfo("Europe/Copenhagen")

PRICE_SOURCE = "api.energidataservice.dk"
BASE_URL = "https://api.energidataservice.dk/dataset/DayAheadPrices"

DEFAULT_PRICE_ZONE = "DK2"
VALID_PRICE_ZONES = ("DK1", "DK2")

BRIDGE_TIMEOUT = 20
PRICE_REQUEST_TIMEOUT = 15
LOOP_SLEEP_SECONDS = 2

# Demonstration mode: one 24 hour EMS day is simulated in 12 real minutes.
DEMO_DAY_SECONDS = 12 * 60
DEMO_SLOT_SECONDS = DEMO_DAY_SECONDS / 96
DEMO_ENABLED = True

LATITUDE = 55.686
LONGITUDE = 12.101
