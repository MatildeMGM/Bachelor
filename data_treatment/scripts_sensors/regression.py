from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np


def find_bachelor_dir():
    script_dir = Path(__file__).resolve().parent

    for parent in [script_dir] + list(script_dir.parents):
        if (parent / "data").exists() and (parent / "data_treatment").exists():
            return parent

    raise FileNotFoundError("Could not find bachelor folder")


BACHELOR_DIR = find_bachelor_dir()
PLOT_DIR = BACHELOR_DIR / "data_treatment" / "plots" / "sensor_plots"
PLOT_DIR.mkdir(parents=True, exist_ok=True)

sys.path.append(str(BACHELOR_DIR / "data_treatment"))

from plot_style import GREY, LIGHT_BLUE, polish_axes, save_report_figure, set_report_style


ref = np.array([0.000, 14.910, 29.220, 43.300, 55.300])
ina = np.array([-0.024, 17.600, 34.721, 51.598, 65.377])

error = ina - ref
a, b = np.polyfit(ref, error, 1)
error_fit = a * ref + b

ss_res = np.sum((error - error_fit) ** 2)
ss_tot = np.sum((error - np.mean(error)) ** 2)
r2 = 1 - ss_res / ss_tot

print(f"Slope: {a:.4f}")
print(f"Intercept: {b:.4f}")
print(f"R^2: {r2:.4f}")

set_report_style()
fig, ax = plt.subplots()

ax.plot(ref, error, "o", color=GREY, label="Measured error")
ax.plot(ref, error_fit, "-", color=LIGHT_BLUE, label=rf"Linear fit, $R^2$ = {r2:.4f}")
ax.set_xlabel("Reference current [mA]")
ax.set_ylabel("Current error [mA]")
ax.set_title("Sensor 45 Current Error Regression")
polish_axes(ax)
ax.legend()

save_report_figure(fig, PLOT_DIR / "sensor_45_current_regression.png")
