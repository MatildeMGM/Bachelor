from dataclasses import dataclass
import pandas as pd
import numpy as np


@dataclass
class ScenarioSchedulerConfig:
    dt_hours: float = 0.25

    price_high_threshold: float = 0.60

    battery_e_max_wh: float = 6.33
    battery_e_min_wh: float = 0.80
    battery_e_charge_stop_wh: float = 6.00
    battery_e_discharge_start_wh: float = 1.80

    battery_charge_power_w: float = 0.60
    battery_discharge_power_w: float = 0.60
    battery_eta_ch: float = 0.95
    battery_eta_dch: float = 0.95

    pv_use_threshold_w: float = 0.20
    pv_charge_threshold_w: float = 0.20

    pem_ready_initial: bool = True


def build_scenario_schedule(
    df_forecast: pd.DataFrame,
    battery_e0_wh: float,
    cfg: ScenarioSchedulerConfig,
    pem_ready0: bool | None = None,
) -> pd.DataFrame:
    """
    Expected columns in df_forecast:
        load_w
        pv_w
        price
    Returns a schedule with one scenario per 15 min slot.
    """

    if pem_ready0 is None:
        pem_ready = cfg.pem_ready_initial
    else:
        pem_ready = pem_ready0

    e_batt = float(battery_e0_wh)
    records = []

    for timestamp, row in df_forecast.iterrows():
        load_w = float(row["load_w"])
        pv_w = float(row["pv_w"])
        price = float(row["price"])

        scenario = 1
        reason = "fallback"

        high_price = price >= cfg.price_high_threshold

        if high_price:
            if pv_w >= max(load_w, cfg.pv_use_threshold_w):
                scenario = 4
                reason = "high price, PV can feed load"

            elif (
                e_batt > cfg.battery_e_discharge_start_wh
                and load_w <= cfg.battery_discharge_power_w
            ):
                scenario = 5
                reason = "high price, use battery"

                e_batt = max(
                    cfg.battery_e_min_wh,
                    e_batt - (load_w / cfg.battery_eta_dch) * cfg.dt_hours
                )

            elif pem_ready:
                scenario = 6
                reason = "high price, use PEM"

            else:
                scenario = 1
                reason = "high price, no storage available"

        else:
            if (
                pv_w >= cfg.pv_charge_threshold_w
                and e_batt < cfg.battery_e_charge_stop_wh
            ):
                scenario = 2
                reason = "low price, charge battery from PV"

                e_batt = min(
                    cfg.battery_e_max_wh,
                    e_batt + cfg.battery_charge_power_w * cfg.battery_eta_ch * cfg.dt_hours
                )

            elif pv_w >= cfg.pv_charge_threshold_w and not pem_ready:
                scenario = 3
                reason = "low price, charge PEM from PV"

            else:
                scenario = 1
                reason = "low price fallback"

        records.append(
            {
                "timestamp": timestamp,
                "price": price,
                "load_w": load_w,
                "pv_w": pv_w,
                "scenario_ref": scenario,
                "battery_e_target_wh": e_batt,
                "pem_ready_ref": pem_ready,
                "reason": reason,
            }
        )

    return pd.DataFrame(records).set_index("timestamp")