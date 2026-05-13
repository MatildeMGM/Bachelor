
import json
import math
import time
from collections import deque
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Deque, Dict, List
import numpy as np



from config import (
    ASSETS_DIR,
    COLD_START_SECONDS,
    CW_MJ_PER_KG_C,
    DELTA_U_COLD,
    DELTA_U_HOT,
    ELEC_CAPACITY_KW,
    ELEC_MIN_KW,
    ELEC_STANDBY_KW,
    FARADAY,
    H2_LHV_KWH_PER_KG,
    HEAT_CAPACITY_MJ_PER_C,
    HISTORY_LIMIT,
    HOT_START_SECONDS,
    KI_COOLING,
    KP_COOLING,
    LOOP_PROFILE,
    MLIQ_KG_PER_S,
    MH2_G_PER_MOL,
    RTC,
    RTH,
    SIM_STEP_HOURS,
    SIM_STEP_SECONDS,
    SPECIFIC_KWH_PER_KG_100,
    SPECIFIC_KWH_PER_KG_25,
    SPECIFIC_KWH_PER_KG_50,
    STANDBY_TO_OFF_STEPS,
    T_CW_IN_C,
    T_ENV_C,
    T_REF_C,
    THERMAL_RESISTANCE_C_PER_MW,
    CLIQ_MJ_PER_KG_C,
    U_HE_MW_PER_M2_C,
    A_HE_M2,
    UTH_V,
    Z_H2,
    ROTATION_STEPS
)

STATE_OFF = "OFF"
STATE_COLD = "COLD_START"
STATE_STANDBY = "STANDBY"
STATE_HOT = "HOT_START"
STATE_PROD = "PRODUCTION"

def fit_h2_curve():
    # points in kW -> kg/h using Table 7
    pts = np.array([
        [0.0, 0.0],
        [0.25 * ELEC_CAPACITY_KW, 0.25 * ELEC_CAPACITY_KW / SPECIFIC_KWH_PER_KG_25],
        [0.50 * ELEC_CAPACITY_KW, 0.50 * ELEC_CAPACITY_KW / SPECIFIC_KWH_PER_KG_50],
        [1.00 * ELEC_CAPACITY_KW, 1.00 * ELEC_CAPACITY_KW / SPECIFIC_KWH_PER_KG_100],
    ], dtype=float)

    # quadratic with least squares, then zero-clamp later
    coeff = np.polyfit(pts[:, 0], pts[:, 1], 2)
    return coeff.tolist()

H2_COEFF_A2, H2_COEFF_A1, H2_COEFF_A0 = fit_h2_curve()

def hydrogen_rate_kgph(power_kw: float) -> float:
    if power_kw <= 0:
        return 0.0
    y = H2_COEFF_A2 * power_kw * power_kw + H2_COEFF_A1 * power_kw + H2_COEFF_A0
    return max(0.0, y)

def hydrogen_rate_kgs(power_kw: float) -> float:
    return hydrogen_rate_kgph(power_kw) / 3600.0

def h2_rate_to_current_a(h2_kgs: float) -> float:
    # Faraday: I = z F m_dot / M_H2
    # m_dot here is converted to g/s
    h2_gs = h2_kgs * 1000.0
    if h2_gs <= 0:
        return 0.0
    return Z_H2 * FARADAY * h2_gs / MH2_G_PER_MOL

def safe_lmtd(dt1: float, dt2: float) -> float:
    eps = 1e-9
    if dt1 <= eps or dt2 <= eps:
        return 0.0
    if abs(dt1 - dt2) < 1e-9:
        return dt1
    return (dt1 - dt2) / math.log(dt1 / dt2)

