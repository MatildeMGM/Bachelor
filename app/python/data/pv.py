import numpy as np
import pandas as pd
import pvlib


RATED_POWER_W = 1.0
GAMMA_PDC = -0.004

SURFACE_TILT = 45
SURFACE_AZIMUTH = 180

LATITUDE = 55.686
LONGITUDE = 12.101
TIMEZONE = "Europe/Copenhagen"


def pv_forecast_from_weather(weather_rows):
    """
    Estimate lab scale PV power from weather forecast data.
    Returns hourly PV power values in W.

    Args:
            name (str): name.
            latitude (float): latitude [degree].
            longitude (float): longitude [degree].
            pdc0 (float): DC power at refence conditions (1000 W/m^2 and 25 C) [W].
            gamma_pdc (float): temperature coefficient of power [1/C].
            surface_tilt (float): surface tilt from horizontal [degree].
            surface_azimuth (float): surface azimuth from north [degree].
    """

    times = [row[0] for row in weather_rows]
    ghi = [row[1] for row in weather_rows]
    temp_air = [row[2] for row in weather_rows]

    index = pd.DatetimeIndex(times)

    if index.tz is None:
        index = index.tz_localize(TIMEZONE)

    weather = pd.DataFrame(
        {
            "ghi": ghi,
            "temp_air": temp_air,
        },
        index=index,
    )

    location = pvlib.location.Location(
        latitude=LATITUDE,
        longitude=LONGITUDE,
        tz=TIMEZONE,
    )

    solar_position = location.get_solarposition(weather.index)

    erbs = pvlib.irradiance.erbs(
        ghi=weather["ghi"],
        zenith=solar_position["zenith"],
        datetime_or_doy=weather.index,
    )

    dni = erbs["dni"]
    dhi = erbs["dhi"]

    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=SURFACE_TILT,
        surface_azimuth=SURFACE_AZIMUTH,
        solar_zenith=solar_position["zenith"],
        solar_azimuth=solar_position["azimuth"],
        dni=dni,
        ghi=weather["ghi"],
        dhi=dhi,
    )

    cell_temperature = pvlib.temperature.sapm_cell(
        poa_global=poa["poa_global"],
        temp_air=weather["temp_air"],
        wind_speed=1.0,
        **pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS["sapm"]["open_rack_glass_glass"],
    )

    power_dc = pvlib.pvsystem.pvwatts_dc(
        effective_irradiance=poa["poa_global"],
        temp_cell=cell_temperature,
        pdc0=RATED_POWER_W,
        gamma_pdc=GAMMA_PDC,
    )

    power_dc = power_dc.clip(lower=0.0, upper=RATED_POWER_W)

    return power_dc.to_numpy()


def pv_15_min_resolution(hourly_values):
    quarter_hour_values = []

    for i in range(len(hourly_values)):
        start = hourly_values[i]

        if i < len(hourly_values) - 1:
            end = hourly_values[i + 1]
        else:
            end = start

        quarter_hour_values.append(start)
        quarter_hour_values.append(start + 0.25 * (end - start))
        quarter_hour_values.append(start + 0.50 * (end - start))
        quarter_hour_values.append(start + 0.75 * (end - start))

    return np.array(quarter_hour_values)


def scale_pv_forecast_for_scheduler(pv_values):
    scaled = []

    for pv_w in pv_values:
        pv_index = pv_w / RATED_POWER_W
        pv_index = max(0.0, min(pv_index, 1.0))

        if pv_index < 0.15:
            pv_level = "low"
        elif pv_index < 0.60:
            pv_level = "medium"
        else:
            pv_level = "high"

        scaled.append({
            "pv_w": float(pv_w),
            "pv_index": float(pv_index),
            "pv_level": pv_level,
        })

    return scaled


def pv_forecast_96_slots(weather_rows):
    hourly_pv = pv_forecast_from_weather(weather_rows)

    pv_96 = pv_15_min_resolution(hourly_pv)

    if len(pv_96) != 96:
        raise RuntimeError(f"Expected 96 PV values, got {len(pv_96)}")

    return pv_96

