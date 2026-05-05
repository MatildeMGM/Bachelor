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


APP_PYTHON_DIR = Path(__file__).resolve().parent
APP_DATA_DIR = APP_PYTHON_DIR / "data"
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
    medium_soc_percent: float
    high_soc_percent: float
    reserve_soc_percent: float = 20.0
    full_soc_percent: float = 90.0


@dataclass(frozen=True)
class PEMLimits:
    min_voltage_v: float
    min_hydrogen_ml: float
    max_discharge_power_w: float
    full_hydrogen_ml: float
    medium_hydrogen_ml: float
    high_hydrogen_ml: float
    hydrogen_production_mL_per_input_j: float
    hydrogen_consumption_mL_per_output_j: float
    startup_delay_s: float


@dataclass(frozen=True)
class PVLimits:
    min_voltage_v: float
    max_power_w: float
    min_load_power_w: float
    min_charging_power_w: float
    medium_power_w: float
    high_power_w: float


@dataclass(frozen=True)
class EMSLimits:
    battery: BatteryLimits
    pem: PEMLimits
    pv: PVLimits


@dataclass(frozen=True)
class EMSInputStates:
    price: str
    demand: str
    pv: str
    battery: str
    pem: str


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


def load_limits(data_dir: Path | str = APP_DATA_DIR) -> EMSLimits:
    """Load the operating limits found during data processing."""

    base = Path(data_dir)

    battery_state = pd.read_csv(base / "processed_Battery" / "battery_state_table.csv")
    battery_discharge = pd.read_csv(
        base / "processed_Battery" / "battery_discharge_summary.csv"
    ).iloc[0]

    pem_params = pd.read_csv(base / "processed_PEM" / "pem_control_parameters.csv").iloc[0]
    pem_state = pd.read_csv(base / "processed_PEM" / "pem_state_table.csv")
    pem_sweep = pd.read_csv(base / "processed_PEM" / "current_sweep_summary.csv").iloc[0]

    pv_params = pd.read_csv(base / "processed_PV" / "pv_control_parameters.csv").iloc[0]
    pv_state = pd.read_csv(base / "processed_PV" / "pv_state_table.csv")

    battery_medium_soc = _state_min(
        battery_state,
        state_column="ems_state",
        state_value="MEDIUM",
        value_column="soc_min_percent",
        default=40.0,
    )
    battery_high_soc = _state_min(
        battery_state,
        state_column="ems_state",
        state_value="HIGH",
        value_column="soc_min_percent",
        default=60.0,
    )
    pem_medium_hydrogen = _state_min(
        pem_state,
        state_column="ems_state",
        state_value="MEDIUM",
        value_column="hydrogen_volume_mL",
        default=float(pem_params["minimum_hydrogen_level_for_discharge_mL"]),
    )
    pem_high_hydrogen = _state_min(
        pem_state,
        state_column="ems_state",
        state_value="HIGH",
        value_column="hydrogen_volume_mL",
        default=0.65 * float(pd.to_numeric(pem_state["hydrogen_volume_mL"], errors="coerce").max()),
    )
    pv_medium_power_w = _state_min(
        pv_state,
        state_column="ems_state",
        state_value="MEDIUM",
        value_column="avg_power_mW",
        default=float(pv_params["min_usable_power_for_charging_mW"]),
    ) / 1000.0
    pv_high_power_w = _state_min(
        pv_state,
        state_column="ems_state",
        state_value="HIGH",
        value_column="avg_power_mW",
        default=float(pv_params["min_usable_power_for_load_mW"]),
    ) / 1000.0
    pem_hydrogen_production = pd.to_numeric(
        pem_params.get("hydrogen_production_mL_per_input_J", 0.08),
        errors="coerce",
    )
    pem_hydrogen_consumption = pd.to_numeric(
        pem_params.get("hydrogen_consumption_mL_per_output_J", 6.0 / 14.0),
        errors="coerce",
    )
    pem_startup_delay = pd.to_numeric(
        pem_params.get("pem_startup_delay_s", 2.0),
        errors="coerce",
    )

    return EMSLimits(
        battery=BatteryLimits(
            min_voltage_v=float(battery_state["voltage_min_V"].min()),
            full_voltage_v=4.2,
            usable_energy_wh=float(battery_discharge["usable_energy_Wh"]),
            max_discharge_power_w=float(battery_discharge["max_discharge_power_W"]),
            medium_soc_percent=battery_medium_soc,
            high_soc_percent=battery_high_soc,
        ),
        pem=PEMLimits(
            min_voltage_v=float(pem_params["minimum_usable_fuel_cell_voltage_V"]),
            min_hydrogen_ml=float(pem_params["minimum_hydrogen_level_for_discharge_mL"]),
            max_discharge_power_w=float(pem_params["maximum_usable_discharge_power_W"]),
            full_hydrogen_ml=float(
                pd.to_numeric(pem_state["hydrogen_volume_mL"], errors="coerce").max()
            ),
            medium_hydrogen_ml=pem_medium_hydrogen,
            high_hydrogen_ml=pem_high_hydrogen,
            hydrogen_production_mL_per_input_j=float(
                0.08 if pd.isna(pem_hydrogen_production) else pem_hydrogen_production
            ),
            hydrogen_consumption_mL_per_output_j=float(
                (6.0 / 14.0)
                if pd.isna(pem_hydrogen_consumption)
                else pem_hydrogen_consumption
            ),
            startup_delay_s=float(2.0 if pd.isna(pem_startup_delay) else pem_startup_delay),
        ),
        pv=PVLimits(
            min_voltage_v=float(pv_params["min_pv_voltage_V"]),
            max_power_w=float(pv_params["max_available_power_mW"]) / 1000.0,
            min_load_power_w=float(pv_params["min_usable_power_for_load_mW"]) / 1000.0,
            min_charging_power_w=float(
                pv_params["min_usable_power_for_charging_mW"]
            )
            / 1000.0,
            medium_power_w=pv_medium_power_w,
            high_power_w=pv_high_power_w,
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

    # The battery reserve is based on upcoming expensive demand.
    reserve_soc = calculate_battery_reserve_soc(
        prices_96=prices_96,
        demand_96=demand_96,
        current_slot=current_slot,
        limits=limits,
        config=config,
    )
    input_states = classify_inputs(
        price_now=price_now,
        prices_96=prices_96,
        demand_now_w=demand_now_w,
        demand_96=demand_96,
        pv_w=pv_now_w,
        reserve_soc_percent=reserve_soc,
        component_state=component_state,
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
    scenario, reason = choose_best_scenario(eligible, input_states)

    required_switch_delay_s = get_required_switch_delay_s(
        current_scenario=component_state.last_scenario,
        next_scenario=scenario,
        limits=limits,
        config=config,
    )
    if (
        scenario != component_state.last_scenario
        and component_state.seconds_since_last_switch < required_switch_delay_s
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
        "price_state": input_states.price,
        "demand_state": input_states.demand,
        "pv_state": input_states.pv,
        "battery_state": input_states.battery,
        "pem_state": input_states.pem,
        "input_states": {
            "price": input_states.price,
            "demand": input_states.demand,
            "pv": input_states.pv,
            "battery": input_states.battery,
            "pem": input_states.pem,
        },
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


def classify_inputs(
    *,
    price_now: float,
    prices_96: list[float],
    demand_now_w: float,
    demand_96: list[float],
    pv_w: float,
    reserve_soc_percent: float,
    component_state: ComponentState,
    limits: EMSLimits,
    config: SchedulerConfig,
) -> EMSInputStates:
    """Convert all scheduler inputs into the same low/medium/high language."""

    return EMSInputStates(
        price=classify_price(price_now, prices_96, config),
        demand=classify_demand(demand_now_w, demand_96),
        pv=classify_pv(pv_w, demand_now_w, limits, config),
        battery=classify_battery(component_state, reserve_soc_percent, limits),
        pem=classify_pem(component_state, limits),
    )


def classify_demand(demand_w: float, demand_96: list[float]) -> str:
    """Classify demand compared with the daily load profile."""

    low = float(np.quantile(demand_96, 0.35))
    high = float(np.quantile(demand_96, 0.70))
    return _low_medium_high(demand_w, low, high)


def classify_pv(
    pv_w: float,
    demand_w: float,
    limits: EMSLimits,
    config: SchedulerConfig,
) -> str:
    """Classify live PV availability from the measured PV power."""

    if pv_w < limits.pv.min_charging_power_w:
        return "low"
    if pv_w < max(limits.pv.high_power_w, demand_w + config.safety_margin_w):
        return "medium"
    return "high"


def classify_battery(
    component_state: ComponentState,
    reserve_soc_percent: float,
    limits: EMSLimits,
) -> str:
    """Classify battery availability while keeping the reserve as low state."""

    if (
        component_state.battery_voltage_v < limits.battery.min_voltage_v
        or component_state.battery_soc_percent <= reserve_soc_percent
    ):
        return "low"

    if component_state.battery_soc_percent >= limits.battery.high_soc_percent:
        return "high"
    return "medium"


def classify_pem(component_state: ComponentState, limits: EMSLimits) -> str:
    """Classify estimated PEM hydrogen availability."""

    if (
        component_state.pem_voltage_v < limits.pem.min_voltage_v
        or component_state.pem_hydrogen_ml < limits.pem.min_hydrogen_ml
    ):
        return "low"

    if component_state.pem_hydrogen_ml >= limits.pem.high_hydrogen_ml:
        return "high"
    return "medium"


def _low_medium_high(value: float, low_limit: float, high_limit: float) -> str:
    if np.isclose(low_limit, high_limit):
        return "medium"
    if value <= low_limit:
        return "low"
    if value >= high_limit:
        return "high"
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


def choose_best_scenario(
    eligible: set[int],
    input_states: EMSInputStates,
) -> tuple[int, str]:
    """Choose one scenario from the safe candidates."""

    if input_states.price == "high":
        priority = [
            (4, "high price, PV available: use live PV for the load"),
            (5, "high price, battery available: discharge battery"),
            (6, "high price, PEM available: use PEM for small load"),
            (1, "high price, local sources low: safe grid fallback"),
        ]
    elif input_states.price == "low":
        priority = [
            (2, "low price, PV available: grid supplies load while PV charges battery"),
            (3, "low price, battery not charging: PV charges PEM"),
            (4, "low price, PV available: PV can cover load directly"),
            (1, "low price: safe grid fallback"),
        ]
    else:
        priority = [
            (4, "medium price, PV available: use PV directly"),
            (1, "medium price: save stored energy"),
        ]

    for scenario, reason in priority:
        if scenario in eligible:
            return scenario, reason

    return 1, "no safe local scenario, grid fallback"


def get_required_switch_delay_s(
    *,
    current_scenario: int,
    next_scenario: int,
    limits: EMSLimits,
    config: SchedulerConfig,
) -> float:
    delay_s = config.min_switch_seconds

    if 6 in {current_scenario, next_scenario}:
        delay_s = max(delay_s, limits.pem.startup_delay_s)

    return float(delay_s)


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
        next_hydrogen += (
            pv_w
            * config.simulated_slot_hours
            * 3600.0
            * limits.pem.hydrogen_production_mL_per_input_j
        )

    if scenario == 6:
        output_j = demand_w * config.simulated_slot_hours * 3600.0
        next_hydrogen -= (
            output_j * limits.pem.hydrogen_consumption_mL_per_output_j
        )

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


def _state_min(
    table: pd.DataFrame,
    *,
    state_column: str,
    state_value: str,
    value_column: str,
    default: float,
) -> float:
    if state_column not in table.columns or value_column not in table.columns:
        return float(default)

    rows = table[table[state_column].astype(str).str.upper() == state_value]
    values = pd.to_numeric(rows[value_column], errors="coerce").dropna()

    if values.empty:
        return float(default)

    return float(values.min())
