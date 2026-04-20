from datetime import datetime, timedelta
from utils import Constants
from solarpv import SolarPV

pv716 = SolarPV(
    name="716",
    latitude=55.686,
    longitude=12.101,
    n_panels=46,
    pdc0=395,
    gamma_pdc=-0.004,
    ratio_dc_ac=0.9085,
    eta_inv=0.96,
    surface_tilt=90,
    surface_azimuth=180,
    toLog=False,
)

df = pv716.predict(
    tStart=datetime.now(Constants.TIME_ZONE_INFO),
    tEnd=datetime.now(Constants.TIME_ZONE_INFO) + timedelta(days=1),
    tInt=60,
    isForecast=True,
    toRecord=False,
    toPrint=True,
)

print("\nResultat:")
print(df.head())