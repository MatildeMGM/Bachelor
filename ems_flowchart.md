# EMS Flowchart From Inputs to Scenario Initiation

This document maps the EMS control path from input parameters and live data to
scenario initiation for scenarios S1-S6.

Main source files:

- `app/python/main.py` starts the app and the EMS background loop.
- `app/python/ems_loop.py` refreshes input data, calls the scheduler, sends
  commands to Arduino, logs results, and updates the UI.
- `app/python/ems/ems_limits.py` contains editable price, PV, battery, PEM,
  load, and safety limits.
- `app/python/scheduler.py` reads price, demand, and Arduino measurements,
  evaluates threshold eligibility, chooses the target scenario, and builds the
  `SCENARIO` command.
- `app/python/ems_state.py` stores current values and converts Arduino status
  into the scheduler's component state.
- `app/python/bridge.py` sends `CONFIG`, `PRICE`, and `SCENARIO` frames to the
  Arduino sketch.
- `app/sketch/sketch.ino` reads sensors, performs final safety checks, switches
  relays, sets LEDs, and reports status.

## 1. Overall Data Flow

```mermaid
flowchart TD
    A[App start: main.py] --> B[setup_ui]
    A --> C[Start ems_loop thread]

    C --> D[Load EMS limits from ems_limits.py]
    D --> E[Build CONFIG command]
    E --> F[Refresh inputs]

    F --> G[Fetch 96 electricity price slots]
    F --> H[Load 96 demand slots from scaled_may_power_profile_15min.csv]
    F --> I[Set current slot, price, and demand]

    I --> J{EMS loop every 0.5 s}
    J --> K[Update demo time and current slot]
    K --> L[Fetch Arduino get_status]
    L --> M[Apply Arduino status to EMSState]
    M --> N[build_component_state]

    N --> O[decide_current_scenario]
    O --> P[Select price mode and compare measurements to thresholds]
    P --> Q[Choose target scenario S1-S6]
    Q --> R[Build SCENARIO command]

    R --> S{Demo running and new slot?}
    S -- No --> T[Send telemetry to UI only]
    S -- Yes --> U[Push CONFIG once]
    U --> V[Push PRICE for current slot]
    V --> W[Push SCENARIO once per slot]

    W --> X[Arduino apply_scenario_frame]
    X --> Y{Arduino safety checks pass?}
    Y -- No --> Z[Fallback to S1 grid supply]
    Y -- Yes --> AA[ApplyScenario S1-S6]
    AA --> AB[Set relays, mode string, and scenario LED]
    Z --> AB
    AB --> AC[Fetch status again, log slot, update UI]
    AC --> J
    T --> J
```

## 2. Input Parameters And Live Measurements

```mermaid
flowchart LR
    A[ems_limits.py] --> B[load_limits]
    B --> C[Battery limits]
    B --> D[PEM limits]
    B --> E[PV limits]
    B --> F[Price and safety limits]

    G[Day-ahead electricity prices] --> H[96 price slots]
    I[Scaled demand CSV] --> J[96 demand slots in W]

    K[Arduino INA226 sensors] --> L[get_status]
    L --> M[PV voltage, current, power]
    L --> N[Battery voltage, power, SOC, energy]
    L --> O[PEM voltage and power]
    L --> P[Load voltage and power]

    C --> S[Threshold comparison]
    D --> S
    E --> S
    F --> S
    H --> S
    J --> S
    M --> S
    N --> S
    O --> S
    P --> S
    S --> T[Scheduler decision]
```

## 3. Scheduler Scenario Selection

In the simplified EMS interpretation, the components are not placed in
operating modes. Only the price creates an economic mode from one threshold:
prices below `PRICE_LIMITS.high_price_min_DKK_per_kWh` are low-price mode, and
prices at or above it are high-price mode. The physical components are measured
and compared directly with their safety and operating thresholds.

```mermaid
flowchart TD
    A[Current slot] --> B[Read price_now and demand_now]
    B --> C[Read Arduino status measurements]
    C --> D[Build ComponentState]
    D --> E[Select economic price mode]

    E --> E1[Low price if price < price threshold]
    E --> E2[High price if price >= price threshold]

    D --> F[Compare live measurements to thresholds]
    F --> F1[PV voltage compared with charge/load thresholds]
    F --> F2[Battery voltage, SOC and demand compared with limits]
    F --> F3[PEM voltage and demand compared with limits]
    F --> F4[Demand compared with battery and PEM discharge limits]

    F1 --> G[Build eligible scenario set]
    F2 --> G
    F3 --> G
    F4 --> G

    G --> H[S1 always eligible]
    G --> I[S2 if PV can charge battery]
    G --> J[S3 if PV can charge PEM]
    G --> K[S4 if PV can supply current demand]
    G --> L[S5 if battery can cover demand]
    G --> M[S6 if PEM can cover demand]

    H --> N{Price mode}
    I --> N
    J --> N
    K --> N
    L --> N
    M --> N

    N -- High --> O[Priority: S4, then S5, then S6, then S1]
    N -- Low --> P[Priority: S2, then S3, then S4, then S1]

    O --> Q
    P --> Q
    Q[Select first eligible scenario] --> U[Build SCENARIO frame]
```

