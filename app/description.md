# App structure description

This document gives a simple overview of the folders and files inside the app. The purpose is to make it easier to understand what each part of the system does, without going into unnecessary code details.

## Overall app structure

The app is divided into three main parts.

1. The user interface

The user interface is placed in the `assets` folder. This part is what the user sees in the browser. It shows system values, prices, status information, and other data sent from the Python layer.

2. The Python layer

The Python layer is placed in the `python` folder. This is the main control part of the app. It collects data, stores the current state of the system, communicates within the Arduino, and sends information to the user interface.

3. The Arduino layer

The Arduino layer is placed in the `sketch` folder. This part interacts with the physical setup. It reads measurements, controls relays, and sends status information back to Python.

## Folder descriptions

### `assets`

This folder contains the files used for the web user interface. It includes the layout, styling, and JavaScript logic that updates the page while the system is running.

Typical contents include:

1. `index.html`

This file defines the structure of the web page. It decides which elements are shown, such as buttons, text fields, status values, and plots.

2. `style.css`

This file controls the visual appearance of the web page. It defines colors, spacing, fonts, and layout.

3. `app.js`

This file handles the dynamic part of the user interface. It receives telemetry data from the Python layer and updates the values shown in the browser.

### `python`

This folder contains the main Python app. It is the supervisory layer of the EMS. It is responsible for collecting input data, storing system state, communicating with the Arduino, and running the higher level control logic.

### `python/data`

This folder contains small data modules used by the Python app. These files collect or prepare input data for the EMS, such as electricity prices, PV forecast values, weather forecast values, and demand profiles.

The purpose of this folder is to keep data collection separate from the control logic.

### `python/forecast`

This folder contains files related to the demand forecast model. These files are used to predict or prepare consumption data that can later be used as an EMS input.

Typical contents include:

1. `Consumption_data.csv`

This file contains consumption data used for training, testing, or running the demand forecast.

2. `lstm_model.keras`

This file contains the trained LSTM model.

3. `scaler_X.pkl` and `scaler_y.pkl`

These files contain scalers used to transform input and output data before and after model prediction.

4. `feature_cols.pkl`

This file stores the feature columns used by the forecast model.

5. `LSTM.ipynb`

This notebook was likely used for model development, training, or testing.

### `sketch`

This folder contains the Arduino part of the app. The Arduino is responsible for interacting with the physical hardware. It receives commands from Python and sends measurements and status information back.

Typical contents include:

1. `sketch.ino`

This is the main Arduino code. It controls relays, reads sensor values, and communicates with the Python layer.

2. `sketch.yaml`

This file contains configuration information for the Arduino app setup.

3. `readme.md`

This file can be used to document how the Arduino sketch should be used or uploaded.

## Python file descriptions

### `main.py`

This is the starting point of the Python app. It sets up the user interface, starts the background loop, and runs the application.

It does not contain the main control logic itself. Instead, it starts the different parts of the app and keeps the system running.

In simple terms, `main.py` is the file that starts everything.

### `ui.py`

This file handles communication between the Python app and the web user interface.

It builds the data payload that is sent to the browser. This includes prices, PV forecast values, current time slot, Arduino status, and possible error messages.

It also contains the main update loop. This loop refreshes data, updates the shared EMS state, communicates with the Arduino through the bridge, and sends updated telemetry to the user interface.

In simple terms, `ui.py` is the connection between the running EMS and what the user sees on the screen.

### `ems_state.py`

This file contains the shared state object for the EMS.

The state object stores the current values used across the Python app. Examples include electricity prices, current price, current time slot, PV forecast, measurements, Arduino status, and error messages.

The state does not send data by itself. Other files read from it and write to it.

In simple terms, `ems_state.py` is the app memory.

### `bridge.py`

This file handles communication between Python and the Arduino.

It sends commands from Python to the Arduino and receives status information back. For example, it can send the current electricity price and time slot to the Arduino, and it can read status values returned from the Arduino.

In simple terms, `bridge.py` is the messenger between Python and Arduino.

### `control.py`

This file is intended for the EMS control logic.

The control logic decides how the system should operate based on inputs such as electricity prices, PV forecast, demand profile, and measured system values.

This is where scenario decisions should be placed, instead of mixing them into the user interface or communication files.

In simple terms, `control.py` is where the EMS decision making belongs.

### `config.py`

This file contains shared configuration values used by the app.

Examples can include time zone, default price zone, API settings, request timeouts, and other constants.

Keeping these values in one place makes the system easier to adjust, because the same constants do not have to be repeated across many files.

In simple terms, `config.py` contains settings used by the app.

### `scheduler.py`

This file is used for timing or scheduling tasks in the Python app.

It can be used to decide when data should be updated, when forecasts should be refreshed, or when repeated tasks should run.

In simple terms, `scheduler.py` helps the app do things at the right time.

### `supervisor.py`

This file is intended to supervise the operation of the system.

A supervisor module can be used to monitor whether the system is running correctly, check for faults, and coordinate higher level behavior between control logic, data inputs, and hardware communication.

In simple terms, `supervisor.py` can act as the system coordinator.

### `constraints.md`

This file describes constraints used in the EMS design.

These constraints may include operating limits, safe voltage ranges, switching rules, or other practical restrictions that the control logic should respect.

In simple terms, `constraints.md` documents the rules that the EMS should follow.

## Files inside `python/data`

### `prices.py`

This file retrieves electricity price data and formats it for use in the EMS.

It returns price values in the time resolution used by the control logic. These prices are then stored in the shared EMS state and can be used for control decisions or sent to the Arduino.

### `weather.py`

This file retrieves weather forecast data from the Open Meteo API.

It returns weather variables such as shortwave radiation and temperature. The weather module does not calculate PV power itself. It only provides weather forecast data to the PV module.

### `pv.py`

This file converts weather forecast data into a simplified PV power estimate.

It uses shortwave radiation, rated panel power, and a correction factor to estimate PV power. The hourly forecast values are then converted to 15 minute values so they match the EMS time structure.

### `demand.py`

This file is intended to provide demand values or demand profiles for the EMS.

It can be used to simulate a realistic load curve, based on either measured data, predefined profiles, or a forecast model.

### `test.py`

This file appears to be used for testing code during development.

It should not contain final app logic unless it is cleaned up and given a clear purpose.

## Suggested data flow

The app can be understood through the following data flow.

1. External data is collected by the data modules.

Electricity prices are collected by `prices.py`.
Weather data is collected by `weather.py`.
PV forecast values are produced by `pv.py`.
Demand profiles can be produced by `demand.py`.

2. The Python layer stores the current values.

The values are stored in `ems_state.py`, where they can be accessed by the rest of the app.

3. The control logic decides what the system should do.

The control logic should be placed in `control.py` or coordinated through `supervisor.py`.

4. Commands are sent to the Arduino.

`bridge.py` sends the relevant command or value to the Arduino sketch.

5. The Arduino executes the physical action.

The Arduino reads sensors, controls relays, and returns status information.

6. The user interface is updated.

`ui.py` sends updated state information to the browser, where `app.js` updates the displayed values.

## Short summary

The `app` folder contains the part of the project that runs the EMS. The `assets` folder contains the user interface, the `python` folder contains the supervisory control system, and the `sketch` folder contains the Arduino hardware code. The Python layer collects data, stores the system state, communicates with the Arduino, and updates the user interface. The Arduino layer performs measurements and executes the physical actions in the laboratory setup.
