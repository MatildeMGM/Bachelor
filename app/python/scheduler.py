from __future__ import annotations

"""Simple rule based EMS scheduler.

The scheduler only decides a target scenario. The Arduino sketch performs the
final safety check before changing relay states.
"""

import csv
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from ems.ems_limits import DEFAULT_LIMITS, EMSLimits


APP_PYTHON_DIR = Path(__file__).resolve().parent
DEMAND_PROFILE_PATH = (
    APP_PYTHON_DIR
    / "data"
    / "variable_load_signal"
    / "scaled_may_power_profile_15min.csv"
)

SCENARIO_DESCRIPTIONS = {
    1: "Grid supplies load.",
    2: "PV charges battery while grid supplies load.",
    3: "PV charges PEM while grid supplies load.",
    4: "PV supplies load.",
    5: "Battery supplies load.",
    6: "PEM supplies load.",
}


@dataclass(frozen=True)
class SchedulerConfig:
    """Small compatibility object for the existing bridge command builder."""

    safety_margin_mW: float = DEFAULT_LIMITS.safety.safety_margin_mW

    @property
    def safety_margin_w(self) -> float:
        return self.safety_margin_mW / 1000.0


@dataclass
class ComponentState:
    pv_voltage_V: float = 0.0
    pv_current_mA: float = 0.0
    battery_voltage_V: float = 0.0
    battery_current_mA: float = 0.0
    pem_voltage_V: float = 0.0
    pem_current_mA: float = 0.0
    load_voltage_V: float = 0.0
    load_current_mA: float = 0.0
    battery_soc_percent: float | None = None

    pv_power_mW: float = 0.0
    battery_power_mW: float = 0.0
    pem_power_mW: float = 0.0
    load_power_mW: float = 0.0

    pv_available: bool = False
    battery_can_discharge: bool = False
    battery_can_charge: bool = False
    pem_can_discharge: bool = False
    pem_can_charge: bool = False
    load_demand_mW: float = 0.0

    # These are convenience checks used by the scenario functions.
    pv_can_supply_load: bool = False
    pv_can_charge: bool = False


def load_limits() -> EMSLimits:
    """Return the editable EMS limits used by the rule based scheduler."""

    return DEFAULT_LIMITS


def load_demand_profile(path: str | Path = DEMAND_PROFILE_PATH) -> list[float]:
    """Load 96 demand values in mW from the scaled demand profile CSV."""

    demand_path = Path(path)
    values: list[float] = []

    with demand_path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        if "power_mW" not in (reader.fieldnames or []):
            raise ValueError("Demand profile must contain a power_mW column.")

        for row in reader:
            values.append(float(row["power_mW"]))

    if len(values) != 96:
        raise ValueError(f"Demand profile must contain 96 values, got {len(values)}.")

    return values


def load_scaled_demand_profile(path: str | Path = DEMAND_PROFILE_PATH) -> list[float]:
    """Existing app helper: load demand values and convert mW to W."""

    return [value_mW / 1000.0 for value_mW in load_demand_profile(path)]


def get_current_slot(now: datetime | None = None) -> int:
    """Return the current 15 minute slot, from 0 to 95."""

    current = now or datetime.now()
    return current.hour * 4 + current.minute // 15


def classify_price(price_DKK_per_kWh: float, limits: EMSLimits) -> str:
    """Return high or low from one price threshold."""

    if price_DKK_per_kWh >= limits.price.high_price_min_DKK_per_kWh:
        return "high"
    return "low"


