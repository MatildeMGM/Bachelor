import math
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
APP_DIR = BASE_DIR.parent
DATA_DIR = APP_DIR / "data"
ASSETS_DIR = DATA_DIR

CSV_PATH = DATA_DIR / "50Hertz.csv"
PROFILE_PATH = DATA_DIR / "wind_profile_5min.bin"
PROFILE_META_PATH = DATA_DIR / "wind_profile_meta.json"

# Wind scaling
WIND_SCALE_MODE = "normalize_to_rated"
WIND_TURBINE_RATED_KW = 4200.0

# Time resolution
RAW_STEP_SECONDS = 15 * 60
SIM_STEP_SECONDS = 5 * 60
SIM_STEP_HOURS = SIM_STEP_SECONDS / 3600.0

# Strategy / system from the paper
N_ELECTROLYZERS = 4
ELEC_CAPACITY_KW = 1000.0
ELEC_MIN_KW = 0.2 * ELEC_CAPACITY_KW
ELEC_STANDBY_KW = 0.05 * ELEC_CAPACITY_KW
STANDBY_TO_OFF_STEPS = 6
ROTATION_STEPS = 24 # Used in Strategy 2 for 2 hours electrolyzer switch

HOT_START_SECONDS = 200
COLD_START_SECONDS = 3600
RTH = math.ceil(HOT_START_SECONDS / SIM_STEP_SECONDS)
RTC = math.ceil(COLD_START_SECONDS / SIM_STEP_SECONDS)

# Hydrogen production support points from Table 7 in the paper
SPECIFIC_KWH_PER_KG_25 = 43.14
SPECIFIC_KWH_PER_KG_50 = 45.50
SPECIFIC_KWH_PER_KG_100 = 48.65

# Thermal parameters based on the paper table used in the earlier model
HEAT_CAPACITY_MJ_PER_C = 68.875
THERMAL_RESISTANCE_C_PER_MW = 0.005
CLIQ_MJ_PER_KG_C = 4.07e-3
CW_MJ_PER_KG_C = 4.2e-3
MLIQ_KG_PER_S = 2.0
UTH_V = 1.43
T_ENV_C = 25.0
T_CW_IN_C = 20.0
U_HE_MW_PER_M2_C = 1e-3
A_HE_M2 = 2.0
KP_COOLING = 0.1
KI_COOLING = 0.05
T_REF_C = 70.0

# Simplified electrochemistry / reporting
FARADAY = 96485.0
Z_H2 = 2.0
MH2_G_PER_MOL = 2.016
H2_LHV_KWH_PER_KG = 33.33

# Degradation counters from Table 7 support values
DELTA_U_COLD = 1e-5
DELTA_U_HOT = 1e-6

# Dashboard / runtime behavior
HISTORY_LIMIT = 720  # 60 hours at 5 min
LOOP_PROFILE = True
BRIDGE_TIMEOUT_S = 1.0
DEFAULT_STEP_INTERVAL_S = 1.0  # browser-friendly live demo pace
MIN_STEP_INTERVAL_S = 0.15
MAX_STEP_INTERVAL_S = 10.0

