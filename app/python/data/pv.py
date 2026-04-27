from app.python.data.weather import fetch_weather_forecast_for_today


RATED_POWER_W = 1.0

# Replace this placeholder value once the laboratory correction factor
# has been determined from measurements of the PV panel under the
# relevant test conditions.
PV_CORRECTION_FACTOR = 1.0


def interpolate_hourly_to_quarter_hour(hourly_values):
    if len(hourly_values) < 2:
        raise ValueError("Not enough PV values for interpolation.")

    quarter_hour_values = []
    n = len(hourly_values)

    for i in range(n):
        start_value = hourly_values[i]

        if i < n - 1:
            end_value = hourly_values[i + 1]
        else:
            end_value = start_value

        quarter_hour_values.append(start_value)
        quarter_hour_values.append(start_value + (end_value - start_value) * 0.25)
        quarter_hour_values.append(start_value + (end_value - start_value) * 0.50)
        quarter_hour_values.append(start_value + (end_value - start_value) * 0.75)

    return quarter_hour_values




def fetch_pv_forecast_for_today():
    weather_rows = fetch_weather_forecast_for_today()

    hourly_pv_values = []

    for _, shortwave_radiation, _ in weather_rows:
        pv_dc_w = (shortwave_radiation / 1000.0) * RATED_POWER_W
        pv_ac_w = pv_dc_w * PV_CORRECTION_FACTOR
        pv_ac_w = max(0.0, min(pv_ac_w, RATED_POWER_W))

        hourly_pv_values.append(pv_ac_w)

    if not hourly_pv_values:
        raise RuntimeError("No PV forecast values found for today.")

    quarter_hour_pv_values = interpolate_hourly_to_quarter_hour(hourly_pv_values)

    if len(quarter_hour_pv_values) != 96:
        raise RuntimeError(
            f"Expected 96 quarter-hour PV values, got {len(quarter_hour_pv_values)}"
        )

    return quarter_hour_pv_values




if __name__ == "__main__":
    pv = fetch_pv_forecast_for_today()
    print("Length:", len(pv))
    print("First 8:", pv[:8])
    print("Middle 8:", pv[40:48])
    print("Last 8:", pv[-8:])