def build_component_state(
    status: dict | ComponentState,
    demand_mW: float,
    limits: EMSLimits,
) -> ComponentState:
    """Convert Arduino status values into simple measured component state."""

    if isinstance(status, ComponentState):
        status = asdict(status)

    pv_voltage = _value(status, ["pv_voltage_V", "panelVoltage", "pvVoltage"])
    pv_current = _current_mA(status, ["pv_current_mA"], ["PVcurrent", "pv_current_A"])
    battery_voltage = _value(status, ["battery_voltage_V", "batteryVoltage"])
    battery_current = _current_mA(
        status,
        ["battery_current_mA"],
        ["Batcurrent", "battery_current_A"],
    )
    pem_voltage = _value(status, ["pem_voltage_V", "pemrfcVoltage", "pemVoltage"])
    pem_current = _current_mA(status, ["pem_current_mA"], ["PEMcurrent", "pem_current_A"])
    load_voltage = _value(status, ["load_voltage_V", "loadVoltage"])
    load_current = _current_mA(status, ["load_current_mA"], ["Loadcurrent", "load_current_A"])

    pv_power = _power_mW(status, ["pv_power_mW"], ["PVpower"], pv_voltage, pv_current)
    battery_power = _power_mW(
        status,
        ["battery_power_mW"],
        ["Batterypower"],
        battery_voltage,
        battery_current,
    )
    pem_power = _power_mW(status, ["pem_power_mW"], ["PEMpower"], pem_voltage, pem_current)
    load_power = _power_mW(status, ["load_power_mW"], ["Loadpower"], load_voltage, load_current)

    battery_soc = _optional_value(status, ["batterySOC", "battery_soc_percent"])

    pv_available = (
        pv_voltage >= limits.pv.min_voltage_for_use_V
        and pv_current >= limits.pv.min_current_out_mA
    )

    # PV current and power can be close to zero when the panel is open-circuit.
    # The scheduler therefore uses voltage and characterised power limits for
    # pre-selection. Arduino validates loaded PV power after switching.
    pv_can_supply_load = (
        pv_available
        and demand_mW <= limits.pv.min_power_for_load_mW
    )
    pv_can_charge = pv_available

    battery_can_discharge = (
        battery_voltage >= limits.battery.min_voltage_discharge_V
        and demand_mW <= limits.battery.min_power_for_load_mW
        and _soc_above_low_limit(battery_soc, limits)
    )
    battery_can_charge = (
        battery_voltage < limits.battery.max_voltage_charge_V
        and abs(battery_current) <= limits.battery.max_charge_current_mA
        and _soc_below_full_limit(battery_soc, limits)
    )

    pem_can_discharge = (
        pem_voltage >= limits.pem.min_voltage_discharge_V
        and demand_mW <= limits.pem.min_power_for_load_mW
    )
    pem_can_charge = (
        pem_voltage < limits.pem.max_voltage_charge_V
        and abs(pem_current) <= limits.pem.max_charge_current_mA
    )

    return ComponentState(
        pv_voltage_V=pv_voltage,
        pv_current_mA=pv_current,
        battery_voltage_V=battery_voltage,
        battery_current_mA=battery_current,
        pem_voltage_V=pem_voltage,
        pem_current_mA=pem_current,
        load_voltage_V=load_voltage,
        load_current_mA=load_current,
        battery_soc_percent=battery_soc,
        pv_power_mW=pv_power,
        battery_power_mW=battery_power,
        pem_power_mW=pem_power,
        load_power_mW=load_power,
        pv_available=pv_available,
        battery_can_discharge=battery_can_discharge,
        battery_can_charge=battery_can_charge,
        pem_can_discharge=pem_can_discharge,
        pem_can_charge=pem_can_charge,
        load_demand_mW=demand_mW,
        pv_can_supply_load=pv_can_supply_load,
        pv_can_charge=pv_can_charge,
    )


def is_s4_eligible(state: ComponentState) -> bool:
    """S4 is eligible when PV can supply the current demand."""

    return state.pv_can_supply_load


def is_s5_eligible(state: ComponentState) -> bool:
    """S5 is eligible when the battery can supply the current demand."""

    return state.battery_can_discharge


def is_s6_eligible(state: ComponentState) -> bool:
    """S6 is eligible when the PEM can supply the current demand."""

    return state.pem_can_discharge


def is_s2_eligible(state: ComponentState) -> bool:
    """S2 is eligible when PV can charge the battery while grid supplies load."""

    return state.pv_can_charge and state.battery_can_charge


def is_s3_eligible(state: ComponentState) -> bool:
    """S3 is eligible when PV can charge the PEM while grid supplies load."""

    return state.pv_can_charge and state.pem_can_charge


