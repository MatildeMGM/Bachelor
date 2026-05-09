from __future__ import annotations

"""Simple rule based EMS scheduler for the bachelor EMS application.

The scheduler chooses one of six scenarios from electricity price, demand,
real time measurements and the estimated battery SOC. The Arduino performs
final physical checks before switching relays.
"""

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
import csv
from typing import Any, Iterable

try:
    from ems.ems_limits import EMS_LIMITS, EMSLimits
except ImportError:
    from pathlib import Path as _Path
    import sys as _sys

    _sys.path.append(str(_Path(__file__).resolve().parent))
    from ems.ems_limits import EMS_LIMITS, EMSLimits


APP_PYTHON_DIR = Path(__file__).resolve().parent
DEMAND_PROFILE_PATH = (
    APP_PYTHON_DIR
    / "data"
    / "variable_load_signal"
    / "scaled_may_power_profile_15min.csv"
)

SCENARIO_DESCRIPTIONS = {
    1: "S1: Grid supplies load. PV, battery and PEM are isolated.",
    2: "S2: PV charges battery while grid supplies load.",
    3: "S3: PV charges PEM while grid supplies load.",
    4: "S4: PV supplies load.",
    5: "S5: Battery supplies load.",
    6: "S6: PEM supplies load.",
}


@dataclass(frozen=True)
class SchedulerConfig:
    slot_minutes: int = 15


@dataclass
class ComponentState:
    pv_voltage_V: float = 0.0
    pv_current_mA: float = 0.0
    pv_power_mW: float = 0.0

    battery_voltage_V: float = 0.0
    battery_current_mA: float = 0.0
    battery_power_mW: float = 0.0
    battery_soc_percent: float = 0.0
    battery_energy_wh: float | None = None

    pem_voltage_V: float = 0.0
    pem_current_mA: float = 0.0
    pem_power_mW: float = 0.0
    pem_hydrogen_ml: float = 0.0

    load_voltage_V: float = 0.0
    load_current_mA: float = 0.0
    load_power_mW: float = 0.0
    load_demand_mW: float = 0.0

    pv_available: bool = False
    battery_can_discharge: bool = False
    battery_can_charge: bool = False
    pem_can_discharge: bool = False
    pem_can_charge: bool = False

    last_scenario: int = 1
    seconds_since_last_switch: float = 9999.0


@dataclass(frozen=True)
class EMSInputStates:
    price: str
    demand: str
    pv: str
    battery: str
    pem: str


def load_limits() -> EMSLimits:
    return EMS_LIMITS


def load_demand_profile(path: Path | str = DEMAND_PROFILE_PATH) -> list[float]:
    """Read 96 demand values from power_mW column."""

    path = Path(path)
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        if "power_mW" not in (reader.fieldnames or []):
            raise ValueError("Demand profile must contain a power_mW column.")
        values = [float(row["power_mW"]) for row in reader]

    if len(values) != 96:
        raise ValueError(f"Demand profile must contain 96 values, got {len(values)}.")

    return values


def load_scaled_demand_profile(path: Path | str = DEMAND_PROFILE_PATH) -> list[float]:
    """Compatibility wrapper used by ems_loop.py.

    The web app stores demand in W. The scheduler command sends mW.
    """

    return [value_mW / 1000.0 for value_mW in load_demand_profile(path)]


def get_current_slot(now: datetime | None = None) -> int:
    now = now or datetime.now()
    return now.hour * 4 + now.minute // 15


def classify_price(price_DKK_per_kWh: float, limits: EMSLimits = EMS_LIMITS) -> str:
    if price_DKK_per_kWh >= limits.price.high_price_min_DKK_per_kWh:
        return "high"
    return "low"


def estimate_battery_soc_from_voltage(
    battery_voltage_V: float,
    limits: EMSLimits = EMS_LIMITS,
) -> float:
    """Estimate initial battery SOC from the measured voltage SOC curve."""

    curve = limits.battery.voltage_soc_curve

    if battery_voltage_V <= curve[0][0]:
        return curve[0][1]

    if battery_voltage_V >= curve[-1][0]:
        return curve[-1][1]

    for index in range(len(curve) - 1):
        v_low, soc_low = curve[index]
        v_high, soc_high = curve[index + 1]

        if v_low <= battery_voltage_V <= v_high:
            fraction = (battery_voltage_V - v_low) / (v_high - v_low)
            return soc_low + fraction * (soc_high - soc_low)

    return 0.0


