from tensorflow.keras.models import load_model
import pickle
import numpy as np
import pandas as pd
import os
import requests


BASE_DIR = os.path.dirname(__file__)
PYTHON_DIR = os.path.dirname(BASE_DIR)

MODEL_PATH = os.path.join(PYTHON_DIR, "forecast", "lstm_model.keras")
SCALER_X_PATH = os.path.join(PYTHON_DIR, "forecast", "scaler_X.pkl")
SCALER_Y_PATH = os.path.join(PYTHON_DIR, "forecast", "scaler_y.pkl")
FEATURE_COLS_PATH = os.path.join(PYTHON_DIR, "forecast", "feature_cols.pkl")

LOOK_BACK = 72

model = None
scaler_X = None
scaler_Y = None
FEATURE_COLS = None
MODEL_LOADED = False


def fetch_recent_consumption(region="Region Hovedstaden", category2="Privat", hours=250):
    """
    Fetch recent hourly consumption data from Energi Data Service.
    Returns a DataFrame with one row per hour.
    """

    url = "https://api.energidataservice.dk/dataset/ConsumptionConsumerCategoryHour"

    params = {
        "limit": hours,
        "filter": f'{{"RegionName":["{region}"],"ConsumerCategory2":["{category2}"]}}',
        "sort": "TimeUTC DESC",
    }

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()

    data = response.json()
    records = data.get("records", [])

    if not records:
        raise RuntimeError("No records returned from Energi Data Service")

    df = pd.DataFrame(records)

    df["TimeUTC"] = pd.to_datetime(df["TimeUTC"])
    df["ConsumptionkWh"] = pd.to_numeric(df["ConsumptionkWh"], errors="coerce")

    df = df[["TimeUTC", "ConsumptionkWh"]].copy()

    df = (
        df.groupby("TimeUTC", as_index=False)["ConsumptionkWh"]
        .sum()
        .sort_values("TimeUTC")
        .reset_index(drop=True)
    )

    return df


def load_lstm_model_components():
    """Load model, scalers, and feature columns."""
    global model, scaler_X, scaler_Y, FEATURE_COLS, MODEL_LOADED

    try:
        model = load_model(MODEL_PATH)

        with open(SCALER_X_PATH, "rb") as f:
            scaler_X = pickle.load(f)

        with open(SCALER_Y_PATH, "rb") as f:
            scaler_Y = pickle.load(f)

        with open(FEATURE_COLS_PATH, "rb") as f:
            FEATURE_COLS = pickle.load(f)

        MODEL_LOADED = True
        print("[DEMAND] LSTM model components loaded successfully")
        return True

    except FileNotFoundError as e:
        print(f"[DEMAND] WARNING: Model components not found: {e}")
        MODEL_LOADED = False
        return False

    except Exception as e:
        print(f"[DEMAND] ERROR loading model components: {e}")
        MODEL_LOADED = False
        return False


load_lstm_model_components()


def demand_forecast_96_slots(region="Region Hovedstaden", category2="Privat"):
    df_hourly = fetch_recent_consumption(region=region, category2=category2)

    now = pd.Timestamp.now()
    last_data = df_hourly["TimeUTC"].iloc[-1]

    print("\n--- Data freshness check ---")
    print("Latest available data:", last_data)
    print("Current system time :", now)

    hourly_forecast = generate_hourly_lstm_forecast(df_hourly)

    print_forecast_vs_recent_actual(df_hourly, hourly_forecast)

    forecast_96 = demand_15_min_resolution(hourly_forecast)

    last_timestamp = pd.to_datetime(df_hourly["TimeUTC"].iloc[-1])
    forecast_times_96 = pd.date_range(
        start=last_timestamp + pd.Timedelta(hours=1),
        periods=96,
        freq="15min",
    )

    return forecast_times_96, forecast_96


def generate_hourly_lstm_forecast(df_hourly):
    if not MODEL_LOADED:
        raise RuntimeError("LSTM model components are not loaded.")

    X_input = prepare_features_for_latest_window(df_hourly)

    X_scaled = scaler_X.transform(X_input.reshape(-1, X_input.shape[-1]))
    X_scaled = X_scaled.reshape(1, LOOK_BACK, len(FEATURE_COLS))

    y_pred_scaled = model.predict(X_scaled, verbose=0)
    y_pred = scaler_Y.inverse_transform(y_pred_scaled.reshape(-1, 1)).flatten()

    return y_pred


def prepare_features_for_latest_window(df_hourly):
    df = df_hourly.copy()
    df["TimeUTC"] = pd.to_datetime(df["TimeUTC"])
    df = df.sort_values("TimeUTC").reset_index(drop=True)

    df["hour"] = df["TimeUTC"].dt.hour
    df["weekday"] = df["TimeUTC"].dt.weekday
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    df["is_weekend"] = (df["weekday"] >= 5).astype(int)

    df["lag_1"] = df["ConsumptionkWh"].shift(1)
    df["lag_24"] = df["ConsumptionkWh"].shift(24)
    df["lag_168"] = df["ConsumptionkWh"].shift(168)

    df = df.dropna().reset_index(drop=True)

    if len(df) < LOOK_BACK:
        raise ValueError(f"Need at least {LOOK_BACK} processed rows, got {len(df)}")

    X_latest = df[FEATURE_COLS].iloc[-LOOK_BACK:].values

    return X_latest


def demand_15_min_resolution(hourly_values):
    """
    Convert 24 hourly values to 96 values using linear interpolation.
    """

    if len(hourly_values) < 2:
        raise ValueError("Need at least 2 hourly values for interpolation")

    quarter_hour_values = []

    for i in range(len(hourly_values)):
        start_value = hourly_values[i]

        if i < len(hourly_values) - 1:
            end_value = hourly_values[i + 1]
        else:
            end_value = start_value

        quarter_hour_values.append(start_value)
        quarter_hour_values.append(start_value + (end_value - start_value) * 0.25)
        quarter_hour_values.append(start_value + (end_value - start_value) * 0.50)
        quarter_hour_values.append(start_value + (end_value - start_value) * 0.75)

    return np.array(quarter_hour_values)


def print_forecast_vs_recent_actual(df_hourly, forecast):
    """
    Print forecast compared with recent actual values.
    """

    last_timestamp = pd.to_datetime(df_hourly["TimeUTC"].iloc[-1])

    forecast_times = pd.date_range(
        start=last_timestamp + pd.Timedelta(hours=1),
        periods=len(forecast),
        freq="h",
    )

    recent_actual = df_hourly["ConsumptionkWh"].iloc[-len(forecast):].values

    print("\nForecast vs recent actual sanity check:\n")
    print(f"{'Time':<20} {'Actual':>12} {'Forecast':>12}")

    for i in range(len(forecast)):
        time_str = forecast_times[i].strftime("%Y-%m-%d %H:%M")
        actual = recent_actual[i] if i < len(recent_actual) else np.nan

        print(f"{time_str:<20} {actual:>12.0f} {forecast[i]:>12.0f}")


if __name__ == "__main__":
    forecast_times_96, forecast_96 = demand_forecast_96_slots()

    print("\nFirst 10 forecast timestamps and values:\n")

    for t, v in zip(forecast_times_96[:10], forecast_96[:10]):
        print(t, round(v, 2))