## 4. Arduino Scenario Validation And Initiation

```mermaid
flowchart TD
    A[Receive SCENARIO frame] --> B[Parse slot, requested scenario, demand_mW]
    B --> C[Parse PV voltage/power thresholds and safety margin]
    C --> D[Read voltage, current, and power]
    D --> E[Run pre-check for requested scenario]

    E -->|Fail| F[Scenario1 fallback]
    E -->|Pass| G[ApplyScenario requested S1-S6]

    G --> H{Requested scenario is S2, S3, or S4?}
    H -- No --> I[Scenario accepted]
    H -- Yes --> J[Wait PV loaded settling time]
    J --> K[Read voltage, current, power, and battery SOC again]
    K --> L[Run loaded PV validation]
    L -->|Fail| F
    L -->|Pass| I

    F --> M[Set S1 relays, mode, LEDS1]
    I --> N[Set requested scenario relays, mode, LED]
    M --> O[Return false to Python]
    N --> P[Return true to Python]
```

## 5. Scenario Conditions And Actions

| Scenario | Scenario behavior | Scheduler eligibility | Arduino pre-check | Arduino loaded validation | Initiation action |
| --- | --- | --- | --- | --- | --- |
| S1 | Grid supplies load. PV, battery and PEM isolated. | Always eligible. | Always accepted. | None. | `Scenario1()` sets grid-load relay state and `LEDS1`. |
| S2 | Grid supplies load. PV charges battery. | PV voltage reaches battery-charge threshold and battery SOC is below full. | PV voltage high enough, battery voltage below max, battery SOC below full. | PV current positive, PV power above battery-charge threshold, battery still below max/full. | `Scenario2()` connects PV to battery and keeps grid supplying load. |
| S3 | Grid supplies load. PV charges PEM. | PV is available and PEM can accept charge. | PV voltage high enough for PEM charging. | PV current positive and PV power above PEM-charge threshold. | `Scenario3()` connects PV to PEM and keeps grid supplying load. |
| S4 | PV supplies load. | PV voltage reaches load-supply threshold. | PV voltage high enough for load supply. | PV current positive, PV power above load-supply threshold, and PV power covers demand plus safety margin. | `Scenario4()` connects PV to load. |
| S5 | Battery supplies load. | Battery voltage above minimum, optional SOC above low limit, and demand within battery load limit. | Battery voltage above minimum, SOC above low SOC threshold, and demand within battery discharge limit plus safety margin. | None. | `Scenario5()` connects battery to load. |
| S6 | PEM supplies load. | PEM voltage above minimum and demand within PEM load limit. | PEM voltage above minimum and demand within PEM discharge limit. | None. | `Scenario6()` connects PEM to load. |

## 6. Scenario Priority Summary

```mermaid
flowchart TD
    A[Eligible scenarios from measured thresholds] --> B{Price >= threshold?}

    B -- Yes: high price --> C{S4 eligible?}
    C -- Yes --> S4[S4: PV supplies load]
    C -- No --> D{S5 eligible?}
    D -- Yes --> S5[S5: Battery supplies load]
    D -- No --> E{S6 eligible?}
    E -- Yes --> S6[S6: PEM supplies load]
    E -- No --> S1a[S1: Grid fallback]

    B -- No: low price --> F{S2 eligible?}
    F -- Yes --> S2[S2: PV charges battery, grid supplies load]
    F -- No --> G{S3 eligible?}
    G -- Yes --> S3[S3: PV charges PEM, grid supplies load]
    G -- No --> H{S4 eligible?}
    H -- Yes --> S4b[S4: PV supplies load]
    H -- No --> S1b[S1: Grid fallback]

```

## 7. Command Frames Sent To Arduino

```text
CONFIG,<bat_min_V>,<bat_full_V>,<bat_empty_test_V>,<bat_full_test_V>,
<bat_capacity_mWh>,<bat_low_soc>,<bat_full_soc>,<bat_max_discharge_mW>,
<pem_min_V>,<pem_max_discharge_mW>,<safety_mW>
```

```text
PRICE,<electricity_price_dkk_kWh>,<slot>
```

```text
SCENARIO,<slot>,<scenario>,<demand_mW>,
<pv_battery_charge_min_V>,<pv_battery_charge_min_mW>,
<pv_pem_charge_min_V>,<pv_pem_charge_min_mW>,
<pv_load_supply_min_V>,<pv_load_supply_min_mW>,
<safety_mW>
```

## 8. Relay And LED Outputs

| Scenario | K1 | K2 | K3 | K4 | K5 | K6 | K7 | LED |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S1 | HIGH | LOW | HIGH | HIGH | HIGH | HIGH | HIGH | LEDS1 |
| S2 | HIGH | LOW | LOW | HIGH | HIGH | HIGH | LOW | LEDS2 |
| S3 | HIGH | LOW | HIGH | LOW | HIGH | HIGH | LOW | LEDS3 |
| S4 | LOW | HIGH | HIGH | HIGH | HIGH | HIGH | LOW | LEDS4 |
| S5 | LOW | LOW | HIGH | HIGH | LOW | HIGH | HIGH | LEDS5 |
| S6 | LOW | LOW | HIGH | HIGH | HIGH | LOW | HIGH | LEDS6 |