def decide_current_scenario(
    price: float,
    demand_mW: float,
    status: dict | ComponentState,
    limits: EMSLimits | None = None,
) -> str:
    """Choose S1-S6 using the required high/low price priority rules."""

    limits = limits or load_limits()
    price_mode = classify_price(price, limits)
    state = build_component_state(status, demand_mW, limits)

    if price_mode == "high":
        if is_s4_eligible(state):
            return "S4"
        if is_s5_eligible(state):
            return "S5"
        if is_s6_eligible(state):
            return "S6"
        return "S1"

    if is_s2_eligible(state):
        return "S2"
    if is_s3_eligible(state):
        return "S3"
    if is_s4_eligible(state):
        return "S4"
    return "S1"


def decide_slot_scenario(
    *,
    prices: Iterable[float],
    demand_profile: Iterable[float],
    current_slot: int,
    status: dict,
    limits: EMSLimits | None = None,
    config: SchedulerConfig | None = None,
) -> dict:
    """App-facing wrapper that returns telemetry and the Arduino command."""

    limits = limits or load_limits()
    config = config or SchedulerConfig()
    prices_96 = _as_96_values(prices, "prices")
    demand_96_w = _as_96_values(demand_profile, "demand_profile")

    price = prices_96[current_slot]
    demand_mW = demand_96_w[current_slot] * 1000.0
    state = build_component_state(status, demand_mW, limits)
    scenario_label = decide_current_scenario(price, demand_mW, state, limits)
    scenario = int(scenario_label[1:])
    price_mode = classify_price(price, limits)

    return {
        "slot": current_slot,
        "price": price,
        "price_mode": price_mode,
        "price_threshold_dkk_kwh": limits.price.high_price_min_DKK_per_kWh,
        "demand_w": demand_mW / 1000.0,
        "demand_mW": demand_mW,
        "component_state": asdict(state),
        "threshold_checks": {
            "pv_can_charge_battery": is_s2_eligible(state),
            "pv_can_charge_pem": is_s3_eligible(state),
            "pv_can_supply_load": is_s4_eligible(state),
            "battery_can_supply_load": is_s5_eligible(state),
            "pem_can_supply_load": is_s6_eligible(state),
        },
        "eligible_scenarios": _eligible_scenarios(state),
        "scenario": scenario,
        "scenario_label": scenario_label,
        "scenario_description": SCENARIO_DESCRIPTIONS[scenario],
        "reason": _scenario_reason(scenario_label, price_mode),
        "live_pv_w": state.pv_power_mW / 1000.0,
        "command": build_scenario_command(
            current_slot,
            scenario,
            demand_mW,
            limits,
            config,
        ),
    }


def build_scenario_command(
    slot: int,
    scenario: int,
    demand_mW: float,
    limits: EMSLimits,
    config: SchedulerConfig,
) -> str:
    """Command frame sent from Python to the Arduino sketch."""

    return (
        f"SCENARIO,{int(slot)},{int(scenario)},{int(round(demand_mW))},"
        f"{limits.pv.min_voltage_for_use_V:.5f},"
        f"{limits.pv.min_power_for_charging_mW:.1f},"
        f"{limits.pv.min_voltage_for_use_V:.5f},"
        f"{limits.pv.min_power_for_charging_mW:.1f},"
        f"{limits.pv.min_voltage_for_use_V:.5f},"
        f"{limits.pv.min_power_for_load_mW:.1f},"
        f"{config.safety_margin_mW:.1f}"
    )


def build_config_command(limits: EMSLimits, config: SchedulerConfig) -> str:
    """Configuration frame that keeps Arduino safety checks aligned with Python."""

    return (
        "CONFIG,"
        f"{limits.battery.min_voltage_discharge_V:.5f},"
        f"{limits.battery.max_voltage_charge_V:.5f},"
        f"{limits.battery.min_voltage_discharge_V:.5f},"
        f"{limits.battery.max_voltage_charge_V:.5f},"
        f"{limits.battery.usable_energy_Wh * 1000.0:.3f},"
        f"{limits.battery.low_soc_percent:.2f},"
        f"{limits.battery.full_soc_percent:.2f},"
        f"{limits.battery.min_power_for_load_mW:.3f},"
        f"{limits.pem.min_voltage_discharge_V:.5f},"
        f"{limits.pem.min_power_for_load_mW:.3f},"
        f"{config.safety_margin_mW:.3f}"
    )


