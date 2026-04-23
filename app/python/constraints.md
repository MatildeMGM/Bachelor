# EMS System Constraints (v1 Optimizer)

Essential physical and operational constraints for the scenario optimizer.

---

## 1. BATTERY

- **Min SOC** (%): ___________
- **Max SOC** (%): ___________
- **Max Charge Power** (W): ___________
- **Max Discharge Power** (W): ___________
- **Charge Efficiency** (%): ___________
- **Discharge Efficiency** (%): ___________

---

## 2. PEM / REVERSIBLE FUEL CELL

### Electrolyzer Mode (producing H2)
- **Min Power** (W): ___________
- **Max Power** (W): ___________
- **Efficiency** (%): ___________

### Fuel Cell Mode (consuming H2)
- **Min Power** (W): ___________
- **Max Power** (W): ___________
- **Efficiency** (%): ___________

### Mode Switching
- **Min time before switching modes** (minutes): ___________

### State
- **Min SOC** (%): ___________
- **Max SOC** (%): ___________

---

## 3. LOAD

- **Type**: Fixed / Flexible / Deferrable / (specify)
- **Average Power** (W): ___________
- **Max Power** (W): ___________
- **Demand Forecast Available**: Yes / No

---

## 4. RELAY MAPPING & SCENARIOS

### Relay Functions

| Relay | Function | Connects |
|-------|----------|----------|
| K1 | ___________ | ___________ |
| K2 | ___________ | ___________ |
| K3 | ___________ | ___________ |
| K4 | ___________ | ___________ |
| K5 | ___________ | ___________ |
| K6 | ___________ | ___________ |
| K7 | ___________ | ___________ |

### Valid Scenarios

| Scenario | Description | K1 | K2 | K3 | K4 | K5 | K6 | K7 | Purpose |
|----------|-------------|----|----|----|----|----|----|----|---------|
| 1 | ___________ | ___ | ___ | ___ | ___ | ___ | ___ | ___ | ___________ |
| 2 | ___________ | ___ | ___ | ___ | ___ | ___ | ___ | ___ | ___________ |
| 3 | ___________ | ___ | ___ | ___ | ___ | ___ | ___ | ___ | ___________ |
| 4 | ___________ | ___ | ___ | ___ | ___ | ___ | ___ | ___ | ___________ |
| 5 | ___________ | ___ | ___ | ___ | ___ | ___ | ___ | ___ | ___________ |
| 6 | ___________ | ___ | ___ | ___ | ___ | ___ | ___ | ___ | ___________ |

---

## 5. OPTIMIZATION OBJECTIVE

**Primary Goal:**
- [ ] Minimize electricity cost (grid import)
- [ ] Maximize self-consumption
- [ ] Balance battery/PEM SOC
- [ ] Maximize PEM H2 production
- [ ] Other: ___________________________

**Rationale:** _________________________________________________________________
