import numpy as np
import matplotlib.pyplot as plt

plt.rcParams.update({
    "font.size": 14,
    "axes.titlesize": 16,
    "axes.labelsize": 14,
    "xtick.labelsize": 12,
    "ytick.labelsize": 12,
    "legend.fontsize": 12,
    "figure.titlesize": 18,
})

plt.style.use("seaborn-v0_8-whitegrid")

loads = ["0", "220", "2×220", "3×220", "4×220"]
x = np.arange(len(loads))

data = {
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

colors = [
    "#6B8FBF",  # blue
    "#7FB77E",  # green
    "#E6A157",  # orange
    "#D67272",  # red
]

fig, ax = plt.subplots(figsize=(9, 5.2))

for (sensor, values), color in zip(data.items(), colors):
    V_ref = values["V_ref"]
    V_ina = values["V_ina"]

    abs_error = V_ina - V_ref

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
ax.set_ylabel("Absolute voltage error [V]")



ax.axhline(0, linestyle="--", color="black", alpha=0.7)
ax.legend(loc="center right")


plt.tight_layout()

save_path = r"C:\Users\matil\OneDrive\Skrivebord\Studieportefølje\repos\Bachelor\data_treatment\hardware_tests\plots\Voltage_abs_error.png"
plt.savefig(save_path, dpi=300, bbox_inches="tight")

plt.show()