def run_demo() -> None:
    """Small scheduler demo that does not require Arduino hardware."""

    limits = load_limits()
    slot = get_current_slot()
    prices = [0.25] * 96
    prices[slot] = 1.00
    demand = load_demand_profile()
    status = {
        "pv_voltage_V": 5.0,
        "pv_current_mA": 20.0,
        "battery_voltage_V": 3.8,
        "battery_current_mA": 0.0,
        "pem_voltage_V": 0.8,
        "pem_current_mA": 0.0,
        "load_voltage_V": 5.0,
        "load_current_mA": 10.0,
        "batterySOC": 70.0,
    }

    price = prices[slot]
    demand_mW = demand[slot]
    state = build_component_state(status, demand_mW, limits)
    scenario = decide_current_scenario(price, demand_mW, state, limits)

    print("slot:", slot)
    print("price:", price)
    print("demand_mW:", round(demand_mW, 2))
    print("component_state:", asdict(state))
    print("chosen_scenario:", scenario)


def _eligible_scenarios(state: ComponentState) -> list[int]:
    eligible = [1]
    if is_s2_eligible(state):
        eligible.append(2)
    if is_s3_eligible(state):
        eligible.append(3)
    if is_s4_eligible(state):
        eligible.append(4)
    if is_s5_eligible(state):
        eligible.append(5)
    if is_s6_eligible(state):
        eligible.append(6)
    return eligible


def _scenario_reason(scenario: str, price_mode: str) -> str:
    reasons = {
        "S1": f"{price_mode} price: no higher-priority eligible source, use grid fallback",
        "S2": "low price, PV and battery charging path eligible",
        "S3": "low price, PV and PEM charging path eligible",
        "S4": f"{price_mode} price, PV load supply path eligible",
        "S5": "high price, battery load supply path eligible",
        "S6": "high price, PEM load supply path eligible",
    }
    return reasons.get(scenario, "grid fallback")


def _as_96_values(values: Iterable[float], name: str) -> list[float]:
    result = [float(value) for value in values]
    if len(result) == 24:
        result = [value for value in result for _ in range(4)]
    if len(result) != 96:
        raise ValueError(f"{name} must contain 24 or 96 values, got {len(result)}.")
    return result


def _value(status: dict, keys: list[str], default: float = 0.0) -> float:
    for key in keys:
        if key in status and status[key] not in [None, ""]:
            return float(status[key])
    return default


def _optional_value(status: dict, keys: list[str]) -> float | None:
    for key in keys:
        if key in status and status[key] not in [None, ""]:
            return float(status[key])
    return None


def _current_mA(status: dict, mA_keys: list[str], ampere_keys: list[str]) -> float:
    for key in mA_keys:
        if key in status and status[key] not in [None, ""]:
            return float(status[key])
    for key in ampere_keys:
        if key in status and status[key] not in [None, ""]:
            return float(status[key]) * 1000.0
    return 0.0


def _power_mW(
    status: dict,
    mW_keys: list[str],
    watt_keys: list[str],
    voltage_V: float,
    current_mA: float,
) -> float:
    for key in mW_keys:
        if key in status and status[key] not in [None, ""]:
            return float(status[key])
    for key in watt_keys:
        if key in status and status[key] not in [None, ""]:
            return float(status[key]) * 1000.0
    return voltage_V * current_mA


def _soc_above_low_limit(soc: float | None, limits: EMSLimits) -> bool:
    if soc is None:
        return True
    return soc > limits.battery.low_soc_percent


def _soc_below_full_limit(soc: float | None, limits: EMSLimits) -> bool:
    if soc is None:
        return True
    return soc < limits.battery.full_soc_percent


if __name__ == "__main__":
    run_demo()
