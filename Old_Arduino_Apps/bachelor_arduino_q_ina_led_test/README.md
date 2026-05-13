Bachelor Arduino Q INA226 + LED test app

What it does
- Reads 4 INA226 sensors at addresses 0x40, 0x41, 0x44, 0x45
- Drives the 6 old LED/Nano signal lines for wiring tests
- Lets you switch between manual LED selection and automatic stepping from the web UI
- Uses the original Arduino Q app layout as the base structure

Pin assumptions used here
- LEDS1 = 12  (moved from old SDA/SCL pin 21)
- LEDS2 = 0
- LEDS3 = 11  (moved from old SDA/SCL pin 20)
- LEDS4 = 6
- LEDS5 = 1
- LEDS6 = 13

Notes
- Pins 0 and 1 are still used because they appear in the old layout. If they cause trouble on your board, move LEDS2 and LEDS5 as well.
- The sketch uses Arduino_RouterBridge and exposes:
  - get_status
  - set_led_mode
  - set_led_index
  - set_led_interval
