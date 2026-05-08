"""Editable EMS operating limits.

These values are deliberately collected in one small file so they are easy to
show in the bachelor report and easy to replace with experimentally derived
thresholds from component characterisation.
"""

from dataclasses import dataclass, field

from parameters import get_parameter


def _p(name: str, default: float) -> float:
    return get_parameter(name, default)


def _mw_from_w(name: str, default_w: float) -> float:
    return 1000.0 * _p(name, default_w)


@dataclass(frozen=True)
class PriceLimits:
    # One threshold is used: below it is low price, at/above it is high price.
    low_price_max_DKK_per_kWh: float = _p("PRICE_LIMITS.high_price_min_DKK_per_kWh", 0.6231)
    high_price_min_DKK_per_kWh: float = _p("PRICE_LIMITS.high_price_min_DKK_per_kWh", 0.6231)


@dataclass(frozen=True)
class PVLimits:
    # Replace with PV characterisation values from the final lab setup.
    min_voltage_for_use_V: float = _p("PV_MIN_LOAD_SUPPLY_VOLTAGE", 4.2812)
    min_power_for_load_mW: float = _mw_from_w("PV_MIN_LOAD_SUPPLY_POWER_W", 0.100)
    min_power_for_charging_mW: float = _mw_from_w("PV_MIN_BATTERY_CHARGING_POWER_W", 0.020)
    min_current_out_mA: float = 0.0


@dataclass(frozen=True)
class BatteryLimits:
    # Replace with battery voltage/current/power limits from tests and datasheet.
    min_voltage_discharge_V: float = _p("BATTERY_MIN_VOLTAGE", 3.0)
    max_voltage_charge_V: float = _p("BATTERY_FULL_VOLTAGE", 4.2)
    min_current_discharge_mA: float = 0.0
    max_charge_current_mA: float = 1000.0
    min_power_for_load_mW: float = _mw_from_w("BATTERY_MAX_DISCHARGE_POWER_W", 0.100)
    usable_energy_Wh: float = _p("EMS_BATTERY_CAPACITY_MILLIWATT_HOUR", 100.0) / 1000.0
    low_soc_percent: float = _p("BATTERY_LOW_SOC_PERCENT", 10.0)
    full_soc_percent: float = _p("BATTERY_FULL_SOC_PERCENT", 90.0)


@dataclass(frozen=True)
class PEMLimits:
    # Replace with PEM RFC limits from voltage cutoff and discharge tests.
    min_voltage_discharge_V: float = _p("PEM_MIN_USABLE_VOLTAGE", 0.54975)
    max_voltage_charge_V: float = 2.0
    min_current_discharge_mA: float = 0.0
    max_charge_current_mA: float = 400.0
    min_power_for_load_mW: float = _mw_from_w("PEM_MAX_DISCHARGE_POWER_W", 0.03195)
    min_power_for_charging_mW: float = _mw_from_w("PV_MIN_PEM_CHARGING_POWER_W", 0.020)

    # Used only by the existing app's simple hydrogen estimator.
    min_hydrogen_mL: float = _p("PEM_MIN_HYDROGEN_ML", 0.911)
    full_hydrogen_ml: float = _p("MEASURED_FULL_HYDROGEN_CAPACITY_ML", 15.6)
    hydrogen_production_mL_per_input_j: float = _p("HYDROGEN_PRODUCTION_ML_PER_INPUT_J", 0.07102)
    hydrogen_consumption_mL_per_output_j: float = _p("HYDROGEN_CONSUMPTION_ML_PER_OUTPUT_J", 0.47514)


@dataclass(frozen=True)
class LoadLimits:
    # Replace with measured minimum acceptable load voltage and demand.
    min_voltage_supplied_V: float = 0.0
    min_power_demand_mW: float = _p("MIN_DEMAND_POWER_MILLIWATT", 20.0)


@dataclass(frozen=True)
class SafetyLimits:
    # Hard limits used by software checks. Arduino remains the final authority.
    absolute_min_battery_voltage_V: float = _p("BATTERY_MIN_VOLTAGE", 3.0)
    absolute_max_battery_voltage_V: float = _p("BATTERY_FULL_VOLTAGE", 4.2)
    absolute_min_pem_voltage_V: float = _p("PEM_MIN_USABLE_VOLTAGE", 0.54975)
    absolute_max_pem_voltage_V: float = 2.0
    max_current_mA: float = 1000.0
    max_power_mW: float = _mw_from_w("PV_MAX_POWER_W", 0.500)
    safety_margin_mW: float = _mw_from_w("SAFETY_MARGIN_W", 0.005)


@dataclass(frozen=True)
class EMSLimits:
    price: PriceLimits = field(default_factory=PriceLimits)
    pv: PVLimits = field(default_factory=PVLimits)
    battery: BatteryLimits = field(default_factory=BatteryLimits)
    pem: PEMLimits = field(default_factory=PEMLimits)
    load: LoadLimits = field(default_factory=LoadLimits)
    safety: SafetyLimits = field(default_factory=SafetyLimits)


DEFAULT_LIMITS = EMSLimits()
