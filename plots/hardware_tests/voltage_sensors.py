import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

DATA_FILE = Path(r"C:\Users\matil\OneDrive\Skrivebord\Studieportefølje\repos\Bachelor\data\hardware_tests\sensor40_current_3.3.xlsx")

SHEETS = {
    "Sensor 40": "Sensor40_Voltage_3_3V",
    "Sensor 41": "Sensor41_Voltage_3_3V",
    "Sensor 44": "Sensor44_Voltage_3_3V",
    "Sensor 45": "Sensor45_Voltage_3_3V",
}

LOADS = ["0", "220", "2×220", "3×220", "4×220"]

R_NOM = {
    "0": np.nan,
    "220": 220.0,
    "2×220": 110.0,
    "3×220": 73.3,
    "4×220": 55.0,
}

V_REF = {
    "Sensor 40": {"0": 3.302, "220": 3.291, "2×220": 3.280, "3×220": 3.269, "4×220": 3.117},
    "Sensor 41": {"0": 3.303, "220": 3.291, "2×220": 3.279, "3×220": 3.267, "4×220": 3.116},
    "Sensor 44": {"0": 3.303, "220": 3.292, "2×220": 3.280, "3×220": 3.268, "4×220": 3.116},
    "Sensor 45": {"0": 3.303, "220": 3.291, "2×220": 3.279, "3×220": 3.267, "4×220": 3.110},
}

V_REF_UNCERT = 0.005

TIME_WINDOWS = {
    "Sensor 40": {
        "0": (1005, 1090),
        "220": (1105, 1190),
        "2×220": (1305, 1390),
        "3×220": (1405, 1490),
        "4×220": (1505, 1590),
    },
    "Sensor 41": {
        "0": (205, 290),
        "220": (305, 390),
        "2×220": (405, 490),
        "3×220": (505, 590),
        "4×220": (605, 690),
    },
    "Sensor 44": {
        "0": (105, 190),
        "220": (205, 290),
        "2×220": (305, 390),
        "3×220": (405, 490),
        "4×220": (505, 590),
    },
    "Sensor 45": {
        "0": (105, 190),
        "220": (205, 290),
        "2×220": (305, 390),
        "3×220": (405, 490),
        "4×220": (505, 590),
    },
}

OUT_PNG = "voltage_calibration_all_sensors.png"
OUT_PDF = "voltage_calibration_all_sensors.pdf"
OUT_CSV = "voltage_calibration_summary.csv"


def try_numeric_conversion(series: pd.Series) -> pd.Series:
    cleaned = series.astype(str).str.strip()
    cleaned = cleaned.str.replace(",", ".", regex=False)

    try:
        return pd.to_numeric(cleaned)
    except Exception:
        return series


def read_excel_with_decimal_comma(path: Path, sheet_name: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet_name)

    df.columns = [str(c).strip().replace("\n", " ") for c in df.columns]

    for col in df.columns:
        df[col] = try_numeric_conversion(df[col])

    return df


def normalize_name(name: str) -> str:
    return str(name).strip().lower().replace(" ", "").replace("_", "")


def find_column(df: pd.DataFrame, keyword_groups):
    normalized = {col: normalize_name(col) for col in df.columns}

    for col, norm in normalized.items():
        for keywords in keyword_groups:
            if all(k in norm for k in keywords):
                return col

    raise ValueError(f"Column not found. Available columns: {list(df.columns)}")


def summarize_sensor(sensor_name: str, file_path: Path, sheet_name: str) -> pd.DataFrame:
    df = read_excel_with_decimal_comma(file_path, sheet_name)

    print(f"\nUsing sheet for {sensor_name}: {sheet_name}")
    print(f"Columns: {list(df.columns)}")

    time_col = find_column(df, [["time"], ["times"], ["times"]])
    voltage_col = find_column(df, [["bus", "v"], ["voltage"], ["bus4", "v"]])

    rows = []

    for load in LOADS:
        t0, t1 = TIME_WINDOWS[sensor_name][load]

        segment = df.loc[(df[time_col] >= t0) & (df[time_col] <= t1), voltage_col].dropna()

        if len(segment) == 0:
            v_mean = np.nan
            v_std = np.nan
        else:
            v_mean = segment.mean()
            v_std = segment.std(ddof=1) if len(segment) > 1 else 0.0

        v_ref = V_REF[sensor_name][load]
        delta_v = v_mean - v_ref if pd.notna(v_mean) else np.nan
        error_pct = (delta_v / v_ref) * 100 if pd.notna(v_mean) else np.nan

        rows.append({
            "sensor": sensor_name,
            "sheet": sheet_name,
            "load": load,
            "R_nom_ohm": R_NOM[load],
            "time_start_s": t0,
            "time_end_s": t1,
            "n_samples": len(segment),
            "V_ref_V": v_ref,
            "V_ref_uncert_V": V_REF_UNCERT,
            "V_INA_mean_V": v_mean,
            "V_INA_std_V": v_std,
            "Delta_V": delta_v,
            "Error_pct": error_pct,
        })

    return pd.DataFrame(rows)


if not DATA_FILE.exists():
    raise FileNotFoundError(f"Excel file not found: {DATA_FILE}")

xls = pd.ExcelFile(DATA_FILE)
print("Available sheets:")
print(xls.sheet_names)

all_results = []

for sensor, sheet in SHEETS.items():
    if sheet not in xls.sheet_names:
        print(f"Warning: sheet '{sheet}' not found for {sensor}")
        continue

    all_results.append(summarize_sensor(sensor, DATA_FILE, sheet))

if not all_results:
    raise FileNotFoundError("No matching voltage sheets could be loaded.")

results = pd.concat(all_results, ignore_index=True)
results.to_csv(OUT_CSV, index=False)

x = np.arange(len(LOADS))
available_sensors = [s for s in SHEETS if s in results["sensor"].unique()]
offsets = np.linspace(-0.24, 0.24, len(available_sensors))

fig, ax = plt.subplots(figsize=(8.5, 4.8))

for offset, sensor in zip(offsets, available_sensors):
    sub = results[results["sensor"] == sensor].copy()
    sub["load"] = pd.Categorical(sub["load"], categories=LOADS, ordered=True)
    sub = sub.sort_values("load")

    err_nom = sub["Error_pct"].to_numpy()
    v_ina = sub["V_INA_mean_V"].to_numpy()
    v_ref = sub["V_ref_V"].to_numpy()

    err_min = ((v_ina - (v_ref + V_REF_UNCERT)) / (v_ref + V_REF_UNCERT)) * 100
    err_max = ((v_ina - (v_ref - V_REF_UNCERT)) / (v_ref - V_REF_UNCERT)) * 100

    yerr_lower = np.abs(err_nom - err_min)
    yerr_upper = np.abs(err_max - err_nom)

    ax.errorbar(
        x + offset,
        err_nom,
        yerr=[yerr_lower, yerr_upper],
        fmt="o-",
        capsize=4,
        linewidth=1.5,
        markersize=5,
        label=sensor,
    )

ax.set_xticks(x)
ax.set_xticklabels(LOADS)
ax.set_xlabel("Load configuration")
ax.set_ylabel("Relative voltage error [%]")
ax.set_title("Voltage calibration of INA226 sensors")
ax.grid(True, alpha=0.3)
ax.legend()

plt.tight_layout()
plt.savefig(OUT_PNG, dpi=300, bbox_inches="tight")
plt.savefig(OUT_PDF, bbox_inches="tight")
plt.show()