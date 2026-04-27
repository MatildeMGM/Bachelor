from app.python.data.weather import fetch_weather_forecast_for_today
from app.python.data.pv import estimate_pv_forecast_96_slots, scale_pv_for_ems

print("Starting PV test...")

weather_rows = fetch_weather_forecast_for_today()

print("Weather rows:", len(weather_rows))
print("First weather row:", weather_rows[0])

pv_96 = estimate_pv_forecast_96_slots(weather_rows)

print("PV slots:", len(pv_96))
print("First 10 PV values:", pv_96[:10])
print("Max PV value:", max(pv_96))

pv_scaled = scale_pv_for_ems(pv_96)

print("First 5 scaled values:")
for row in pv_scaled[:5]:
    print(row)

print("\nFull 96 PV slots:\n")

for i, v in enumerate(pv_96):
    print(f"Slot {i:02d}: {v:.3f}")

print("PV test finished.")