def build_component_state(
    status: dict[str, Any] | ComponentState,
    demand_mW: float,
    limits: EMSLimits = EMS_LIMITS,
) -> ComponentState:
    """Convert Arduino status measurements into scheduler state."""

    if isinstance(status, ComponentState):
        pv_voltage = status.pv_voltage_V
        pv_current = status.pv_current_mA
        pv_power = status.pv_power_mW
        battery_voltage = status.battery_voltage_V
        battery_current = status.battery_current_mA
        battery_power = status.battery_power_mW
        battery_soc = status.battery_soc_percent
        battery_energy_wh = status.battery_energy_wh
        pem_voltage = status.pem_voltage_V
        pem_current = status.pem_current_mA
        pem_power = status.pem_power_mW
        pem_hydrogen_ml = status.pem_hydrogen_ml
        load_voltage = status.load_voltage_V
        load_current = status.load_current_mA
        load_power = status.load_power_mW
        last_scenario = status.last_scenario
        seconds_since_last_switch = status.seconds_since_last_switch
    else:
        pv_voltage = _read_float(status, "pv_voltage_V", "panelVoltage")
        pv_current = _read_current_mA(status, "pv_current_mA", "PVcurrent")
        pv_power = _read_power_mW(status, "pv_power_mW", "PVpower", pv_voltage, pv_current)

        battery_voltage = _read_float(status, "battery_voltage_V", "batteryVoltage")
        battery_current = _read_current_mA(status, "battery_current_mA", "Batcurrent")
        battery_power = _read_power_mW(
            status, "battery_power_mW", "Batterypower", battery_voltage, battery_current
        )
        battery_soc = _read_float(status, "batterySOC", "battery_soc_percent", default=0.0)
        battery_energy_wh = _read_float(status, "batteryEnergyWh", default=0.0)

        pem_voltage = _read_float(status, "pem_voltage_V", "pemrfcVoltage")
        pem_current = _read_current_mA(status, "pem_current_mA", "PEMcurrent")
        pem_power = _read_power_mW(status, "pem_power_mW", "PEMpower", pem_voltage, pem_current)
        pem_hydrogen_ml = _read_float(status, "pem_hydrogen_ml", default=0.0)

        load_voltage = _read_float(status, "load_voltage_V", "loadVoltage")
        load_current = _read_current_mA(status, "load_current_mA", "Loadcurrent")
        load_power = _read_power_mW(status, "load_power_mW", "Loadpower", load_voltage, load_current)

        last_scenario = int(_read_float(status, "activeScenario", "scenario", default=1))
        seconds_since_last_switch = 9999.0

    demand = _clamp(float(demand_mW), limits.demand.min_demand_power_mW, limits.demand.max_demand_power_mW)

    pv_available = pv_voltage >= limits.pv.min_voltage_for_use_V

    battery_can_discharge = (
        battery_voltage >= limits.battery.min_voltage_discharge_V
        and battery_soc > limits.battery.min_soc_discharge_percent
        and demand <= limits.battery.max_load_power_mW
    )

    battery_can_charge = (
        battery_soc < limits.battery.full_soc_percent
        and battery_voltage < limits.battery.max_voltage_charge_control_V
    )

    pem_can_discharge = (
        pem_voltage >= limits.pem.min_voltage_discharge_V
        and demand <= limits.pem.max_attempted_load_power_mW
    )

    pem_can_charge = pem_voltage < limits.pem.max_voltage_charge_control_V

    return ComponentState(
        pv_voltage_V=pv_voltage,
        pv_current_mA=pv_current,
        pv_power_mW=max(0.0, pv_power),
        battery_voltage_V=battery_voltage,
        battery_current_mA=battery_current,
        battery_power_mW=battery_power,
        battery_soc_percent=battery_soc,
        battery_energy_wh=battery_energy_wh,
        pem_voltage_V=pem_voltage,
        pem_current_mA=pem_current,
        pem_power_mW=pem_power,
        pem_hydrogen_ml=pem_hydrogen_ml,
        load_voltage_V=load_voltage,
        load_current_mA=load_current,
        load_power_mW=load_power,
        load_demand_mW=demand,
        pv_available=pv_available,
        battery_can_discharge=battery_can_discharge,
        battery_can_charge=battery_can_charge,
        pem_can_discharge=pem_can_discharge,
        pem_can_charge=pem_can_charge,
        last_scenario=last_scenario,
        seconds_since_last_switch=seconds_since_last_switch,
    )


def is_s4_eligible(state: ComponentState, limits: EMSLimits = EMS_LIMITS) -> bool:
    return state.pv_available and state.load_demand_mW <= limits.pv.max_load_power_mW


def is_s5_eligible(state: ComponentState, limits: EMSLimits = EMS_LIMITS) -> bool:
    return state.battery_can_discharge


def is_s6_eligible(state: ComponentState, limits: EMSLimits = EMS_LIMITS) -> bool:
    return state.pem_can_discharge


def is_s2_eligible(state: ComponentState, limits: EMSLimits = EMS_LIMITS) -> bool:
    return state.pv_available and state.battery_can_charge


def is_s3_eligible(state: ComponentState, limits: EMSLimits = EMS_LIMITS) -> bool:
    return state.pv_available and state.pem_can_charge


