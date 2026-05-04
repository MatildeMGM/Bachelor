from __future__ import annotations

"""Simple EMS scheduler for the accelerated daily load demonstration.

Python decides the wanted scenario from price, demand and live measurements.
The Arduino sketch still has the final safety check before switching relays.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_TREATMENT_DIR = PROJECT_ROOT / "data_treatment"
DEMAND_PROFILE_PATH = (
    Path(__file__).resolve().parent
    / "data"
    / "variable_load_signal"
    / "scaled_may_power_profile_15min.csv"
)


SCENARIO_DESCRIPTIONS = {
    1: "Load from grid. PV, battery and PEM are isolated.",
    2: "Load from grid. PV charges battery.",
    3: "Load from grid. PV charges PEM.",
    4: "Load from PV. Battery and PEM are isolated.",
    5: "Load from battery. PV and PEM are isolated.",
    6: "Load from PEM. PV and battery are isolated.",
}


@dataclass(frozen=True)
class BatteryLimits:
    min_voltage_v: float
    full_voltage_v: float
    usable_energy_wh: float
    max_discharge_power_w: float
    reserve_soc_percent: float = 20.0
    full_soc_percent: float = 90.0


@dataclass(frozen=True)
class PEMLimits:
    min_voltage_v: float
    min_hydrogen_ml: float
    max_discharge_power_w: float
    full_hydrogen_ml: float


@dataclass(frozen=True)
class PVLimits:
    min_voltage_v: float
    max_power_w: float
    min_load_power_w: float
    min_charging_power_w: float


@dataclass(frozen=True)
class EMSLimits:
    battery: BatteryLimits
    pem: PEMLimits
    pv: PVLimits


@dataclass
class ComponentState:
    battery_soc_percent: float = 50.0
    battery_voltage_v: float = 0.0
    battery_energy_wh: float | None = None
    pem_hydrogen_ml: float = 0.0
    pem_voltage_v: float = 0.0
    pv_voltage_v: float = 0.0
    pv_current_a: float = 0.0
    pv_power_w: float | None = None
    last_scenario: int = 1
    seconds_since_last_switch: float = 9999.0


@dataclass(frozen=True)
class SchedulerConfig:
    simulated_slot_hours: float = 0.25
    price_low_quantile: float = 0.35
    price_high_quantile: float = 0.70
    lookahead_slots: int = 96
    safety_margin_w: float = 0.005
    min_switch_seconds: float = 2.0


def load_limits(data_treatment_dir: Path | str = DATA_TREATMENT_DIR) -> EMSLimits:
    """Load the operating limits found during data processing."""

    base = Path(data_treatment_dir)

    battery_state = pd.read_csv(base / "processed_Battery" / "battery_state_table.csv")
    battery_discharge = pd.read_csv(
        base / "processed_Battery" / "battery_discharge_summary.csv"
    ).iloc[0]

    pem_params = pd.read_csv(base / "processed_PEM" / "pem_control_parameters.csv").iloc[0]
    pem_state = pd.read_csv(base / "processed_PEM" / "pem_state_table.csv")
    pem_sweep = pd.read_csv(base / "processed_PEM" / "current_sweep_summary.csv").iloc[0]

    pv_params = pd.read_csv(base / "processed_PV" / "pv_control_parameters.csv").iloc[0]

    return EMSLimits(
        battery=BatteryLimits(
            min_voltage_v=float(battery_state["voltage_min_V"].min()),
            full_voltage_v=4.2,
            usable_energy_wh=float(battery_discharge["usable_energy_Wh"]),
            max_discharge_power_w=float(battery_discharge["max_discharge_power_W"]),
        ),
        pem=PEMLimits(
            min_voltage_v=float(pem_params["minimum_usable_fuel_cell_voltage_V"]),
            min_hydrogen_ml=float(pem_params["minimum_hydrogen_level_for_discharge_mL"]),
            max_discharge_power_w=float(pem_sweep["max_power_W"]),
            full_hydrogen_ml=float(
                pd.to_numeric(pem_state["hydrogen_volume_mL"], errors="coerce").max()
            ),
        ),
        pv=PVLimits(
            min_voltage_v=float(pv_params["min_pv_voltage_V"]),
            max_power_w=float(pv_params["max_available_power_mW"]) / 1000.0,
            min_load_power_w=float(pv_params["min_usable_power_for_load_mW"]) / 1000.0,
            min_charging_power_w=float(
                pv_params["min_usable_power_for_charging_mW"]
            )
            / 1000.0,
        ),
    )


def load_scaled_demand_profile(path: Path | str = DEMAND_PROFILE_PATH) -> list[float]:
    """Load the 96 slot demand profile and convert mW to W."""

    df = pd.read_csv(path)
    if "power_mW" not in df.columns:
        raise ValueError("Demand profile must contain a power_mW column.")
    return (df["power_mW"].astype(float) / 1000.0).tolist()


def decide_current_scenario(
    prices: Iterable[float],
    demand_profile: Iterable[float],
    current_slot: int,
    component_state: ComponentState,
    limits: EMSLimits | None = None,
    config: SchedulerConfig | None = None,
) -> dict:
    """Choose the scenario for the current accelerated demo slot."""

    limits = limits or load_limits()
    config = config or SchedulerConfig()

    prices_96 = _as_96_values(prices, "prices")
    demand_96 = _as_96_values(demand_profile, "demand_profile")

    price_now = prices_96[current_slot]
    demand_now_w = demand_96[current_slot]
    pv_now_w = estimate_live_pv_power_w(component_state, limits)
    price_state = classify_price(price_now, prices_96, config)

    # The battery reserve is based on upcoming expensive demand.
    reserve_soc = calculate_battery_reserve_soc(
        prices_96=prices_96,
        demand_96=demand_96,
        current_slot=current_slot,
        limits=limits,
        config=config,
    )

    eligible = get_eligible_scenarios(
        demand_w=demand_now_w,
        pv_w=pv_now_w,
        reserve_soc_percent=reserve_soc,
        component_state=component_state,
        limits=limits,
        config=config,
    )
    scenario, reason = choose_best_scenario(eligible, price_state)

    if (
        scenario != component_state.last_scenario
        and component_state.seconds_since_last_switch < config.min_switch_seconds
    ):
        scenario = 1
        reason = "minimum switching time, safe grid fallback"

    pem_hydrogen_ml = estimate_next_pem_hydrogen(
        scenario=scenario,
        demand_w=demand_now_w,
        pv_w=pv_now_w,
        pem_hydrogen_ml=component_state.pem_hydrogen_ml,
        limits=limits,
        config=config,
    )

    return {
        "slot": current_slot,
        "price": price_now,
        "price_state": price_state,
        "demand_w": demand_now_w,
        "live_pv_w": pv_now_w,
        "battery_reserve_soc_percent": reserve_soc,
        "pem_hydrogen_est_ml": pem_hydrogen_ml,
        "eligible_scenarios": sorted(eligible),
        "scenario": scenario,
        "scenario_label": f"S{scenario}",
        "scenario_description": SCENARIO_DESCRIPTIONS[scenario],
        "reason": reason,
        "command": build_scenario_command(current_slot, scenario, demand_now_w),
    }


def estimate_live_pv_power_w(
    component_state: ComponentState,
    limits: EMSLimits | None = None,
) -> float:
    """Estimate usable PV power from the live INA226 measurement."""

    limits = limits or load_limits()

    if component_state.pv_voltage_v < limits.pv.min_voltage_v:
        return 0.0

    if component_state.pv_power_w is not None:
        pv_w = component_state.pv_power_w
    else:
        pv_w = component_state.pv_voltage_v * component_state.pv_current_a

    return float(np.clip(pv_w, 0.0, limits.pv.max_power_w))


def classify_price(
    price: float,
    prices_96: list[float],
    config: SchedulerConfig,
) -> str:
    """Classify the current price compared with the daily price curve."""

    low = float(np.quantile(prices_96, config.price_low_quantile))
    high = float(np.quantile(prices_96, config.price_high_quantile))

    if np.isclose(low, high):
        return "medium"
    if price >= high:
        return "high"
    if price <= low:
        return "low"
    return "medium"


def calculate_battery_reserve_soc(
    *,
    prices_96: list[float],
    demand_96: list[float],
    current_slot: int,
    limits: EMSLimits,
    config: SchedulerConfig,
) -> float:
    """Reserve battery energy for expensive slots later in the demo day."""

    high_price = float(np.quantile(prices_96, config.price_high_quantile))
    end_slot = min(96, current_slot + config.lookahead_slots + 1)

    future_expensive_load_wh = 0.0
    for slot in range(current_slot + 1, end_slot):
        if prices_96[slot] >= high_price:
            future_expensive_load_wh += demand_96[slot] * config.simulated_slot_hours

    reserve_from_lookahead = (
        100.0 * future_expensive_load_wh / limits.battery.usable_energy_wh
    )

    return float(
        np.clip(
            max(limits.battery.reserve_soc_percent, reserve_from_lookahead),
            limits.battery.reserve_soc_percent,
            limits.battery.full_soc_percent,
        )
    )


def get_eligible_scenarios(
    *,
    demand_w: float,
    pv_w: float,
    reserve_soc_percent: float,
    component_state: ComponentState,
    limits: EMSLimits,
    config: SchedulerConfig,
) -> set[int]:
    """Find the scenarios that are allowed by the measured component limits."""

    eligible = {1}

    pv_can_feed_load = (
        pv_w >= limits.pv.min_load_power_w
        and pv_w >= demand_w + config.safety_margin_w
    )
    pv_can_charge = pv_w >= limits.pv.min_charging_power_w

    if pv_can_feed_load:
        eligible.add(4)

    if pv_can_charge and component_state.battery_soc_percent < limits.battery.full_soc_percent:
        eligible.add(2)

    if pv_can_charge and component_state.pem_hydrogen_ml < limits.pem.full_hydrogen_ml:
        eligible.add(3)

    battery_can_discharge = (
        component_state.battery_voltage_v >= limits.battery.min_voltage_v
        and component_state.battery_soc_percent > reserve_soc_percent
        and demand_w <= limits.battery.max_discharge_power_w + config.safety_margin_w
    )
    if battery_can_discharge:
        eligible.add(5)

    pem_can_discharge = (
        component_state.pem_voltage_v >= limits.pem.min_voltage_v
        and component_state.pem_hydrogen_ml >= limits.pem.min_hydrogen_ml
        and demand_w <= limits.pem.max_discharge_power_w
    )
    if pem_can_discharge:
        eligible.add(6)

    return eligible


def choose_best_scenario(eligible: set[int], price_state: str) -> tuple[int, str]:
    """Choose one scenario from the safe candidates."""

    if price_state == "high":
        priority = [
            (4, "high price: use live PV if it can cover load"),
            (5, "high price: use battery while reserve allows it"),
            (6, "high price: use PEM for small loads"),
            (1, "high price: no local source can safely cover load"),
        ]
    elif price_state == "low":
        priority = [
            (2, "low price: grid supplies load while PV charges battery"),
            (3, "low price: battery is not priority, PV charges PEM"),
            (4, "low price: PV can cover load directly"),
            (1, "low price: grid fallback"),
        ]
    else:
        priority = [
            (4, "medium price: use PV directly if available"),
            (1, "medium price: save stored energy"),
        ]

    for scenario, reason in priority:
        if scenario in eligible:
            return scenario, reason

    return 1, "no safe local scenario, grid fallback"


def estimate_next_pem_hydrogen(
    *,
    scenario: int,
    demand_w: float,
    pv_w: float,
    pem_hydrogen_ml: float,
    limits: EMSLimits,
    config: SchedulerConfig,
) -> float:
    """Update the PEM estimate for the next scheduler decision."""

    next_hydrogen = pem_hydrogen_ml

    if scenario == 3:
        # From the PEM tests, electrolysis gave roughly 0.08 mL hydrogen per J.
        next_hydrogen += pv_w * config.simulated_slot_hours * 3600.0 * 0.08

    if scenario == 6:
        # Full PEM test: about 6 mL gave roughly 14 J of usable output.
        output_j = demand_w * config.simulated_slot_hours * 3600.0
        next_hydrogen -= output_j / 14.0 * 6.0

    return float(np.clip(next_hydrogen, 0.0, limits.pem.full_hydrogen_ml))


def build_scenario_command(slot: int, scenario: int, demand_w: float) -> str:
    """Command frame sent from Python to the Arduino sketch."""

    demand_mw = int(round(demand_w * 1000.0))
    return f"SCENARIO,{int(slot)},{int(scenario)},{demand_mw}"


def _as_96_values(values: Iterable[float], name: str) -> list[float]:
    values = [float(value) for value in values]

    if len(values) == 24:
        values = [value for value in values for _ in range(4)]

    if len(values) != 96:
        raise ValueError(f"{name} must contain 24 or 96 values, got {len(values)}.")

    return values