def solve_heat_exchanger_q_mw(th_c: float, mcw_kg_s: float) -> Dict[str, float]:
    if mcw_kg_s <= 1e-9 or th_c <= T_CW_IN_C:
        return {"q_he_mw": 0.0, "t_liq_c": th_c, "t_cw_out_c": T_CW_IN_C}

    ua = U_HE_MW_PER_M2_C * A_HE_M2
    ch = MLIQ_KG_PER_S * CLIQ_MJ_PER_KG_C
    cc = mcw_kg_s * CW_MJ_PER_KG_C

    # upper bound constrained by both streams
    q_hi = min(ch * max(th_c - T_CW_IN_C, 0.0), cc * max(th_c - T_CW_IN_C, 0.0))
    q_hi = max(q_hi, 1e-6)

    def residual(q):
        t_liq = th_c - q / ch
        t_cw_out = T_CW_IN_C + q / cc
        dt1 = th_c - T_CW_IN_C
        dt2 = t_liq - t_cw_out
        lmtd = safe_lmtd(dt1, dt2)
        return ua * lmtd - q

    lo, hi = 0.0, q_hi
    rlo = residual(lo)
    rhi = residual(hi)

    if rhi > 0:
        q = min(ua * max(th_c - T_CW_IN_C, 0.0), q_hi)
    else:
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            rm = residual(mid)
            if rm > 0:
                lo = mid
            else:
                hi = mid
        q = 0.5 * (lo + hi)

    t_liq = th_c - q / ch
    t_cw_out = T_CW_IN_C + q / cc
    return {"q_he_mw": q, "t_liq_c": t_liq, "t_cw_out_c": t_cw_out}

@dataclass
class ElectrolyzerSnapshot:
    id: int
    state: str
    H: int
    C: int
    requested_kw: float
    actual_kw: float
    standby_kw: float
    h2_kgph: float
    h2_total_kg: float
    temp_c: float
    cooling_kg_s: float
    standby_steps: int
    nhs: int
    ncs: int

