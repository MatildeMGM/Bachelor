import numpy as np
import matplotlib.pyplot as plt

plt.style.use("seaborn-v0_8-whitegrid")

plt.rcParams.update({
    "font.size": 14,
    "axes.titlesize": 16,
    "axes.labelsize": 14,
    "xtick.labelsize": 12,
    "ytick.labelsize": 12,
    "legend.fontsize": 10,
    "figure.titlesize": 18,
})

loads = ["0", "220", "2×220", "3×220", "4×220"]
x = np.arange(len(loads))

voltage_data = {
    "Sensor 40": {
        "V_ref": np.array([3.302, 3.291, 3.280, 3.269, 3.117]),
        "V_ina": np.array([3.371, 3.359, 3.348, 3.336, 3.184]),
    },
    "Sensor 41": {
        "V_ref": np.array([3.303, 3.291, 3.279, 3.267, 3.116]),
        "V_ina": np.array([3.369, 3.357, 3.345, 3.333, 3.180]),
    },
    "Sensor 44": {
        "V_ref": np.array([3.303, 3.292, 3.280, 3.268, 3.116]),
        "V_ina": np.array([3.485, 3.473, 3.461, 3.449, 3.289]),
    },
    "Sensor 45": {
        "V_ref": np.array([3.303, 3.291, 3.279, 3.267, 3.110]),
        "V_ina": np.array([3.367, 3.355, 3.343, 3.331, 3.173]),
    },
}

current_data = {
    "Sensor 40": {
        "I_ref": np.array([0.000, 14.870, 29.050, 42.900, 55.100]),
        "I_ina": np.array([-0.015, 14.390, 28.701, 42.677, 53.351]),
    },
    "Sensor 41": {
        "I_ref": np.array([0.000, 14.830, 29.030, 42.900, 54.800]),
        "I_ina": np.array([0.007, 14.816, 28.970, 43.254, 54.680]),
    },
    "Sensor 44": {
        "I_ref": np.array([0.000, 14.910, 29.230, 43.300, 55.200]),
        "I_ina": np.array([-0.121, 14.882, 29.000, 43.236, 54.952]),
    },
    "Sensor 45": {
        "I_ref": np.array([0.000, 14.910, 29.220, 43.300, 55.300]),
        "I_ina": np.array([-0.024, 17.600, 34.721, 51.598, 65.377]),
    },
}

raw_color = "#9aa0a6"

corr_colors = {
    "Sensor 40": "#4c78a8",
    "Sensor 41": "#54a24b",
    "Sensor 44": "#f28e2b",
    "Sensor 45": "#e15759",
}

sensors = list(voltage_data.keys())

fig, axes = plt.subplots(
    4, 2,
    figsize=(14, 16),
    sharex=True
)

voltage_errors_all = []
current_errors_all = []

for sensor in sensors:
    V_ref = voltage_data[sensor]["V_ref"]
    V_ina = voltage_data[sensor]["V_ina"]

    raw_error_v = V_ina - V_ref
    b_v = np.mean(V_ref - V_ina)
    V_corr = V_ina + b_v
    corr_error_v = V_corr - V_ref

    voltage_errors_all.extend(raw_error_v)
    voltage_errors_all.extend(corr_error_v)

    I_ref = current_data[sensor]["I_ref"]
    I_ina = current_data[sensor]["I_ina"]

    raw_error_i = I_ina - I_ref

    if sensor == "Sensor 45":
        a_i, b_i = np.polyfit(I_ina, I_ref, 1)
        I_corr = a_i * I_ina + b_i
        current_eq = rf"$I_{{corr}} = {a_i:.3f}I_{{INA}} + {b_i:.3f}$"
    else:
        b_i = np.mean(I_ref - I_ina)
        I_corr = I_ina + b_i
        current_eq = rf"$I_{{corr}} = I_{{INA}} + {b_i:.3f}$"

    corr_error_i = I_corr - I_ref

    current_errors_all.extend(raw_error_i)
    current_errors_all.extend(corr_error_i)

