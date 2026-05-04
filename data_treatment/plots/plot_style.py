from __future__ import annotations

import matplotlib.pyplot as plt


BLUE = "#2F6DB3"
GREEN = "#2E8B57"
PURPLE = "#7B4FA3"
LIGHT_BLUE = "#8DB6E8"
LIGHT_GREEN = "#7CCBA2"
LIGHT_PURPLE = "#B99AD6"
DARK = "#243447"
GREY = "#8A94A6"
GRID = "#D6DCE5"

CURRENT_COLORS = {
    0.2: BLUE,
    0.3: GREEN,
    0.4: PURPLE,
}

DISTANCE_COLORS = {
    1: PURPLE,
    5: BLUE,
    10: GREEN,
    15: LIGHT_BLUE,
    20: LIGHT_PURPLE,
}

SENSOR_COLORS = {
    "Sensor 40": BLUE,
    "Sensor 41": GREEN,
    "Sensor 44": PURPLE,
    "Sensor 45": LIGHT_BLUE,
}


def set_report_style():
    plt.style.use("default")
    plt.rcParams.update({
        "figure.figsize": (6.4, 4.6),
        "figure.dpi": 120,
        "savefig.dpi": 300,
        "font.family": "DejaVu Sans",
        "font.size": 18,
        "axes.titlesize": 20,
        "axes.labelsize": 20,
        "xtick.labelsize": 17,
        "ytick.labelsize": 17,
        "legend.fontsize": 14,
        "axes.edgecolor": DARK,
        "axes.labelcolor": DARK,
        "xtick.color": DARK,
        "ytick.color": DARK,
        "text.color": DARK,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.9,
        "grid.alpha": 0.7,
        "legend.frameon": False,
        "lines.linewidth": 3.0,
        "lines.markersize": 7,
    })


def polish_axes(ax):
    ax.grid(True, axis="y")
    ax.grid(False, axis="x")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.margins(x=0.03)


def save_report_figure(fig, path):
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
