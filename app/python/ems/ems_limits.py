"""Editable EMS operating limits.

These values are deliberately collected in one small file so they are easy to
show in the bachelor report and easy to replace with experimentally derived
thresholds from component characterisation.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PriceLimits:
    # One threshold is used: below it is low price, at/above it is high price.
    low_price_max_DKK_per_kWh: float = 0.6231
    high_price_min_DKK_per_kWh: float = 0.6231


@dataclass(frozen=True)
class PVLimits:
    # Replace with PV characterisation values from the final lab setup.
    min_voltage_for_use_V: float = 4.2812
    min_power_for_load_mW: float = 100.0
    min_power_for_charging_mW: float = 20.0
    min_current_out_mA: float = 0.0


@dataclass(frozen=True)
class BatteryLimits:
    # Replace with battery voltage/current/power limits from tests and datasheet.
    min_voltage_discharge_V: float = 3.0
    max_voltage_charge_V: float = 4.2
    min_current_discharge_mA: float = 0.0
    max_charge_current_mA: float = 1000.0
    min_power_for_load_mW: float = 100.0
    usable_energy_Wh: float = 0.100
    low_soc_percent: float = 10.0
    full_soc_percent: float = 90.0


@dataclass(frozen=True)
class PEMLimits:
    # Replace with PEM RFC limits from voltage cutoff and discharge tests.
    min_voltage_discharge_V: float = 0.54975
    max_voltage_charge_V: float = 2.0
    min_current_discharge_mA: float = 0.0
    max_charge_current_mA: float = 400.0
    min_power_for_load_mW: float = 31.95
    min_power_for_charging_mW: float = 20.0

    # Used only by the existing app's simple hydrogen estimator.
    min_hydrogen_mL: float = 0.911
    full_hydrogen_ml: float = 15.6
    hydrogen_production_mL_per_input_j: float = 0.07102
    hydrogen_consumption_mL_per_output_j: float = 0.47514


@dataclass(frozen=True)
class LoadLimits:
    # Replace with measured minimum acceptable load voltage and demand.
    min_voltage_supplied_V: float = 0.0
    min_power_demand_mW: float = 20.0


@dataclass(frozen=True)
class SafetyLimits:
    # Hard limits used by software checks. Arduino remains the final authority.
    absolute_min_battery_voltage_V: float = 3.0
    absolute_max_battery_voltage_V: float = 4.2
    absolute_min_pem_voltage_V: float = 0.54975
    absolute_max_pem_voltage_V: float = 2.0
    max_current_mA: float = 1000.0
    max_power_mW: float = 500.0
    safety_margin_mW: float = 5.0


@dataclass(frozen=True)
class EMSLimits:
    price: PriceLimits = field(default_factory=PriceLimits)
    pv: PVLimits = field(default_factory=PVLimits)
    battery: BatteryLimits = field(default_factory=BatteryLimits)
    pem: PEMLimits = field(default_factory=PEMLimits)
    load: LoadLimits = field(default_factory=LoadLimits)
    safety: SafetyLimits = field(default_factory=SafetyLimits)


DEFAULT_LIMITS = EMSLimits()