class Electrolyzer:
    def __init__(self, idx: int):
        self.id = idx
        self.H = RTH
        self.C = RTC
        self.requested_kw = 0.0
        self.actual_kw = 0.0
        self.standby_kw = 0.0
        self.h2_kgph = 0.0
        self.h2_total_kg = 0.0
        self.temp_c = T_REF_C
        self.cooling_kg_s = 0.0
        self.t_liq_c = T_REF_C
        self.t_cw_out_c = T_CW_IN_C
        self.standby_steps = 0
        self.nhs = 0
        self.ncs = 0
        self.energy_in_kwh = 0.0
        self.standby_energy_kwh = 0.0
        self.h2_energy_kwh = 0.0
        self.window_temp_error = deque(maxlen=6)

    @property
    def state(self) -> str:
        if self.C == -1:
            return STATE_OFF
        if 0 <= self.C < RTC:
            return STATE_COLD
        if self.H == -1:
            return STATE_STANDBY
        if 0 <= self.H < RTH:
            return STATE_HOT
        return STATE_PROD

    def shut_down_hot(self):
        if self.C == RTC:
            self.H = -1

    def shut_down_cold(self):
        self.C = -1
        self.H = RTH

    def hot_start(self):
        if self.C == RTC and self.H == -1:
            self.H = 0
            self.nhs += 1
            self.standby_steps = 0

    def cold_start(self):
        if self.C == -1:
            self.C = 0
            self.H = RTH
            self.ncs += 1
            self.standby_steps = 0

    def apply_thermal_model(self):
        err = self.temp_c - T_REF_C
        self.window_temp_error.append(err)
        integ = sum(self.window_temp_error)
        self.cooling_kg_s = max(0.0, KP_COOLING * err + KI_COOLING * integ)

        hx = solve_heat_exchanger_q_mw(self.temp_c, self.cooling_kg_s)
        self.t_liq_c = hx["t_liq_c"]
        self.t_cw_out_c = hx["t_cw_out_c"]
        q_liq_mw = MLIQ_KG_PER_S * CLIQ_MJ_PER_KG_C * (self.temp_c - self.t_liq_c)
        q_loss_mw = ((self.temp_c - T_ENV_C) / THERMAL_RESISTANCE_C_PER_MW) / 1e6

        i_a = h2_rate_to_current_a(hydrogen_rate_kgs(self.actual_kw))
        if i_a > 1e-9 and self.actual_kw > 0:
            u_eff = (self.actual_kw * 1000.0) / i_a
        else:
            u_eff = UTH_V
        # Stack-equivalent approximation: paper uses N(U-Uth)I; N is not provided.
        q_gen_mw = max(0.0, (u_eff - UTH_V) * i_a * 1e-6)

        delta_t_s = SIM_STEP_SECONDS
        dT = (q_gen_mw - q_liq_mw - q_loss_mw) * delta_t_s / HEAT_CAPACITY_MJ_PER_C
        self.temp_c += dT

    def step(self, available_kw: float):
        self.requested_kw = max(0.0, available_kw)
        self.actual_kw = 0.0
        self.standby_kw = 0.0
        self.h2_kgph = 0.0

        available_kw = max(0.0, available_kw)

        if self.C == -1:
            # OFF
            self.C = -1
            self.H = RTH

        elif 0 <= self.C < RTC:
            # COLD_START: no production yet
            # If you want startup consumption here too, use min(ELEC_STANDBY_KW, available_kw)
            self.C += 1

        else:
            if self.H == -1:
                # STANDBY
                self.standby_kw = min(ELEC_STANDBY_KW, available_kw)
                self.standby_steps += 1

            elif 0 <= self.H < RTH:
                # HOT_START
                self.standby_kw = min(ELEC_STANDBY_KW, available_kw)
                self.H += 1
                self.standby_steps = 0

            else:
                # PRODUCTION
                self.actual_kw = min(available_kw, ELEC_CAPACITY_KW)
                self.actual_kw = max(0.0, self.actual_kw)
                self.standby_steps = 0

                if self.actual_kw > 0:
                    self.h2_kgph = hydrogen_rate_kgph(self.actual_kw)

        self.h2_total_kg += self.h2_kgph * SIM_STEP_HOURS
        self.energy_in_kwh += self.actual_kw * SIM_STEP_HOURS
        self.standby_energy_kwh += self.standby_kw * SIM_STEP_HOURS
        self.h2_energy_kwh += self.h2_kgph * SIM_STEP_HOURS * H2_LHV_KWH_PER_KG

        self.apply_thermal_model()

    def snapshot(self):
        return ElectrolyzerSnapshot(
            id=self.id,
            state=self.state,
            H=self.H,
            C=self.C,
            requested_kw=round(self.requested_kw, 3),
            actual_kw=round(self.actual_kw, 3),
            standby_kw=round(self.standby_kw, 3),
            h2_kgph=round(self.h2_kgph, 5),
            h2_total_kg=round(self.h2_total_kg, 5),
            temp_c=round(self.temp_c, 3),
            cooling_kg_s=round(self.cooling_kg_s, 4),
            standby_steps=self.standby_steps,
            nhs=self.nhs,
            ncs=self.ncs,
        )

