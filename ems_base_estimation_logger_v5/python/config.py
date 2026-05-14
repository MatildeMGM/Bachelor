from zoneinfo import ZoneInfo

DK_TZ = ZoneInfo("Europe/Copenhagen")

PRICE_SOURCE = "api.energidataservice.dk"
BASE_URL = "https://api.energidataservice.dk/dataset/DayAheadPrices"

DEFAULT_PRICE_ZONE = "DK2"
VALID_PRICE_ZONES = ("DK1", "DK2")

BRIDGE_TIMEOUT = 20
PRICE_REQUEST_TIMEOUT = 15
LOOP_SLEEP_SECONDS = 1.0

DEMO_DAY_SECONDS = 24 * 60 # 24 minutes total test time
DEMO_SLOT_COUNT = 96
DEMO_SLOT_SECONDS = DEMO_DAY_SECONDS / DEMO_SLOT_COUNT
DEMO_ENABLED = True

LATITUDE = 55.686
LONGITUDE = 12.101