for row, sensor in enumerate(sensors):
    ax_v = axes[row, 0]
    ax_i = axes[row, 1]

    V_ref = voltage_data[sensor]["V_ref"]
    V_ina = voltage_data[sensor]["V_ina"]

    raw_error_v = V_ina - V_ref
    b_v = np.mean(V_ref - V_ina)
    V_corr = V_ina + b_v
    corr_error_v = V_corr - V_ref

    sign_v = "+" if b_v >= 0 else "-"
    voltage_eq = rf"$V_{{corr}} = V_{{INA}} {sign_v} {abs(b_v):.3f}\,\mathrm{{V}}$"

    ax_v.plot(
        x, raw_error_v, "o-",
        linewidth=2.2,
        color=raw_color,
        label="Raw measurement error"
    )
    ax_v.plot(
        x, corr_error_v, "o--",
        linewidth=2,
        color=corr_colors[sensor],
        label="Corrected error"
    )
    ax_v.axhline(0, linestyle="--", color="black", alpha=0.7)
    ax_v.set_title(f"{sensor} voltage\n{voltage_eq}", fontweight="bold", pad=10)
    ax_v.grid(True, linestyle="--", alpha=0.4)
    ax_v.spines["top"].set_visible(False)
    ax_v.spines["right"].set_visible(False)
    ax_v.legend(loc="upper left", frameon=True)

    I_ref = current_data[sensor]["I_ref"]
    I_ina = current_data[sensor]["I_ina"]

    raw_error_i = I_ina - I_ref

    if sensor == "Sensor 45":
        a_i, b_i = np.polyfit(I_ina, I_ref, 1)
        I_corr = a_i * I_ina + b_i
        current_eq = rf"$I_{{corr}} = {a_i:.3f}I_{{INA}} + {b_i:.3f}$"
    else:
        b_i = np.mean(I_ref - I_ina)
        I_corr = I_ina + b_i
        current_eq = rf"$I_{{corr}} = I_{{INA}} + {b_i:.3f}$"

    corr_error_i = I_corr - I_ref

    ax_i.plot(
        x, raw_error_i, "o-",
        linewidth=2.2,
        color=raw_color,
        label="Raw measurement error"
    )
    ax_i.plot(
        x, corr_error_i, "o--",
        linewidth=2,
        color=corr_colors[sensor],
        label="Corrected error"
    )
    ax_i.axhline(0, linestyle="--", color="black", alpha=0.7)
    ax_i.set_title(f"{sensor} current\n{current_eq}", fontweight="bold", pad=10)
    ax_i.grid(True, linestyle="--", alpha=0.4)
    ax_i.spines["top"].set_visible(False)
    ax_i.spines["right"].set_visible(False)
    ax_i.legend(loc="upper left", frameon=True)

voltage_ymin = min(voltage_errors_all) - 0.01
voltage_ymax = max(voltage_errors_all) + 0.01

current_ymin = min(current_errors_all) - 0.5
current_ymax = max(current_errors_all) + 0.5

for row in range(4):
    axes[row, 0].set_ylim(voltage_ymin, voltage_ymax)
    axes[row, 1].set_ylim(current_ymin, current_ymax)

for row in range(4):
    axes[row, 0].set_xticks(x)
    axes[row, 0].set_xticklabels(loads)
    axes[row, 1].set_xticks(x)
    axes[row, 1].set_xticklabels(loads)

axes[0, 0].set_ylabel("Absolute voltage error [V]")
axes[1, 0].set_ylabel("Absolute voltage error [V]")
axes[2, 0].set_ylabel("Absolute voltage error [V]")
axes[3, 0].set_ylabel("Absolute voltage error [V]")

axes[0, 1].set_ylabel("Absolute current error [mA]")
axes[1, 1].set_ylabel("Absolute current error [mA]")
axes[2, 1].set_ylabel("Absolute current error [mA]")
axes[3, 1].set_ylabel("Absolute current error [mA]")

axes[3, 0].set_xlabel("Load configuration")
axes[3, 1].set_xlabel("Load configuration")

plt.tight_layout()

save_path = r"C:\Users\matil\OneDrive\Skrivebord\Studieportefølje\repos\Bachelor\data_treatment\hardware_tests\plots\combined_sensor_corrections.png"
plt.savefig(save_path, dpi=300, bbox_inches="tight")

plt.show()
