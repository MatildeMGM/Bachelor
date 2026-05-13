#include <Arduino_RouterBridge.h>
#include <Wire.h>
#include <INA226_WE.h>

// -----------------------------------------------------------------------------
// INA226 addresses
// -----------------------------------------------------------------------------
#define ADDR_1 0x40
#define ADDR_2 0x41
#define ADDR_3 0x44
#define ADDR_4 0x45

INA226_WE ina1(&Wire, ADDR_1);
INA226_WE ina2(&Wire, ADDR_2);
INA226_WE ina3(&Wire, ADDR_3);
INA226_WE ina4(&Wire, ADDR_4);

bool ina1Init = false;
bool ina2Init = false;
bool ina3Init = false;
bool ina4Init = false;

float ina1BusV = 0.0, ina1CurrentmA = 0.0, ina1PowermW = 0.0, ina1ShuntmV = 0.0;
float ina2BusV = 0.0, ina2CurrentmA = 0.0, ina2PowermW = 0.0, ina2ShuntmV = 0.0;
float ina3BusV = 0.0, ina3CurrentmA = 0.0, ina3PowermW = 0.0, ina3ShuntmV = 0.0;
float ina4BusV = 0.0, ina4CurrentmA = 0.0, ina4PowermW = 0.0, ina4ShuntmV = 0.0;

// -----------------------------------------------------------------------------
// LED / Nano signal outputs
// LEDS1 and LEDS3 moved off old SDA/SCL pins
// -----------------------------------------------------------------------------
const int LEDS1 = 12;  // old 21 -> new D12, Nano D7
const int LEDS2 = 0;   // Nano D4
const int LEDS3 = 11;  // old 20 -> new D11, Nano D3
const int LEDS4 = 6;   // Nano D6
const int LEDS5 = 1;   // Nano D5
const int LEDS6 = 13;  // Nano D2

const int ledPins[] = {LEDS1, LEDS2, LEDS3, LEDS4, LEDS5, LEDS6};
const char* ledNames[] = {
  "LEDS1_NanoD7",
  "LEDS2_NanoD4",
  "LEDS3_NanoD3",
  "LEDS4_NanoD6",
  "LEDS5_NanoD5",
  "LEDS6_NanoD2"
};
const int NUM_LED_PINS = sizeof(ledPins) / sizeof(ledPins[0]);

String ledMode = "AUTO";
int activeLedIndex = 0;
unsigned long lastLedStepMs = 0;
unsigned long ledStepIntervalMs = 1500;
unsigned long lastInaReadMs = 0;
unsigned long inaReadIntervalMs = 1000;

void setupINA(INA226_WE &sensor, const char* name, bool &okFlag) {
  Monitor.print("Initializing ");
  Monitor.print(name);
  Monitor.print(" ... ");

  if (!sensor.init()) {
    Monitor.println("FAILED");
    okFlag = false;
    return;
  }

  sensor.setAverage(INA226_AVERAGE_16);
  sensor.setConversionTime(INA226_CONV_TIME_1100);
  sensor.setMeasureMode(INA226_CONTINUOUS);
  sensor.waitUntilConversionCompleted();

  okFlag = true;
  Monitor.println("OK");
}

void readOneSensor(INA226_WE &sensor, bool okFlag, float &busV, float &currentmA, float &powermW, float &shuntmV) {
  if (!okFlag) {
    busV = 0.0;
    currentmA = 0.0;
    powermW = 0.0;
    shuntmV = 0.0;
    return;
  }

  busV = sensor.getBusVoltage_V();
  currentmA = sensor.getCurrent_mA();
  powermW = sensor.getBusPower();
  shuntmV = sensor.getShuntVoltage_mV();
}

void readAllIna() {
  readOneSensor(ina1, ina1Init, ina1BusV, ina1CurrentmA, ina1PowermW, ina1ShuntmV);
  readOneSensor(ina2, ina2Init, ina2BusV, ina2CurrentmA, ina2PowermW, ina2ShuntmV);
  readOneSensor(ina3, ina3Init, ina3BusV, ina3CurrentmA, ina3PowermW, ina3ShuntmV);
  readOneSensor(ina4, ina4Init, ina4BusV, ina4CurrentmA, ina4PowermW, ina4ShuntmV);
}

void allSignalsLow() {
  for (int i = 0; i < NUM_LED_PINS; i++) {
    digitalWrite(ledPins[i], LOW);
  }
}

void activateSignal(int index) {
  if (index < 0 || index >= NUM_LED_PINS) {
    return;
  }

  allSignalsLow();
  digitalWrite(ledPins[index], HIGH);
  activeLedIndex = index;

  Monitor.print("Active test output: ");
  Monitor.print(ledNames[index]);
  Monitor.print(" | Uno pin D");
  Monitor.println(ledPins[index]);
}

bool set_led_mode(String payload) {
  payload.trim();
  payload.toUpperCase();

  if (payload == "AUTO" || payload == "MANUAL") {
    ledMode = payload;
    Monitor.print("LED mode set to: ");
    Monitor.println(ledMode);
    return true;
  }

  Monitor.println("Invalid LED mode");
  return false;
}

bool set_led_index(String payload) {
  payload.trim();
  int index = payload.toInt();
  if (index < 0 || index >= NUM_LED_PINS) {
    Monitor.println("Invalid LED index");
    return false;
  }

  ledMode = "MANUAL";
  activateSignal(index);
  return true;
}

bool set_led_interval(String payload) {
  payload.trim();
  unsigned long interval = (unsigned long) payload.toInt();
  if (interval < 100) {
    Monitor.println("LED interval too small");
    return false;
  }

  ledStepIntervalMs = interval;
  Monitor.print("LED interval set to ");
  Monitor.println(ledStepIntervalMs);
  return true;
}