class ElectrolyzerPlant:
    def __init__(self):
        path = ASSETS_DIR / "wind_profile_5min.bin"
        if not path.exists():
            raise FileNotFoundError(
                f"{path} does not exist. Run preprocess_wind.py first."
            )

        self.strategy = "S1"
        self.rotation_steps = ROTATION_STEPS

        self.wind_profile_kw = np.fromfile(path, dtype=np.uint16).astype(float)
        self.idx = 0
        self.step_idx = 0

        self.electrolyzers = [Electrolyzer(i + 1) for i in range(4)]
        self.history: Deque[Dict] = deque(maxlen=HISTORY_LIMIT)

        self.total_curtailed_kwh = 0.0
        self.total_wind_kwh = 0.0

    def set_strategy(self, strategy: str):
        if strategy in ("S1", "S2"):
            self.strategy = strategy

    def get_dispatch_order(self) -> List[Electrolyzer]:
        if self.strategy == "S1":
            return list(self.electrolyzers)

        if self.strategy == "S2":
            shift = (self.step_idx // self.rotation_steps) % len(self.electrolyzers)
            return list(self.electrolyzers[shift:] + self.electrolyzers[:shift])

        return list(self.electrolyzers)

    def current_wind_kw(self) -> float:
        return float(self.wind_profile_kw[self.idx])

    def advance_profile(self):
        self.idx += 1
        if self.idx >= len(self.wind_profile_kw):
            if LOOP_PROFILE:
                self.idx = 0
            else:
                self.idx = len(self.wind_profile_kw) - 1

    def dispatch_actions(self, remaining_kw: float, e: Electrolyzer):
        state = e.state

        if remaining_kw < ELEC_MIN_KW:
            if state == STATE_PROD:
                e.shut_down_hot()
            elif state == STATE_STANDBY and e.standby_steps >= STANDBY_TO_OFF_STEPS:
                e.shut_down_cold()
            return

        # remaining_kw >= minimum operating power
        if state == STATE_STANDBY:
            e.hot_start()
        elif state == STATE_OFF:
            e.cold_start()

    def step(self) -> Dict:
        wind_kw = self.current_wind_kw()
        remaining_kw = wind_kw
        dispatch_order = self.get_dispatch_order()

        for e in dispatch_order:
            self.dispatch_actions(remaining_kw, e)
            e.step(remaining_kw)

            consumed_kw = e.actual_kw + e.standby_kw
            remaining_kw = max(0.0, remaining_kw - consumed_kw)

        standby_kw = sum(e.standby_kw for e in self.electrolyzers)
        production_kw = sum(e.actual_kw for e in self.electrolyzers)
        used_kw = production_kw + standby_kw
        h2_kgph = sum(e.h2_kgph for e in self.electrolyzers)
        h2_total_kg = sum(e.h2_total_kg for e in self.electrolyzers)
        curtailed_kw = max(0.0, wind_kw - used_kw)

        self.total_wind_kwh += wind_kw * SIM_STEP_HOURS
        self.total_curtailed_kwh += curtailed_kw * SIM_STEP_HOURS

        total_h2_energy_kwh = sum(e.h2_energy_kwh for e in self.electrolyzers)
        total_input_kwh = self.total_wind_kwh + sum(e.standby_energy_kwh for e in self.electrolyzers)
        efficiency = total_h2_energy_kwh / total_input_kwh if total_input_kwh > 0 else 0.0

        snap = {
            "step": self.step_idx,
            "wind_kw": round(wind_kw, 3),
            "used_kw": round(used_kw, 3),
            "standby_kw": round(standby_kw, 3),
            "curtailed_kw": round(curtailed_kw, 3),
            "h2_kgph_total": round(h2_kgph, 5),
            "h2_total_kg": round(h2_total_kg, 5),
            "system_efficiency": round(efficiency, 5),
            "strategy": self.strategy,
            "dispatch_order": [e.id for e in dispatch_order],
            "electrolyzers": [asdict(e.snapshot()) for e in self.electrolyzers],
            "nhs_total": sum(e.nhs for e in self.electrolyzers),
            "ncs_total": sum(e.ncs for e in self.electrolyzers),
            "load_factors": [
                round(
                    e.energy_in_kwh / ((self.step_idx + 1) * SIM_STEP_HOURS * ELEC_CAPACITY_KW),
                    5
                )
                for e in self.electrolyzers
            ],
        }

        self.history.append(snap)
        self.step_idx += 1
        self.advance_profile()
        return snap

    def get_state(self) -> Dict:
        if self.history:
            current = dict(self.history[-1])
        else:
            current = self.step()

        current["strategy"] = self.strategy
        current["dispatch_order"] = [e.id for e in self.get_dispatch_order()]

        return {
            "current": current,
            "history": list(self.history),
            "meta": {
                "profile_points": int(len(self.wind_profile_kw)),
                "sim_step_seconds": SIM_STEP_SECONDS,
                "hot_start_steps": int(RTH),
                "cold_start_steps": int(RTC),
                "standby_to_off_steps": int(STANDBY_TO_OFF_STEPS),
                "rotation_steps": int(self.rotation_steps),
                "h2_curve_coeff": [H2_COEFF_A2, H2_COEFF_A1, H2_COEFF_A0],
                "approximation_note": "Thermal heat generation uses stack-equivalent U/I because stack cell count N is not provided in the paper tables.",
            },
        }