def decide_current_scenario(
    price_DKK_per_kWh: float | None = None,
    demand_mW: float | None = None,
    status: dict[str, Any] | ComponentState | None = None,
    limits: EMSLimits | None = None,
    *,
    prices: Iterable[float] | None = None,
    demand_profile: Iterable[float] | None = None,
    current_slot: int | None = None,
    component_state: ComponentState | None = None,
    config: SchedulerConfig | None = None,
) -> dict[str, Any]:
    """Choose the current S1 to S6 scenario."""

    limits = limits or EMS_LIMITS
    config = config or SchedulerConfig()

    if prices is not None and demand_profile is not None and current_slot is not None:
        price_values = list(prices)
        demand_values_W = list(demand_profile)
        slot = int(current_slot) % 96
        price = float(price_values[slot])
        demand = float(demand_values_W[slot]) * 1000.0
        raw_status = component_state or status or {}
    else:
        slot = get_current_slot()
        price = float(price_DKK_per_kWh or 0.0)
        demand = float(demand_mW or 0.0)
        raw_status = status or component_state or {}

    state = build_component_state(raw_status, demand, limits)
    price_state = classify_price(price, limits)

    if price_state == "high":
        if is_s4_eligible(state, limits):
            scenario = 4
            reason = "High price: PV is above the voltage check and demand is within the PV demo limit."
        elif is_s5_eligible(state, limits):
            scenario = 5
            reason = "High price: battery SOC and voltage allow load supply."
        elif is_s6_eligible(state, limits):
            scenario = 6
            reason = "High price: PEM voltage allows a backup supply attempt."
        else:
            scenario = 1
            reason = "High price: no local source is available, grid fallback."
    else:
        if is_s2_eligible(state, limits):
            scenario = 2
            reason = "Low price: PV charges the battery while the grid supplies the load."
        elif is_s3_eligible(state, limits):
            scenario = 3
            reason = "Low price: battery is considered full, so PV charges the PEM."
        elif is_s4_eligible(state, limits):
            scenario = 4
            reason = "Low price: storage charging is not available, so PV supplies the load."
        else:
            scenario = 1
            reason = "Low price: no PV scenario is available, grid fallback."

    return {
        "slot": slot,
        "price": price,
        "price_state": price_state,
        "demand_state": "demand",
        "pv_state": "available" if state.pv_available else "not_available",
        "battery_state": "available" if state.battery_can_discharge else "not_available",
        "pem_state": "available" if state.pem_can_discharge else "not_available",
        "input_states": {
            "price": price_state,
            "demand": "demand",
            "pv": "available" if state.pv_available else "not_available",
            "battery": "available" if state.battery_can_discharge else "not_available",
            "pem": "available" if state.pem_can_discharge else "not_available",
        },
        "demand_w": state.load_demand_mW / 1000.0,
        "demand_mW": state.load_demand_mW,
        "component_state": asdict(state),
        "eligible_scenarios": _eligible_list(state, limits),
        "scenario": scenario,
        "scenario_label": f"S{scenario}",
        "scenario_description": SCENARIO_DESCRIPTIONS[scenario],
        "reason": reason,
        "command": build_scenario_command(slot, scenario, state.load_demand_mW),
    }


def build_scenario_command(slot: int, scenario: int, demand_mW: float) -> str:
    return f"SCENARIO,{int(slot)},{int(scenario)},{float(demand_mW):.1f}"


def _eligible_list(state: ComponentState, limits: EMSLimits) -> list[int]:
    eligible = [1]
    if is_s2_eligible(state, limits):
        eligible.append(2)
    if is_s3_eligible(state, limits):
        eligible.append(3)
    if is_s4_eligible(state, limits):
        eligible.append(4)
    if is_s5_eligible(state, limits):
        eligible.append(5)
    if is_s6_eligible(state, limits):
        eligible.append(6)
    return eligible


def _read_float(data: dict[str, Any], *names: str, default: float = 0.0) -> float:
    for name in names:
        if name in data:
            try:
                return float(data[name])
            except (TypeError, ValueError):
                return default
    return default


def _read_current_mA(data: dict[str, Any], mA_name: str, A_name: str) -> float:
    if mA_name in data:
        return _read_float(data, mA_name)
    return 1000.0 * _read_float(data, A_name)


def _read_power_mW(
    data: dict[str, Any],
    mW_name: str,
    W_name: str,
    voltage_V: float,
    current_mA: float,
) -> float:
    if mW_name in data:
        return _read_float(data, mW_name)
    if W_name in data:
        return 1000.0 * _read_float(data, W_name)
    return voltage_V * current_mA


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


if __name__ == "__main__":
    demo_prices = [0.20] * 48 + [1.10] * 48
    demo_demand_W = [0.050] * 96
    fake_status = {
        "panelVoltage": 4.10,
        "PVcurrent": 0.0,
        "PVpower": 0.0,
        "batteryVoltage": 3.85,
        "Batcurrent": 0.0,
        "batterySOC": 80.0,
        "pemrfcVoltage": 0.70,
        "PEMcurrent": 0.0,
        "loadVoltage": 0.0,
        "Loadcurrent": 0.0,
    }

    decision = decide_current_scenario(
        prices=demo_prices,
        demand_profile=demo_demand_W,
        current_slot=10,
        component_state=build_component_state(fake_status, demand_mW=50.0),
    )

    print("slot:", decision["slot"])
    print("price:", decision["price"])
    print("demand_mW:", decision["demand_mW"])
    print("component_state:", decision["component_state"])
    print("chosen scenario:", decision["scenario_label"])
    print("command:", decision["command"])