String get_status() {
  float totalPowermW = ina1PowermW + ina2PowermW + ina3PowermW + ina4PowermW;
  float maxCurrentmA = ina1CurrentmA;
  if (ina2CurrentmA > maxCurrentmA) maxCurrentmA = ina2CurrentmA;
  if (ina3CurrentmA > maxCurrentmA) maxCurrentmA = ina3CurrentmA;
  if (ina4CurrentmA > maxCurrentmA) maxCurrentmA = ina4CurrentmA;

  String payload = "";
  payload += "ledMode=" + ledMode;
  payload += ",activeSignalIndex=" + String(activeLedIndex);
  payload += ",activeSignalPin=" + String(ledPins[activeLedIndex]);
  payload += ",activeSignalName=" + String(ledNames[activeLedIndex]);
  payload += ",modeText=INA226_LED_TEST";
  payload += ",sensorCount=4";
  payload += ",readIntervalMs=" + String(inaReadIntervalMs);
  payload += ",totalPowermW=" + String(totalPowermW, 4);
  payload += ",maxCurrentmA=" + String(maxCurrentmA, 4);

  payload += ",ina1Init=" + String(ina1Init ? 1 : 0);
  payload += ",ina1BusV=" + String(ina1BusV, 4);
  payload += ",ina1CurrentmA=" + String(ina1CurrentmA, 4);
  payload += ",ina1PowermW=" + String(ina1PowermW, 4);
  payload += ",ina1ShuntmV=" + String(ina1ShuntmV, 4);

  payload += ",ina2Init=" + String(ina2Init ? 1 : 0);
  payload += ",ina2BusV=" + String(ina2BusV, 4);
  payload += ",ina2CurrentmA=" + String(ina2CurrentmA, 4);
  payload += ",ina2PowermW=" + String(ina2PowermW, 4);
  payload += ",ina2ShuntmV=" + String(ina2ShuntmV, 4);

  payload += ",ina3Init=" + String(ina3Init ? 1 : 0);
  payload += ",ina3BusV=" + String(ina3BusV, 4);
  payload += ",ina3CurrentmA=" + String(ina3CurrentmA, 4);
  payload += ",ina3PowermW=" + String(ina3PowermW, 4);
  payload += ",ina3ShuntmV=" + String(ina3ShuntmV, 4);

  payload += ",ina4Init=" + String(ina4Init ? 1 : 0);
  payload += ",ina4BusV=" + String(ina4BusV, 4);
  payload += ",ina4CurrentmA=" + String(ina4CurrentmA, 4);
  payload += ",ina4PowermW=" + String(ina4PowermW, 4);
  payload += ",ina4ShuntmV=" + String(ina4ShuntmV, 4);

  return payload;
}

void setup() {
  Monitor.begin();
  delay(1000);
  Monitor.println("INA226 + LED test sketch started");

  Bridge.begin();
  Bridge.provide("get_status", get_status);
  Bridge.provide("set_led_mode", set_led_mode);
  Bridge.provide("set_led_index", set_led_index);
  Bridge.provide("set_led_interval", set_led_interval);

  for (int i = 0; i < NUM_LED_PINS; i++) {
    pinMode(ledPins[i], OUTPUT);
    digitalWrite(ledPins[i], LOW);
  }

  Wire.begin();
  delay(500);

  setupINA(ina1, "INA226_0x40", ina1Init);
  setupINA(ina2, "INA226_0x41", ina2Init);
  setupINA(ina3, "INA226_0x44", ina3Init);
  setupINA(ina4, "INA226_0x45", ina4Init);

  readAllIna();
  activateSignal(activeLedIndex);
}

void loop() {
  unsigned long now = millis();

  if (now - lastInaReadMs >= inaReadIntervalMs) {
    lastInaReadMs = now;
    readAllIna();

    Monitor.println("----- INA226 Readings -----");
    Monitor.print("0x40 | Bus[V]: "); Monitor.print(ina1BusV, 4); Monitor.print(" | Current[mA]: "); Monitor.print(ina1CurrentmA, 4); Monitor.print(" | Power[mW]: "); Monitor.print(ina1PowermW, 4); Monitor.print(" | Shunt[mV]: "); Monitor.println(ina1ShuntmV, 4);
    Monitor.print("0x41 | Bus[V]: "); Monitor.print(ina2BusV, 4); Monitor.print(" | Current[mA]: "); Monitor.print(ina2CurrentmA, 4); Monitor.print(" | Power[mW]: "); Monitor.print(ina2PowermW, 4); Monitor.print(" | Shunt[mV]: "); Monitor.println(ina2ShuntmV, 4);
    Monitor.print("0x44 | Bus[V]: "); Monitor.print(ina3BusV, 4); Monitor.print(" | Current[mA]: "); Monitor.print(ina3CurrentmA, 4); Monitor.print(" | Power[mW]: "); Monitor.print(ina3PowermW, 4); Monitor.print(" | Shunt[mV]: "); Monitor.println(ina3ShuntmV, 4);
    Monitor.print("0x45 | Bus[V]: "); Monitor.print(ina4BusV, 4); Monitor.print(" | Current[mA]: "); Monitor.print(ina4CurrentmA, 4); Monitor.print(" | Power[mW]: "); Monitor.print(ina4PowermW, 4); Monitor.print(" | Shunt[mV]: "); Monitor.println(ina4ShuntmV, 4);
    Monitor.println();
  }

  if (ledMode == "AUTO" && now - lastLedStepMs >= ledStepIntervalMs) {
    lastLedStepMs = now;
    activeLedIndex++;
    if (activeLedIndex >= NUM_LED_PINS) {
      activeLedIndex = 0;
    }
    activateSignal(activeLedIndex);
  }

  delay(20);
}
