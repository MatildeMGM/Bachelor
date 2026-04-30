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

colors = [
    "#6B8FBF",  # soft blue
    "#7FB77E",  # soft green
    "#E6A157",  # soft orange
    "#D67272",  # soft red
]

fig, ax = plt.subplots(figsize=(9, 5.2))

for (sensor, values), color in zip(data.items(), colors):
    I_ref = values["I_ref"]
    I_ina = values["I_ina"]

    abs_error = I_ina - I_ref

    ax.plot(
        x,
        abs_error,
        "o-",
        linewidth=2,
        markersize=6,
        color=color,
        label=sensor,
    )

ax.set_xticks(x)
ax.set_xticklabels(loads)

ax.set_xlabel("Load configuration")
ax.set_ylabel("Absolute current error [mA]")



ax.axhline(0, linestyle="--", color="black", alpha=0.7)
ax.legend()

plt.tight_layout()

save_path = r"C:\Users\matil\OneDrive\Skrivebord\Studieportefølje\repos\Bachelor\data_treatment\hardware_tests\plots\Current_abs_error.png"
plt.savefig(save_path, dpi=300, bbox_inches="tight")

plt.show()