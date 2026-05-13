
import json
from pathlib import Path

import numpy as np
import pandas as pd

from config import (
    ASSETS_DIR,
    CSV_PATH,
    RAW_STEP_SECONDS,
    SIM_STEP_SECONDS,
    WIND_SCALE_MODE,
    WIND_TURBINE_RATED_KW,
)

def load_flat_profile(csv_path: Path) -> np.ndarray:
    df = pd.read_csv(csv_path)
    time_cols = [c for c in df.columns if c != "Date"]
    values = df[time_cols].to_numpy(dtype=float).reshape(-1)
    return values

def upsample_15min_to_5min(values: np.ndarray) -> np.ndarray:
    if SIM_STEP_SECONDS == RAW_STEP_SECONDS:
        return values.copy()

    factor = RAW_STEP_SECONDS // SIM_STEP_SECONDS
    if factor != 3:
        raise ValueError("This script currently expects 15 min -> 5 min interpolation.")

    out = []
    for i in range(len(values) - 1):
        a = values[i]
        b = values[i + 1]
        out.append(a)
        out.append(a + (b - a) / 3.0)
        out.append(a + 2.0 * (b - a) / 3.0)
    out.append(values[-1])
    return np.array(out, dtype=float)

def scale_profile(values: np.ndarray) -> np.ndarray:
    if WIND_SCALE_MODE == "assume_kw":
        scaled = values.copy()
    elif WIND_SCALE_MODE == "normalize_to_rated":
        vmax = float(np.max(values))
        scaled = values / vmax * WIND_TURBINE_RATED_KW
    else:
        raise ValueError(f"Unsupported WIND_SCALE_MODE: {WIND_SCALE_MODE}")
    return np.clip(scaled, 0.0, None)

def main():
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    raw = load_flat_profile(CSV_PATH)
    interp = upsample_15min_to_5min(raw)
    scaled_kw = scale_profile(interp)

    # uint16 is enough for 0..4200 kW
    data_u16 = np.rint(scaled_kw).astype(np.uint16)
    bin_path = ASSETS_DIR / "wind_profile_5min.bin"
    data_u16.tofile(bin_path)

    meta = {
        "source_csv": str(CSV_PATH),
        "raw_points": int(len(raw)),
        "processed_points": int(len(data_u16)),
        "raw_step_seconds": RAW_STEP_SECONDS,
        "sim_step_seconds": SIM_STEP_SECONDS,
        "scale_mode": WIND_SCALE_MODE,
        "rated_kw": WIND_TURBINE_RATED_KW,
        "raw_min": float(np.min(raw)),
        "raw_max": float(np.max(raw)),
        "raw_mean": float(np.mean(raw)),
        "scaled_min_kw": float(np.min(scaled_kw)),
        "scaled_max_kw": float(np.max(scaled_kw)),
        "scaled_mean_kw": float(np.mean(scaled_kw)),
    }
    (ASSETS_DIR / "wind_profile_meta.json").write_text(json.dumps(meta, indent=2))
    print(f"Wrote {bin_path}")
    print(json.dumps(meta, indent=2))

if __name__ == "__main__":
    main()
