from app.python.forecast.pv import fetch_pv_forecast_for_today

pv = fetch_pv_forecast_for_today()
print(len(pv))   # should be 96