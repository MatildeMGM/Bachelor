

# constraints defined from battery tests and specifications
BATTERY = {
    "E_max": 6.33,        # Wh (measured usable)
    "E_min": 0.8,         # avoid deep discharge (≈ 10-15%)
    "P_max": 0.6,         # W (from your test)
    "eta_ch": 0.95,
    "eta_dch": 0.95,
}



import numpy as np
import cvxpy as cp


def optimize_battery(
    net_load_w,
    dt=0.25,
    e_init=3.0,
):
    n = len(net_load_w)

    p_ch = cp.Variable(n, nonneg=True)
    p_dch = cp.Variable(n, nonneg=True)
    e = cp.Variable(n + 1)

    # residual after battery
    residual = net_load_w + p_ch - p_dch

    constraints = []

    # initial energy
    constraints += [e[0] == e_init]

    # bounds
    constraints += [
        e >= BATTERY["E_min"],
        e <= BATTERY["E_max"]
    ]

    constraints += [
        p_ch <= BATTERY["P_max"],
        p_dch <= BATTERY["P_max"]
    ]

    # dynamics
    for t in range(n):
        constraints += [
            e[t+1] == e[t]
            + BATTERY["eta_ch"] * p_ch[t] * dt
            - (p_dch[t] / BATTERY["eta_dch"]) * dt
        ]

    # objective: smooth net load
    objective = cp.Minimize(cp.sum_squares(residual))

    problem = cp.Problem(objective, constraints)
    problem.solve()

    return {
        "p_ch": p_ch.value,
        "p_dch": p_dch.value,
        "energy": e.value,
        "residual": residual.value
    }