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


def plot_current_correction():
    set_report_style()
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.5), sharex=True, sharey=True)
    axes = axes.flatten()

    for ax, (sensor, values) in zip(axes, data.items()):
        I_ref = values["I_ref"]
        I_ina = values["I_ina"]
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

        ax.plot(x, raw_error, "o-", color=GREY, label="Raw error")
        ax.plot(x, corr_error, "o--", color=SENSOR_COLORS[sensor], label="Corrected error")
        ax.axhline(0, linestyle="--", color="#243447", alpha=0.7, linewidth=1)

        ax.set_title(f"{sensor}\n{title_eq}")
        ax.set_xticks(x)
        ax.set_xticklabels(loads)
        polish_axes(ax)
        ax.legend(loc="upper left")

    axes[0].set_ylabel("Current error [mA]")
    axes[2].set_ylabel("Current error [mA]")
    axes[2].set_xlabel("Load configuration")
    axes[3].set_xlabel("Load configuration")

    save_report_figure(fig, PLOT_DIR / "current_correction.png")


def plot_current_abs_error():
    set_report_style()
    fig, ax = plt.subplots()

    for sensor, values in data.items():
        I_ref = values["I_ref"]
        I_ina = values["I_ina"]
        abs_error = I_ina - I_ref

        ax.plot(x, abs_error, "o-", color=SENSOR_COLORS[sensor], label=sensor)

    ax.set_xticks(x)
    ax.set_xticklabels(loads)
    ax.set_xlabel("Load configuration")
    ax.set_ylabel("Current error [mA]")
    ax.set_title("INA226 Current Measurement Error")
    ax.axhline(0, linestyle="--", color="#243447", alpha=0.7, linewidth=1)
    polish_axes(ax)
    ax.legend()

    save_report_figure(fig, PLOT_DIR / "Current_abs_error.png")


def main():
    plot_current_correction()
    plot_current_abs_error()

    print("\nSaved current sensor plots in:")
    print(PLOT_DIR)


if __name__ == "__main__":
    main()
