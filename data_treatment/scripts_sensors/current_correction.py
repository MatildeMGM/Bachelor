import numpy as np
import matplotlib.pyplot as plt

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



loads = ["0", "220", "2×220", "3×220", "4×220"]
x = np.arange(len(loads))

data = {
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

fig, axes = plt.subplots(2, 2, figsize=(12, 9), sharex=True, sharey=True)
axes = axes.flatten()

raw_color = "#9aa0a6"

corr_colors = {
    "Sensor 40": "#4c78a8",
    "Sensor 41": "#54a24b",
    "Sensor 44": "#f28e2b",
    "Sensor 45": "#e15759",
}

for ax, (sensor, values) in zip(axes, data.items()):
    I_ref = values["I_ref"]
    I_ina = values["I_ina"]

    corr_color = corr_colors[sensor]
    raw_error = I_ina - I_ref

    if sensor == "Sensor 45":
        a, b = np.polyfit(I_ina, I_ref, 1)
        I_corr = a * I_ina + b
        title_eq = rf"$I_{{corr}} = {a:.3f}I_{{INA}} + {b:.3f}$"
    else:
        b = np.mean(I_ref - I_ina)
        I_corr = I_ina + b
        title_eq = rf"$I_{{corr}} = I_{{INA}} + {b:.3f}$"

    corr_error = I_corr - I_ref

    ax.plot(x, raw_error, "o-", linewidth=2.2, color=raw_color, label="Raw measurement error")
    ax.plot(x, corr_error, "o--", linewidth=2, color=corr_color, label="Corrected error")

    ax.axhline(0, linestyle="--", color="black", alpha=0.7)

    ax.set_title(f"{sensor}\n{title_eq}", fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(loads)

    ax.grid(True, linestyle="--", alpha=0.4)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.legend( loc="upper left")

axes[0].set_ylabel("Absolute error [mA]")
axes[2].set_ylabel("Absolute error [mA]")
axes[2].set_xlabel("Load configuration")
axes[3].set_xlabel("Load configuration")



plt.tight_layout(rect=[0, 0, 1, 0.95])

# Save the figure
save_path = r"C:\Users\matil\OneDrive\Skrivebord\Studieportefølje\repos\Bachelor\data_treatment\hardware_tests\plots\current_correction.png"
plt.savefig(save_path, dpi=300, bbox_inches="tight")

plt.show()