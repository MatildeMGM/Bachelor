"""
File: ems_limits.py

Description:
    This script is part of the bachelor project:
    "Investigation of reversible electrolyzers and implementation of energy
    management control strategies through IoT embedded microcontroller".

    This script defines the various limits and thresholds used by the EMS control logic. 
    These limits include price thresholds, demand limits, runtime constraints,
    PV availability criteria, battery voltage thresholds, PEM operating limits, and hard safety limits. 
    The limits are organized into dataclasses for structured access throughout the EMS application.

Authors:
    Jacob Norman Sørensen
    Matilde Marie Grønkjær Matell

Institution:
    Technical University of Denmark (DTU)

Date:
    2026-05-18
"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PriceLimits:
    """
    Stores the electricity price threshold used to classify the current price state for the EMS.
    """

    high_price_min_DKK_per_kWh: float = 0.6231


@dataclass(frozen=True)
class DemandLimits:
    """
    Stores the demand profile limits used by the EMS, including the minimum and maximum load power levels.
    """

    min_demand_power_mW: float = 15.0
    max_demand_power_mW: float = 75.0


@dataclass(frozen=True)
class RuntimeLimits:
    """
    Stores the runtime constraints used by the EMS, including minimum switch times and validation delays.
    """

    min_switch_seconds: float = 2.0
    post_switch_validation_seconds: float = 3.0


@dataclass(frozen=True)
class PVLimits:
    """
    Stores the PV availability and operating limits used by the EMS.
    """

    min_voltage_for_use_V: float = 3.6
    min_power_for_available_mW: float = 10.0

    latch_off_delay_seconds: float = 1.0
    max_load_power_mW: float = 100.0

    min_load_voltage_after_apply_V: float = 4.5


@dataclass(frozen=True)
class BatteryLimits:
    """
    Stores the battery voltage, SoC, capacity, and load limits used by the EMS.
    """

    min_voltage_discharge_V: float = 3.08315
    warning_low_voltage_V: float = 3.20
    charge_stop_voltage_control_V: float = 4.29630

    real_capacity_mAh: float = 2000.0

    demo_capacity_mAh: float = 10.0
    demo_nominal_voltage_V: float = 3.7

    min_soc_discharge_percent: float = 10.0
    full_soc_control_percent: float = 90.0

    max_load_power_mW: float = 100.0
    min_load_voltage_after_apply_V: float = 3.0

    voltage_soc_curve: tuple[tuple[float, float], ...] = (
        (2.98, 0.0),
        (3.20, 1.0),
        (3.40, 3.0),
        (3.60, 6.0),
        (3.72, 8.0),
        (3.78, 12.0),
        (3.83, 20.0),
        (3.88, 40.0),
        (3.92, 50.0),
        (3.98, 60.0),
        (4.05, 70.0),
        (4.12, 80.0),
        (4.20, 100.0),
    )

@dataclass(frozen=True)
class PEMLimits:
    """
    Stores the PEM voltage, hydrogen, current, and load limits used by the EMS.
    """

    min_voltage_discharge_V: float = 0.54975
    warning_high_charge_voltage_V: float = 1.75
    charge_stop_voltage_control_V: float = 1.90

    preferred_load_power_mW: float = 31.95
    max_load_power_mW: float = 40.0
    max_attempted_load_power_mW: float = 40.0

    charge_energy_for_useful_output_J: float = 12.82
    useful_output_duration_s: float = 60.0

    h2_max_mL: float = 15.6
    h2_min_usable_mL: float = 7.6

    h2_charge_mL_per_C: float = 0.104095
    h2_discharge_mL_per_C: float = 0.25175648

    min_discharge_soc: float = 10.0

    charge_current_threshold_mA: float = 10.0
    discharge_current_threshold_mA: float = -5.0


@dataclass(frozen=True)
class SafetyLimits:
    """
    Stores the absolute voltage, current, and power safety limits used by the EMS.
    """

    absolute_min_battery_voltage_V: float = 3.03315
    absolute_max_battery_voltage_V: float = 4.34630

    absolute_min_pem_voltage_V: float = 0.54975
    absolute_max_pem_voltage_V: float = 2.20

    max_current_mA: float = 500.0
    max_power_mW: float = 500.0


@dataclass(frozen=True)
class EMSLimits:
    """
    Collects all EMS limit categories into one shared configuration object.
    """

    price: PriceLimits = field(default_factory=PriceLimits)
    demand: DemandLimits = field(default_factory=DemandLimits)
    runtime: RuntimeLimits = field(default_factory=RuntimeLimits)
    pv: PVLimits = field(default_factory=PVLimits)
    battery: BatteryLimits = field(default_factory=BatteryLimits)
    pem: PEMLimits = field(default_factory=PEMLimits)
    safety: SafetyLimits = field(default_factory=SafetyLimits)


EMS_LIMITS = EMSLimits()