from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PriceLimits:
    high_price_min_DKK_per_kWh: float = 0.6231


@dataclass(frozen=True)
class DemandLimits:
    min_demand_power_mW: float = 15.0
    max_demand_power_mW: float = 75.0


@dataclass(frozen=True)
class RuntimeLimits:
    min_switch_seconds: float = 2.0
    post_switch_validation_seconds: float = 3.0


@dataclass(frozen=True)
class PVLimits:
    # The EMS only considers PV available if the measured PV voltage is above
    # this value. This avoids treating weak/open-circuit PV voltage as usable PV.
    min_voltage_for_use_V: float = 3.6

    # Once PV is latched as available, it becomes unavailable again if the PV
    # power falls below this value. All EMS power values are handled in mW.
    min_power_for_available_mW: float = 10.0

    # Time delay before PV is unlatched after low PV power is detected.
    latch_off_delay_seconds: float = 1.0

    # Normal EMS operating limits when PV supplies the load.
    max_load_power_mW: float = 100.0
    min_load_voltage_after_apply_V: float = 4.5


@dataclass(frozen=True)
class BatteryLimits:
    # Normal EMS discharge limit. This is intentionally slightly above the
    # Arduino hard safety threshold from the battery discharge lookup curve.
    min_voltage_discharge_V: float = 3.08315

    # Warning level before the lower voltage knee/collapse region. This is not
    # a hard safety cutoff, but it can be used to warn that the virtual battery
    # estimate may no longer be reliable.
    warning_low_voltage_V: float = 3.20

    # Normal EMS charging control limit. This is intentionally slightly below
    # the Arduino hard safety threshold from the battery charge lookup curve.
    charge_stop_voltage_control_V: float = 4.29630

    # Nameplate capacity of the physical battery used for the real battery
    # current-integration estimate. Keep this separate from the scaled demo
    # battery below.
    real_capacity_mAh: float = 2000.0

    # Virtual battery capacity used by the EMS demo.
    # The virtual battery is intentionally scaled to 10 mAh so that the SoC
    # changes visibly during a short laboratory demo. This is not the true
    # physical battery capacity.
    demo_capacity_mAh: float = 10.0

    # Nominal voltage used when converting mW to mA for the virtual battery
    # charge/discharge estimate if no valid measured battery voltage is available.
    demo_nominal_voltage_V: float = 3.7

    # Scheduler SoC limits for the virtual battery.
    min_soc_discharge_percent: float = 10.0
    full_soc_control_percent: float = 90.0

    # Normal EMS operating limits when the battery supplies the load.
    max_load_power_mW: float = 100.0
    min_load_voltage_after_apply_V: float = 3.0

    # Optional reference curve for estimating initial SoC from measured battery
    # voltage. The EMS mainly uses the virtual 10 mAh battery model.
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
    min_voltage_discharge_V: float = 0.54975

    # Normal charge region from your tests is roughly 1.5–1.65 V.
    # This warning tells you that the PEM charge voltage is higher than usual.
    warning_high_charge_voltage_V: float = 1.75

    # EMS charge stop limit. This is below the hard safety maximum but high
    # enough to allow the short transient seen in one test.
    charge_stop_voltage_control_V: float = 1.90

    preferred_load_power_mW: float = 31.95

    # New PEM load limit:
    # The PEM should only be used to supply the load when the load demand is
    # below this value. Your tests showed that the PEM cannot reliably supply
    # more than about 40 mW.
    max_load_power_mW: float = 40.0

    # Kept for backwards compatibility with any UI/logging code that still
    # refers to the older name.
    max_attempted_load_power_mW: float = 40.0

    charge_energy_for_useful_output_J: float = 12.82
    useful_output_duration_s: float = 60.0

    h2_max_mL: float = 15.6
    h2_min_usable_mL: float = 7.6

    h2_charge_mL_per_C: float = 0.104095
    h2_discharge_mL_per_C: float = 0.25175648

    min_discharge_soc: float = 10.0

    # All EMS current values are handled in mA.
    charge_current_threshold_mA: float = 10.0
    discharge_current_threshold_mA: float = -5.0


@dataclass(frozen=True)
class SafetyLimits:
    # Hard battery safety limits based on the characterised lookup-table
    # endpoints. The EMS control limits are kept slightly inside these values.
    absolute_min_battery_voltage_V: float = 3.03315
    absolute_max_battery_voltage_V: float = 4.34630

    # Hard PEM safety limits.
    absolute_min_pem_voltage_V: float = 0.54975
    absolute_max_pem_voltage_V: float = 2.20

    # Hard current and power safety limits.
    max_current_mA: float = 500.0
    max_power_mW: float = 500.0


@dataclass(frozen=True)
class EMSLimits:
    price: PriceLimits = field(default_factory=PriceLimits)
    demand: DemandLimits = field(default_factory=DemandLimits)
    runtime: RuntimeLimits = field(default_factory=RuntimeLimits)
    pv: PVLimits = field(default_factory=PVLimits)
    battery: BatteryLimits = field(default_factory=BatteryLimits)
    pem: PEMLimits = field(default_factory=PEMLimits)
    safety: SafetyLimits = field(default_factory=SafetyLimits)


EMS_LIMITS = EMSLimits()