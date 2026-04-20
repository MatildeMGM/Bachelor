import numpy as np
import matplotlib.pyplot as plt

# Style (same as before)
plt.style.use("seaborn-v0_8-whitegrid")

plt.rcParams.update({
    "font.size": 14,
    "axes.titlesize": 16,
    "axes.labelsize": 14,
    "xtick.labelsize": 12,
    "ytick.labelsize": 12,
    "legend.fontsize": 12,
    "figure.titlesize": 18,
})

# Load labels
loads = ["0", "220", "2×220", "3×220", "4×220"]
x = np.arange(len(loads))

# Colors (same as before)
colors = [
    "#6B8FBF",
    "#7FB77E",
    "#E6A157",
    "#D67272",
]

# ------------------------
# Voltage data
# ------------------------
voltage_data = {
    "Sensor 40": {
        "ref": np.array([3.302, 3.291, 3.280, 3.269, 3.117]),
        "ina": np.array([3.371, 3.359, 3.348, 3.336, 3.184]),
    },
    "Sensor 41": {
        "ref": np.array([3.303, 3.291, 3.279, 3.267, 3.116]),
        "ina": np.array([3.369, 3.357, 3.345, 3.333, 3.180]),
    },
    "Sensor 44": {
        "ref": np.array([3.303, 3.292, 3.280, 3.268, 3.116]),
        "ina": np.array([3.485, 3.473, 3.461, 3.449, 3.289]),
    },
    "Sensor 45": {
        "ref": np.array([3.303, 3.291, 3.279, 3.267, 3.110]),
        "ina": np.array([3.367, 3.355, 3.343, 3.331, 3.173]),
    },
}

# ------------------------
# Current data
# ------------------------
current_data = {
    "Sensor 40": {
        "ref": np.array([0.000, 14.870, 29.050, 42.900, 55.100]),
        "ina": np.array([-0.015, 14.390, 28.701, 42.677, 53.351]),
    },
    "Sensor 41": {
        "ref": np.array([0.000, 14.830, 29.030, 42.900, 54.800]),
        "ina": np.array([0.007, 14.816, 28.970, 43.254, 54.680]),
    },
    "Sensor 44": {
        "ref": np.array([0.000, 14.910, 29.230, 43.300, 55.200]),
        "ina": np.array([-0.121, 14.882, 29.000, 43.236, 54.952]),
    },
    "Sensor 45": {
        "ref": np.array([0.000, 14.910, 29.220, 43.300, 55.300]),
        "ina": np.array([-0.024, 17.600, 34.721, 51.598, 65.377]),
    },
}

# ------------------------
# Create figure
# ------------------------
fig, (ax1, ax2) = plt.subplots(
    2, 1,
    figsize=(9, 8),
    sharex=True
)

# ------------------------
# Voltage subplot
# ------------------------
for (sensor, values), color in zip(voltage_data.items(), colors):
    error = values["ina"] - values["ref"]
    ax1.plot(x, error, "o-", linewidth=2, markersize=6, color=color, label=sensor)

ax1.axhline(0, linestyle="--", color="black", alpha=0.7)
ax1.set_ylabel("Absolute voltage error [V]")
ax1.set_title("Absolute error of voltage measurements")


# ------------------------
# Current subplot
# ------------------------
for (sensor, values), color in zip(current_data.items(), colors):
    error = values["ina"] - values["ref"]
    ax2.plot(x, error, "o-", linewidth=2, markersize=6, color=color, label=sensor)

ax2.axhline(0, linestyle="--", color="black", alpha=0.7)
ax2.set_ylabel("Absolute current error [mA]")
ax2.set_xlabel("Load configuration")
ax2.set_title("Absolute error of current measurements")
ax2.legend(loc="upper left")

# Shared x-axis formatting
ax2.set_xticks(x)
ax2.set_xticklabels(loads)

# Clean up spines
for ax in [ax1, ax2]:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

# Layout
plt.tight_layout()

# Save (same folder)
save_path = r"C:\Users\matil\OneDrive\Skrivebord\Studieportefølje\repos\Bachelor\data_treatment\hardware_tests\plots\Combined_abs_error.png"
plt.savefig(save_path, dpi=300, bbox_inches="tight")

plt.show()