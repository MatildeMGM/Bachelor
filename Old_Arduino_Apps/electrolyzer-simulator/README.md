# Wind-H2 Strategy S1 Dashboard for Uno Q

Open app at http://82.211.206.229:7000/

This app is structured like the `interface-to-display` Arduino App Lab project you uploaded:

- `app.yaml` uses `bricks: - arduino:web_ui: {}` so the browser UI is hosted by Arduino App Lab.
- `assets/` contains the browser dashboard files.
- `python/main.py` runs the simulation, talks to the browser through WebUI messages, and forwards compact frames to the MCU through `Bridge.call(...)`.
- `sketch/sketch.ino` stays lightweight and device-focused. It receives compact simulation frames and renders a short summary on the same 16x2 LCD wiring used in your LCD project.

## Main changes vs the earlier version

The earlier package used a custom Python HTTP server. This version removes that and instead follows the same App Lab pattern as `interface-to-display`:

- browser assets are served by the `arduino:web_ui` brick
- live telemetry is pushed with `ui.send_message(...)`
- browser control actions come back with `ui.on_message(...)`
- MCU communication uses `Bridge.provide(...)` on the sketch side and `Bridge.call(...)` on the Python side

## Runtime behavior

- The simulation runs continuously in Python.
- One simulation step equals 5 simulated minutes.
- Default live pace is 1 real second per simulation step.
- The browser can pause, resume, single-step, reset, and change the live pace.
- The LCD shows a compact local summary:
  - line 1: wind and used power
  - line 2: electrolyzer state letters and total hydrogen

## Folder layout

- `app.yaml`
- `assets/index.html`
- `assets/app.js`
- `assets/style.css`
- `assets/wind_profile_5min.bin`
- `assets/wind_profile_meta.json`
- `python/main.py`
- `python/config.py`
- `python/simulator.py`
- `python/preprocess_wind.py`
- `sketch/sketch.ino`
- `sketch/sketch.yaml`

## Notes

The model logic still follows the paper-oriented simulator from the previous version, including:

- S1 sequential dispatch
- four 1 MW electrolyzers
- 4.2 MW wind scaling
- hot start / cold start timing
- standby-to-off behavior after 6 steps
- fitted part-load hydrogen production curve
- thermal / cooling model approximation

The one key approximation is unchanged: the paper's heat-generation term depends on stack cell count `N`, which was not available in the extracted table values, so the simulator keeps the stack-equivalent approximation already used in the earlier version.
