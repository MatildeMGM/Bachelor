# EMS Required Parameters per Component

## Variable Load
- Measured load voltage  
- Measured load current  
- Calculated load power  
- Demand setpoint from profile  
- Maximum allowed load power  
- Minimum supply voltage for acceptable operation  

## PV Panels
- PV voltage  
- PV current  
- PV power  
- Minimum PV voltage for usable production  
- Maximum PV current  
- Maximum PV power under lab conditions  
- Available surplus power after supplying load  

## Battery

3.0 V minimum
4.2 V maximum
6.33 Wh usable energy
90 percent SOC as full
10 percent SOC as empty


- Battery voltage  
Measured range: approximately 3.0 V to 3.97 V during the discharge test.

- Battery current  
Measured range: approximately -160 mA to -140 mA during discharge (negative indicates discharge).

- Estimated state of charge (SOC)  
Defined as a normalized value from 100 percent at 3.97 V to 0 percent at 3.0 V, based on the measured discharge curve and updated during operation using power integration.

- Minimum allowed voltage  
3.0 V  
Defined as the practical end of discharge observed in the experiment.

- Maximum allowed voltage  
4.2 V  
Taken from the nominal full charge voltage of the Li polymer battery, not from the experiment.

- Maximum charge current  
Not determined from the experiment  
Must be taken from battery specifications or set conservatively, for example 0.5 C which corresponds to 1.0 A for a 2.0 Ah battery.

- Maximum discharge current  
Approximately 160 mA  
Observed as the maximum during the discharge test, but this reflects the test setup with a 22 ohm load and not the true battery limit.

- Usable energy capacity  
6.33 Wh  
Calculated from integrated discharge energy.

- Charge state (empty, low, medium, high, full)  
Can be defined from the voltage to SOC relation, for example:  
empty: 0 to 10 percent (below approx. 3.1 V)  
low: 10 to 30 percent  
medium: 30 to 70 percent  
high: 70 to 90 percent  
full: 90 to 100 percent (above approx. 3.9 V)

## PEM Cell
- PEM voltage
- PEM current
- PEM power, calculated as P = V · I
- Estimated hydrogen volume
- Minimum hydrogen level for discharge
- Minimum usable fuel cell voltage
- Maximum usable discharge current
- Maximum electrolysis current, limited by measured PV current of approximately 0.40 A
- Minimum charge time before useful discharge
- Usable discharge energy per state, calculated as sum(P · Δt)
- PEM state:
  - empty: no usable discharge
  - low: short discharge time
  - medium: moderate discharge time
  - high: reliable discharge time
  - full: cylinder close to maximum hydrogen level
- Minimum time before switching mode 

## Grid Supply
- Grid voltage  
- Grid current  
- Grid power  
- Maximum current (~125 mA)  
- Maximum allowed power  
- Electricity price  
- Price state (low, medium, high)  

## Arduino and Sensors
- Voltage sensor calibration  
- Current sensor calibration  
- Measurement noise  
- Sampling time  
- Control time step  
- Switching elements (relay/MOSFET states)  
- Safe switching delay  

## Scheduler Input
- 24-hour electricity price profile  
- 96-slot demand profile  
- PV availability or measured PV state  
- Initial battery state  
- Initial PEM state  
- Test duration (e.g. 12 minutes)  
- Slot duration (e.g. 7.5 seconds)  