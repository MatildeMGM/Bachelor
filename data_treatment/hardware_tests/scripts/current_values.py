import os
import numpy as np
import matplotlib.pyplot as plt

plt.style.use("seaborn-v0_8-whitegrid")
plt.rcParams.update({
    "font.size": 14,
    "axes.titlesize": 16,
    "axes.labelsize": 14,
    "xtick.labelsize": 12,
    "ytick.labelsize": 12,
    "legend.fontsize": 9,
    "figure.titlesize": 18,
})

loads = ["0", "220", "2×220", "3×220", "4×220"]
x = np.arange(len(loads))

# Multimeter current [mA]
I_mMeter = np.array([0.000, 14.910, 29.220, 43.300, 55.300])

# Resistances [ohm]
R_resistors = np.array([np.nan, 219.6, 109.5, 73.0, 54.6])
R_circuit   = np.array([np.nan, 172.9, 96.8, 67.1, 51.5])

# Sensor data
data = {
    "Sensor 40": {
        "V_ref": np.array([3.302, 3.291, 3.280, 3.269, 3.117]),
        "I_ina": np.array([-0.015, 14.390, 28.701, 42.677, 53.351]),
    },
    "Sensor 41": {
        "V_ref": np.array([3.303, 3.291, 3.279, 3.267, 3.116]),
        "I_ina": np.array([0.007, 14.816, 28.970, 43.254, 54.680]),
    },
    "Sensor 44": {
        "V_ref": np.array([3.303, 3.292, 3.280, 3.268, 3.116]),
        "I_ina": np.array([-0.121, 14.882, 29.000, 43.236, 54.952]),
    },
    "Sensor 45": {
        "V_ref": np.array([3.303, 3.291, 3.279, 3.267, 3.110]),
        "I_ina": np.array([-0.024, 17.600, 34.721, 51.598, 65.377]),
    },
}

sensor_colors = {
    "Sensor 40": "#4c78a8",
    "Sensor 41": "#54a24b",
    "Sensor 44": "#f28e2b",
    "Sensor 45": "#e15759",
}

fig, axes = plt.subplots(2, 2, figsize=(13, 9), sharex=True, sharey=True)
axes = axes.flatten()

all_currents = []

# -------- LOOP --------
for ax, (sensor, values) in zip(axes, data.items()):
    V_ref = values["V_ref"]
    I_ina = values["I_ina"]

    # Calculate currents
    I_calc_res = np.full_like(V_ref, np.nan)
    I_calc_circ = np.full_like(V_ref, np.nan)

    valid_res = ~np.isnan(R_resistors)
    valid_circ = ~np.isnan(R_circuit)

    I_calc_res[valid_res] = (V_ref[valid_res] / R_resistors[valid_res]) * 1000
    I_calc_circ[valid_circ] = (V_ref[valid_circ] / R_circuit[valid_circ]) * 1000

    # Set no-load = 0
    I_calc_res[0] = 0
    I_calc_circ[0] = 0

    # Collect for axis scaling
    all_currents.extend(I_ina)
    all_currents.extend(I_mMeter)
    all_currents.extend(I_calc_res[1:])
    all_currents.extend(I_calc_circ[1:])

    # -------- PLOT --------
    ax.plot(
    x, I_mMeter, "s-",
    color="#9467bd",  # lilla
    linewidth=2,
    label=r"$I_{mMeter}$"
    )

    ax.plot(
        x, I_calc_res, "d--",
        color="#edc948",  # gul
        linewidth=2,
        label=r"$I_{calc,res}$"
    )

    ax.plot(
        x, I_calc_circ, "^-.",
        color="#e377c2",  # pink
        linewidth=2,
        label=r"$I_{calc,circ}$"
    )
    ax.plot(x, I_ina, "o-", color=sensor_colors[sensor], linewidth=2.2, label=r"$I_{INA}$")

    ax.set_title(sensor, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(loads)

    ax.grid(True, linestyle="--", alpha=0.4)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.legend(loc="upper left", frameon=True)

# -------- SAME Y-LIMITS --------
ymin = min(all_currents) - 2
ymax = max(all_currents) + 2

for ax in axes:
    ax.set_ylim(ymin, ymax)

# Labels
axes[0].set_ylabel("Current [mA]")
axes[2].set_ylabel("Current [mA]")
axes[2].set_xlabel("Load configuration")
axes[3].set_xlabel("Load configuration")

fig.suptitle("Comparison of measured and calculated current values", fontweight="bold")

plt.tight_layout(rect=[0, 0, 1, 0.95])

# Save
save_path = r"C:\Users\matil\OneDrive\Skrivebord\Studieportefølje\repos\Bachelor\data_treatment\hardware_tests\plots\Current_reference_comparison_subplots.png"
os.makedirs(os.path.dirname(save_path), exist_ok=True)
plt.savefig(save_path, dpi=300, bbox_inches="tight")

plt.show()