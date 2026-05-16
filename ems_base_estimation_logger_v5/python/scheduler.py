"""
File: scheduler.py

Description:
    This script is part of the bachelor project:
    "Investigation of reversible electrolyzers and implementation of energy
    management control strategies through IoT embedded microcontroller".

    This script defines the scheduler logic for deciding the appropriate scenario
    based on the current system state and market conditions.
  
Authors:
    Jacob Norman Sørensen
    Matilde Marie Grønkjær Matell

Institution:
    Technical University of Denmark (DTU)

Date:
    2026-05-18
"""

from __future__ import annotations
from dataclasses import dataclass
from ems_limits import EMS_LIMITS


@dataclass(frozen=True)
class SchedulerInputs:
    """
    Data class representing the input parameters for the EMS scheduler decision logic.
    """
    price_state: str
    pv_available: bool
    battery_soc: float
    pem_soc: float
    battery_voltage_V: float = 0.0

    load_demand_mW: float = EMS_LIMITS.demand.max_demand_power_mW


@dataclass(frozen=True)
class SchedulerDecision:
    """
    Data class representing the output of the EMS scheduler decision logic.
    """
    scenario: int
    reason: str


def decide_scenario(inputs: SchedulerInputs) -> SchedulerDecision:
    """
    Determines the appropriate EMS scenario based on the current system state and price conditions. 
    """
    price_state = str(inputs.price_state).upper()

    low_price = price_state == "LOW"
    high_price = price_state == "HIGH"

    battery_voltage_available = inputs.battery_voltage_V > 0.1

    battery_voltage_high_for_charge = (
        battery_voltage_available
        and inputs.battery_voltage_V >= EMS_LIMITS.battery.charge_stop_voltage_control_V
    )

    battery_voltage_ok_for_discharge = (
        not battery_voltage_available
        or inputs.battery_voltage_V >= EMS_LIMITS.battery.min_voltage_discharge_V
    )

    battery_almost_full = (
        inputs.battery_soc >= EMS_LIMITS.battery.full_soc_control_percent
        or battery_voltage_high_for_charge
    )

    battery_can_discharge = (
        inputs.battery_soc > EMS_LIMITS.battery.min_soc_discharge_percent
        and battery_voltage_ok_for_discharge
    )

    pem_has_energy = (
        inputs.pem_soc > EMS_LIMITS.pem.min_discharge_soc
    )

    pem_load_is_low_enough = (
        inputs.load_demand_mW < EMS_LIMITS.pem.max_load_power_mW
    )

    pem_can_discharge = (
        pem_has_energy
        and pem_load_is_low_enough
    )

    if low_price:
        if not inputs.pv_available:
            return SchedulerDecision(
                scenario=1,
                reason="LOW price and PV unavailable -> grid supplies load.",
            )
    
        if not battery_almost_full:
            return SchedulerDecision(
                scenario=2,
                reason=(
                    "LOW price, PV available and battery below 90% "
                    "-> grid supplies load and PV charges battery."
                ),
            )
    
        if inputs.pem_soc < 100.0:
            return SchedulerDecision(
                scenario=3,
                reason=(
                    "LOW price, PV available, battery above 90% and PEM below 100% "
                    "-> grid supplies load and PV charges PEM."
                ),
            )
    
        return SchedulerDecision(
            scenario=4,
            reason=(
                "LOW price, PV available, battery above 90% and PEM at 100% "
                "-> PV supplies load."
            ),
        )

    if high_price:
        if inputs.pv_available:
            return SchedulerDecision(
                scenario=4,
                reason="HIGH price and PV available -> PV supplies load.",
            )

        if battery_can_discharge:
            return SchedulerDecision(
                scenario=5,
                reason="HIGH price, PV unavailable and battery has energy -> battery supplies load.",
            )

        if pem_can_discharge:
            return SchedulerDecision(
                scenario=6,
                reason=(
                    "HIGH price, PV unavailable, battery low, PEM has usable hydrogen "
                    "and load demand is below 40 mW -> PEM supplies load."
                ),
            )

        if pem_has_energy and not pem_load_is_low_enough:
            return SchedulerDecision(
                scenario=1,
                reason=(
                    "HIGH price, but load demand is too high for PEM "
                    f"({inputs.load_demand_mW:.1f} mW >= "
                    f"{EMS_LIMITS.pem.max_load_power_mW:.1f} mW) -> grid supplies load."
                ),
            )

    return SchedulerDecision(
        scenario=1,
        reason="No local source available -> grid supplies load.",
    )