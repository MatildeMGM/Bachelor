from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt


def find_bachelor_dir():
    script_dir = Path(__file__).resolve().parent

    for parent in [script_dir] + list(script_dir.parents):
        if (parent / "data").exists() and (parent / "data_treatment").exists():
            return parent

    raise FileNotFoundError("Could not find bachelor folder")


BACHELOR_DIR = find_bachelor_dir()
PLOT_DIR = BACHELOR_DIR / "control_parameters_new" / "scripts_sensors" / "plots"
PLOT_DIR.mkdir(parents=True, exist_ok=True)


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


def plot_voltage_abs_error():
    colors = [
        "#6B8FBF",
        "#7FB77E",
        "#E6A157",
        "#D67272",
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

    save_path = PLOT_DIR / "Voltage_abs_error.png"
    plt.savefig(save_path, dpi=300, bbox_inches="tight")

    plt.show()


def plot_voltage_correction():
    fig, axes = plt.subplots(
        2, 2,
        figsize=(13, 9),
        sharex=True,
        sharey=True,
        constrained_layout=True
    )
    axes = axes.flatten()

    raw_color = "#9aa0a6"

    corr_colors = {
        "Sensor 40": "#4c78a8",
        "Sensor 41": "#54a24b",
        "Sensor 44": "#f28e2b",
        "Sensor 45": "#e15759",
    }

    all_errors = []

    for ax, (sensor, values) in zip(axes, data.items()):
        V_ref = values["V_ref"]
        V_ina = values["V_ina"]

        corr_color = corr_colors[sensor]

        raw_error = V_ina - V_ref

        b = np.mean(V_ref - V_ina)
        sign = "+" if b >= 0 else "-"
        V_corr = V_ina + b
        corr_error = V_corr - V_ref

        all_errors.extend(raw_error)
        all_errors.extend(corr_error)

        title_eq = rf"$V_{{corr}} = V_{{INA}} {sign} {abs(b):.3f}\,\mathrm{{V}}$"

        ax.plot(
            x, raw_error, "o-",
            linewidth=2.2,
            color=raw_color,
            label="Raw measurement error"
        )

        ax.plot(
            x, corr_error, "o--",
            linewidth=2,
            color=corr_color,
            label="Corrected error"
        )

        ax.axhline(0, linestyle="--", color="black", alpha=0.7)

        ax.set_title(
            f"{sensor}\n{title_eq}",
            fontweight="bold",
            pad=12
        )

        ax.set_xticks(x)
        ax.set_xticklabels(loads)

        ax.grid(True, linestyle="--", alpha=0.4)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        ax.legend(loc="upper left", frameon=True)

    ymin = min(all_errors) - 0.01
    ymax = 0.3
    for ax in axes:
        ax.set_ylim(ymin, ymax)

    axes[0].set_ylabel("Absolute voltage error [V]")
    axes[2].set_ylabel("Absolute voltage error [V]")
    axes[2].set_xlabel("Load configuration")
    axes[3].set_xlabel("Load configuration")

    save_path = PLOT_DIR / "Voltage_correction.png"
    plt.savefig(save_path, dpi=300, bbox_inches="tight")

    plt.show()


def main():
    plot_voltage_abs_error()
    plot_voltage_correction()

    print("\nSaved sensor plots in:")
    print(PLOT_DIR)


if __name__ == "__main__":
    main()