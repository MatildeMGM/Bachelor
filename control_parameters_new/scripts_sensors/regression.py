import numpy as np

# Sensor 45 current data
ref = np.array([0.000, 14.910, 29.220, 43.300, 55.300])
ina = np.array([-0.024, 17.600, 34.721, 51.598, 65.377])

# Error
error = ina - ref

# Linear regression: y = a*x + b
a, b = np.polyfit(ref, error, 1)

# Predicted error from regression line
error_fit = a * ref + b

# R^2
ss_res = np.sum((error - error_fit)**2)
ss_tot = np.sum((error - np.mean(error))**2)
r2 = 1 - ss_res / ss_tot

print(f"Slope: {a:.4f}")
print(f"Intercept: {b:.4f}")
print(f"R^2: {r2:.4f}")

import matplotlib.pyplot as plt

plt.figure(figsize=(7,5))
plt.plot(ref, error, "o", label="Measured error")
plt.plot(ref, error_fit, "-", label=f"Linear fit, $R^2$ = {r2:.4f}")
plt.xlabel("Reference current [mA]")
plt.ylabel("Error [mA]")
plt.title("Sensor 45: error versus current")
plt.legend()
plt.grid(True)
plt.show()