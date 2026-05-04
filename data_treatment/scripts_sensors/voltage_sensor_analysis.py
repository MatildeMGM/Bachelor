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

from plot_style import GREY, SENSOR_COLORS, polish_axes, save_report_figure, set_report_style


loads = ["0", "220", "2x220", "3x220", "4x220"]
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
    set_report_style()
    fig, ax = plt.subplots()

    for sensor, values in data.items():
        V_ref = values["V_ref"]
        V_ina = values["V_ina"]
        abs_error = V_ina - V_ref

        ax.plot(x, abs_error, "o-", color=SENSOR_COLORS[sensor], label=sensor)

    ax.set_xticks(x)
    ax.set_xticklabels(loads)
    ax.set_xlabel("Load configuration")
    ax.set_ylabel("Voltage error [V]")
    ax.set_title("INA226 Voltage Measurement Error")
    ax.axhline(0, linestyle="--", color="#243447", alpha=0.7, linewidth=1)
    polish_axes(ax)
    ax.legend(loc="center right")

    save_report_figure(fig, PLOT_DIR / "Voltage_abs_error.png")


def plot_voltage_correction():
    set_report_style()
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.5), sharex=True, sharey=True)
    axes = axes.flatten()
    all_errors = []

    for ax, (sensor, values) in zip(axes, data.items()):
        V_ref = values["V_ref"]
        V_ina = values["V_ina"]
        raw_error = V_ina - V_ref

        b = np.mean(V_ref - V_ina)
        sign = "+" if b >= 0 else "-"
        V_corr = V_ina + b
        corr_error = V_corr - V_ref

        all_errors.extend(raw_error)
        all_errors.extend(corr_error)

        title_eq = rf"$V_{{corr}} = V_{{INA}} {sign} {abs(b):.3f}\,\mathrm{{V}}$"

        ax.plot(x, raw_error, "o-", color=GREY, label="Raw error")
        ax.plot(x, corr_error, "o--", color=SENSOR_COLORS[sensor], label="Corrected error")
        ax.axhline(0, linestyle="--", color="#243447", alpha=0.7, linewidth=1)

        ax.set_title(f"{sensor}\n{title_eq}")
        ax.set_xticks(x)
        ax.set_xticklabels(loads)
        polish_axes(ax)
        ax.legend(loc="upper left")

    ymin = min(all_errors) - 0.01
    ymax = max(all_errors) + 0.03
    for ax in axes:
        ax.set_ylim(ymin, ymax)

    axes[0].set_ylabel("Voltage error [V]")
    axes[2].set_ylabel("Voltage error [V]")
    axes[2].set_xlabel("Load configuration")
    axes[3].set_xlabel("Load configuration")

    save_report_figure(fig, PLOT_DIR / "Voltage_correction.png")


def main():
    plot_voltage_abs_error()
    plot_voltage_correction()

    print("\nSaved sensor plots in:")
    print(PLOT_DIR)


if __name__ == "__main__":
    main()
