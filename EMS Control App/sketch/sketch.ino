/*
File: sketch.ino

Description:
    This sketch is part of the bachelor project:
    "Investigation of reversible electrolyzers and implementation of energy
    management control strategies through IoT embedded microcontroller".

    This sketch is the hardware-facing layer of the EMS demonstrator. The
    Python application sends price, scenario, relay and load-trigger commands
    through Arduino_RouterBridge. The sketch reads the INA226 sensors, applies
    the measured calibration corrections, checks hardware safety limits and
    drives the relay outputs that connect the grid, PV panel, battery, PEM/RFC
    and load.

Authors:
    Jacob Norman Sorensen
    Matilde Marie Gronkjaer Matell

Institution:
    Technical University of Denmark (DTU)

Date:
    2026-05-18
*/

// Communication, I2C sensor and math libraries used by the EMS hardware layer.
#include <Arduino_RouterBridge.h>
#include <Wire.h>
#include <INA226_WE.h>
#include <math.h>

// I2C addresses for the four INA226 sensors mounted in the demonstrator.
#define ADDR_BAT  0x40
#define ADDR_LOAD 0x41
#define ADDR_PV   0x44
#define ADDR_PEM  0x45

// Dedicated sensor objects for the battery, load, PV panel and PEM/RFC branch.
INA226_WE inaBat(&Wire, ADDR_BAT);
INA226_WE inaLoad(&Wire, ADDR_LOAD);
INA226_WE inaPV(&Wire, ADDR_PV);
INA226_WE inaPEM(&Wire, ADDR_PEM);

// Relay outputs. The scenario functions below define which relays are closed
// for each EMS operating mode.
const int K1 = 8;
const int K2 = 2;
const int K3 = 3;
const int K4 = 4;
const int K5 = 5;
const int K6 = 7;
const int K7 = 9;

// Digital output used to start or stop the external variable-load sequence.
const int LOAD_SEQUENCE_TRIGGER_PIN = 10;

// Indicator LEDs showing which EMS scenario is currently active.
const int LEDS1 = 12;
const int LEDS2 = 0;
const int LEDS3 = 11;
const int LEDS4 = 6;
const int LEDS5 = 1;
const int LEDS6 = 13;

// Hard battery safety endpoints are based on the characterised lookup table.
// The discharge minimum uses the 0% discharge voltage. The charge maximum uses
// the 100% charge voltage. The EMS control limits in Python are kept slightly
// inside these hard safety limits.
const float BATTERY_SAFETY_MIN_DISCHARGE_VOLTAGE = 3.03315;
const float BATTERY_SAFETY_MAX_CHARGE_VOLTAGE = 4.34630;
const float BATTERY_EMS_MIN_DISCHARGE_VOLTAGE = 3.08315;
const float BATTERY_EMS_CHARGE_STOP_VOLTAGE = 4.29630;

const float BATTERY_MIN_VOLTAGE = BATTERY_SAFETY_MIN_DISCHARGE_VOLTAGE;
const float BATTERY_MAX_VOLTAGE = BATTERY_SAFETY_MAX_CHARGE_VOLTAGE;
const float PEM_MIN_VOLTAGE = 0.54975;
const float PEM_MAX_VOLTAGE = 2.20;

const float MAX_CURRENT_A = 0.5;
const float MAX_POWER_W = 0.5;

// Sensor availability flags are set during setup and reported back to Python.
bool inaBatOk = false;
bool inaLoadOk = false;
bool inaPVOk = false;
bool inaPEMOk = false;

// Latest price frame received from the Python EMS app.
int priceSlot = 0;
float electricityprice = 0.0;
bool priceReceived = false;

// Scenario state used to distinguish the requested scenario from the active
// scenario that was actually accepted by the Arduino safety checks.
int requestedScenario = 1;
int activeScenario = 1;
bool scenarioReceived = false;
bool scenarioAccepted = true;
String lastRejectReason = "";
String lastError = "";

// Latest corrected voltage readings from the INA226 sensors.
float nominalVoltage = 0.0;
float panelVoltage = 0.0;
float loadVoltage = 0.0;
float pemrfcVoltage = 0.0;
float batteryVoltage = 0.0;

// Latest corrected current readings. Values are stored in ampere for safety
// checks and converted to mA in the status payload when needed.
float PVcurrent = 0.0;
float Loadcurrent = 0.0;
float PEMcurrent = 0.0;
float Batcurrent = 0.0;

// Raw shunt voltages are kept for debugging and app-side diagnostics.
float PVshuntVoltage_mV = 0.0;
float LoadshuntVoltage_mV = 0.0;
float PEMshuntVoltage_mV = 0.0;
float BatshuntVoltage_mV = 0.0;

// Calculated branch powers based on the corrected voltage and current values.
float PVpower = 0.0;
float Loadpower = 0.0;
float PEMpower = 0.0;
float Batterypower = 0.0;

String mode = "S1 Grid -> Load";

unsigned long lastPrint = 0;
const unsigned long printInterval = 2000;

// Function declarations keep the sketch readable in the Arduino IDE while the
// implementation is grouped by purpose below.
bool setupINA(INA226_WE &sensor, const char* name);
float correctCurrent_A(byte address, float current_A);
float correctVoltage_V(byte address, float voltage_V);

void readMeasurements();

void setLoadSequenceTrigger(bool active);

void applyScenario(int scenario);
bool scenarioIsSafe(int scenario);
void setScenarioLEDs(int scenario);
void allScenarioLEDsOff();
int relayPinFromName(String relayName);

void scenario1();
void scenario2();
void scenario3();
void scenario4();
void scenario5();
void scenario6();

bool apply_price_frame(String payload);
bool apply_scenario_frame(String payload);
bool apply_relay_frame(String payload);
bool apply_load_trigger_frame(String payload);
String get_status();

void printValues();

// Initialize bridge callbacks, I2C sensors, relay pins, trigger output and
// scenario LEDs. The demonstrator starts in scenario 1 as a known safe state.
void setup() {
  Monitor.begin();
  delay(1000);
  Monitor.println("EMS Arduino safety layer started");

  Bridge.begin();
  Bridge.provide("apply_price_frame", apply_price_frame);
  Bridge.provide("apply_scenario_frame", apply_scenario_frame);
  Bridge.provide("apply_relay_frame", apply_relay_frame);
  Bridge.provide("apply_load_trigger_frame", apply_load_trigger_frame);
  Bridge.provide("get_status", get_status);

  Wire.begin();
  delay(500);

  inaBatOk = setupINA(inaBat, "INA226 Battery");
  inaLoadOk = setupINA(inaLoad, "INA226 Load");
  inaPVOk = setupINA(inaPV, "INA226 PV");
  inaPEMOk = setupINA(inaPEM, "INA226 PEMRFC");

  pinMode(K1, OUTPUT);
  pinMode(K2, OUTPUT);
  pinMode(K3, OUTPUT);
  pinMode(K4, OUTPUT);
  pinMode(K5, OUTPUT);
  pinMode(K6, OUTPUT);
  pinMode(K7, OUTPUT);

  pinMode(LOAD_SEQUENCE_TRIGGER_PIN, OUTPUT);
  digitalWrite(LOAD_SEQUENCE_TRIGGER_PIN, LOW);

  pinMode(LEDS1, OUTPUT);
  pinMode(LEDS2, OUTPUT);
  pinMode(LEDS3, OUTPUT);
  pinMode(LEDS4, OUTPUT);
  pinMode(LEDS5, OUTPUT);
  pinMode(LEDS6, OUTPUT);

  applyScenario(1);
}

// Main runtime loop. Measurements are refreshed frequently, while serial status
// output is throttled so the monitor remains readable during operation.
void loop() {
  readMeasurements();

  if (millis() - lastPrint >= printInterval) {
    lastPrint = millis();
    printValues();
  }

  delay(400);
}

// Configure a single INA226 sensor for continuous averaged measurements.
// Returning false allows the rest of the sketch to keep running if one sensor
// is missing, while still reporting that fault to the Python app.
bool setupINA(INA226_WE &sensor, const char* name) {
  Monitor.print("Initializing ");
  Monitor.print(name);
  Monitor.print(" ... ");

  if (!sensor.init()) {
    Monitor.println("FAILED");
    return false;
  }

  sensor.setAverage(INA226_AVERAGE_64);
  sensor.setConversionTime(INA226_CONV_TIME_1100);
  sensor.setMeasureMode(INA226_CONTINUOUS);
  sensor.waitUntilConversionCompleted();

  Monitor.println("OK");
  return true;
}

// Apply current calibration values found during sensor characterization.
// Each INA226 channel has its own offset or gain correction.
float correctCurrent_A(byte address, float current_A) {
  switch (address) {
    case ADDR_BAT:
      return current_A + 0.000563;

    case ADDR_LOAD:
      return current_A - 0.000033;

    case ADDR_PV:
      return current_A + 0.000138;

    case ADDR_PEM:
      return 0.843 * current_A + 0.001;

    default:
      return current_A;
  }
}

// Apply voltage calibration offsets found during sensor characterization.
float correctVoltage_V(byte address, float voltage_V) {
  switch (address) {
    case ADDR_BAT:
      return voltage_V - 0.068;

    case ADDR_LOAD:
      return voltage_V - 0.066;

    case ADDR_PV:
      return voltage_V - 0.180;

    case ADDR_PEM:
      return voltage_V - 0.064;

    default:
      return voltage_V;
  }
}

// Read every available INA226 sensor and update the shared measurement state.
// These values are used both for the safety checks and for the app status view.
void readMeasurements() {
  nominalVoltage = 5.0;

  if (inaBatOk) {
    inaBat.readAndClearFlags();
    batteryVoltage = correctVoltage_V(ADDR_BAT, inaBat.getBusVoltage_V());
    BatshuntVoltage_mV = inaBat.getShuntVoltage_mV();
    Batcurrent = correctCurrent_A(ADDR_BAT, inaBat.getCurrent_mA() / 1000.0);
    Batterypower = batteryVoltage * Batcurrent;
  }

  if (inaLoadOk) {
    inaLoad.readAndClearFlags();
    loadVoltage = correctVoltage_V(ADDR_LOAD, inaLoad.getBusVoltage_V());
    LoadshuntVoltage_mV = inaLoad.getShuntVoltage_mV();
    Loadcurrent = correctCurrent_A(ADDR_LOAD, inaLoad.getCurrent_mA() / 1000.0);
    Loadpower = loadVoltage * Loadcurrent;
  }

  if (inaPVOk) {
    inaPV.readAndClearFlags();
    panelVoltage = correctVoltage_V(ADDR_PV, inaPV.getBusVoltage_V());
    PVshuntVoltage_mV = inaPV.getShuntVoltage_mV();
    PVcurrent = correctCurrent_A(ADDR_PV, inaPV.getCurrent_mA() / 1000.0);
    PVpower = panelVoltage * PVcurrent;
  }

  if (inaPEMOk) {
    inaPEM.readAndClearFlags();
    pemrfcVoltage = correctVoltage_V(ADDR_PEM, inaPEM.getBusVoltage_V());
    PEMshuntVoltage_mV = inaPEM.getShuntVoltage_mV();
    PEMcurrent = correctCurrent_A(ADDR_PEM, inaPEM.getCurrent_mA() / 1000.0);
    PEMpower = pemrfcVoltage * PEMcurrent;
  }
}

// Control line for the separate variable-load Arduino. A HIGH value starts the
// configured load profile and LOW stops it.
void setLoadSequenceTrigger(bool active) {
  digitalWrite(LOAD_SEQUENCE_TRIGGER_PIN, active ? HIGH : LOW);
}

// Parse a price frame from Python: PRICE,<price_DKK_per_kWh>,<slot_index>.
// The price is stored for monitoring and logging; relay decisions are handled
// by the Python EMS controller before it sends a scenario request.
bool apply_price_frame(String payload) {
  if (!payload.startsWith("PRICE,")) {
    lastError = "invalid price frame";
    return false;
  }

  int firstComma = payload.indexOf(',');
  int secondComma = payload.indexOf(',', firstComma + 1);

  if (firstComma < 0 || secondComma < 0) {
    lastError = "invalid price commas";
    return false;
  }

  electricityprice = payload.substring(firstComma + 1, secondComma).toFloat();
  priceSlot = payload.substring(secondComma + 1).toInt();
  priceReceived = true;
  lastError = "";

  Monitor.print("Received price: ");
  Monitor.print(electricityprice, 5);
  Monitor.print(" DKK/kWh, slot ");
  Monitor.println(priceSlot);

  return true;
}

// Parse and validate a scenario frame. The Python app can send either an
// automatic EMS scenario or a manual scenario, but the Arduino performs the
// same safety check before energizing any relay configuration.
bool apply_scenario_frame(String payload) {
  if (!payload.startsWith("SCENARIO,") && !payload.startsWith("MANUAL_SCENARIO,")) {
    scenarioAccepted = false;
    lastRejectReason = "invalid scenario frame";
    lastError = lastRejectReason;
    return false;
  }

  int c1 = payload.indexOf(',');
  int c2 = payload.indexOf(',', c1 + 1);
  int c3 = payload.indexOf(',', c2 + 1);

  if (c1 < 0) {
    scenarioAccepted = false;
    lastRejectReason = "invalid scenario commas";
    lastError = lastRejectReason;
    return false;
  }

  int scenario = 1;

  if (c2 < 0) {
    scenario = payload.substring(c1 + 1).toInt();
  } else if (c3 >= 0) {
    scenario = payload.substring(c2 + 1, c3).toInt();
  } else {
    scenario = payload.substring(c1 + 1, c2).toInt();
  }

  if (scenario < 1 || scenario > 6) {
    scenarioAccepted = false;
    lastRejectReason = "scenario must be 1-6";
    lastError = lastRejectReason;
    return false;
  }

  requestedScenario = scenario;
  scenarioReceived = true;

  readMeasurements();

  if (!scenarioIsSafe(scenario)) {
    scenarioAccepted = false;
    lastError = lastRejectReason;
    return false;
  }

  applyScenario(scenario);

  scenarioAccepted = true;
  lastRejectReason = "";
  lastError = "";

  Monitor.print("Applied scenario S");
  Monitor.println(scenario);

  return true;
}

// Manual relay command used for hardware testing and debugging. It bypasses the
// scenario LED mapping because the relay state no longer represents one of the
// six predefined EMS scenarios.
bool apply_relay_frame(String payload) {
  if (!payload.startsWith("RELAY,")) {
    lastError = "invalid relay frame";
    return false;
  }

  int c1 = payload.indexOf(',');
  int c2 = payload.indexOf(',', c1 + 1);

  if (c1 < 0 || c2 < 0) {
    lastError = "invalid relay commas";
    return false;
  }

  String relayName = payload.substring(c1 + 1, c2);
  relayName.trim();
  relayName.toUpperCase();

  int pin = relayPinFromName(relayName);

  if (pin < 0) {
    lastError = "unknown relay";
    return false;
  }

  int outputState = payload.substring(c2 + 1).toInt() ? HIGH : LOW;
  digitalWrite(pin, outputState);

  allScenarioLEDsOff();

  mode = "Manual relay " + relayName + (outputState == HIGH ? " HIGH" : " LOW");
  lastError = "";
  return true;
}

// Parse a load-trigger command from Python: LOAD_TRIGGER,0/1. This keeps the
// variable load profile synchronized with the EMS app.
bool apply_load_trigger_frame(String payload) {
  if (!payload.startsWith("LOAD_TRIGGER,")) {
    lastError = "invalid load trigger frame";
    return false;
  }

  int c1 = payload.indexOf(',');

  if (c1 < 0) {
    lastError = "invalid load trigger commas";
    return false;
  }

  int value = payload.substring(c1 + 1).toInt();

  setLoadSequenceTrigger(value == 1);

  lastError = "";

  Monitor.print("Load sequence trigger D10 ");
  Monitor.println(value == 1 ? "HIGH" : "LOW");

  return true;
}

// Final safety gate for scenario changes. The checks combine global branch
// current/power limits with scenario-specific voltage and sensor requirements.
bool scenarioIsSafe(int scenario) {
  lastRejectReason = "";

  if (inaBatOk && fabs(Batcurrent) > MAX_CURRENT_A) {
    lastRejectReason = "battery current limit exceeded";
    return false;
  }

  if (inaLoadOk && fabs(Loadcurrent) > MAX_CURRENT_A) {
    lastRejectReason = "load current limit exceeded";
    return false;
  }

  if (inaPVOk && fabs(PVcurrent) > MAX_CURRENT_A) {
    lastRejectReason = "PV current limit exceeded";
    return false;
  }

  if (inaPEMOk && fabs(PEMcurrent) > MAX_CURRENT_A) {
    lastRejectReason = "PEM current limit exceeded";
    return false;
  }

  if (inaBatOk && fabs(Batterypower) > MAX_POWER_W) {
    lastRejectReason = "battery power limit exceeded";
    return false;
  }

  if (inaLoadOk && fabs(Loadpower) > MAX_POWER_W) {
    lastRejectReason = "load power limit exceeded";
    return false;
  }

  if (inaPVOk && fabs(PVpower) > MAX_POWER_W) {
    lastRejectReason = "PV power limit exceeded";
    return false;
  }

  if (inaPEMOk && fabs(PEMpower) > MAX_POWER_W) {
    lastRejectReason = "PEM power limit exceeded";
    return false;
  }

  // Only the battery charging scenario is blocked by the charge maximum.
  // S1 must remain available as safe standby.
  if (scenario == 2 && inaBatOk && batteryVoltage > BATTERY_SAFETY_MAX_CHARGE_VOLTAGE) {
    lastRejectReason = "battery voltage above charge lookup safety maximum";
    return false;
  }

  if (inaPEMOk && pemrfcVoltage > PEM_MAX_VOLTAGE) {
    lastRejectReason = "PEM voltage above maximum";
    return false;
  }

  if (scenario == 4 && !inaPVOk) {
    lastRejectReason = "PV sensor not available for PV scenario";
    return false;
  }

  if (scenario == 5 && !inaBatOk) {
    lastRejectReason = "battery sensor not available for battery scenario";
    return false;
  }

  if (scenario == 6 && !inaPEMOk) {
    lastRejectReason = "PEM sensor not available for PEM scenario";
    return false;
  }

  if (scenario == 5 && batteryVoltage < BATTERY_SAFETY_MIN_DISCHARGE_VOLTAGE) {
    lastRejectReason = "battery voltage below discharge lookup safety minimum";
    return false;
  }

  if (scenario == 6 && pemrfcVoltage < PEM_MIN_VOLTAGE) {
    lastRejectReason = "PEM voltage too low for discharge";
    return false;
  }

  return true;
}

// Apply the accepted relay configuration for a scenario number. Unknown values
// fall back to scenario 1 as the safe grid-to-load state.
void applyScenario(int scenario) {
  if (scenario == 1) {
    scenario1();
  } else if (scenario == 2) {
    scenario2();
  } else if (scenario == 3) {
    scenario3();
  } else if (scenario == 4) {
    scenario4();
  } else if (scenario == 5) {
    scenario5();
  } else if (scenario == 6) {
    scenario6();
  } else {
    scenario1();
  }
}

// Build the comma-separated status payload consumed by the Python EMS app.
// The payload includes sensor availability, measurements, relay states, safety
// limits, load-trigger state and the most recent accept/reject reason.
String get_status() {
  // readMeasurements();

  String payload = "";

  payload += "inaBatOk=" + String(inaBatOk ? 1 : 0);
  payload += ",inaLoadOk=" + String(inaLoadOk ? 1 : 0);
  payload += ",inaPVOk=" + String(inaPVOk ? 1 : 0);
  payload += ",inaPEMOk=" + String(inaPEMOk ? 1 : 0);

  payload += ",slot=" + String(priceSlot);
  payload += ",price=" + String(electricityprice, 5);
  payload += ",priceReceived=" + String(priceReceived ? 1 : 0);

  payload += ",panelVoltage=" + String(panelVoltage, 5);
  payload += ",batteryVoltage=" + String(batteryVoltage, 5);
  payload += ",pemrfcVoltage=" + String(pemrfcVoltage, 5);
  payload += ",loadVoltage=" + String(loadVoltage, 5);

  payload += ",PVcurrent=" + String(PVcurrent, 5);
  payload += ",Batcurrent=" + String(Batcurrent, 5);
  payload += ",PEMcurrent=" + String(PEMcurrent, 5);
  payload += ",Loadcurrent=" + String(Loadcurrent, 5);

  payload += ",PVcurrent_mA=" + String(PVcurrent * 1000.0, 3);
  payload += ",Batcurrent_mA=" + String(Batcurrent * 1000.0, 3);
  payload += ",PEMcurrent_mA=" + String(PEMcurrent * 1000.0, 3);
  payload += ",Loadcurrent_mA=" + String(Loadcurrent * 1000.0, 3);

  payload += ",PVshunt_mV=" + String(PVshuntVoltage_mV, 5);
  payload += ",Batshunt_mV=" + String(BatshuntVoltage_mV, 5);
  payload += ",PEMshunt_mV=" + String(PEMshuntVoltage_mV, 5);
  payload += ",Loadshunt_mV=" + String(LoadshuntVoltage_mV, 5);

  payload += ",PVpower=" + String(PVpower, 5);
  payload += ",Batterypower=" + String(Batterypower, 5);
  payload += ",PEMpower=" + String(PEMpower, 5);
  payload += ",Loadpower=" + String(Loadpower, 5);

  payload += ",PVpower_mW=" + String(PVpower * 1000.0, 3);
  payload += ",Batterypower_mW=" + String(Batterypower * 1000.0, 3);
  payload += ",PEMpower_mW=" + String(PEMpower * 1000.0, 3);
  payload += ",Loadpower_mW=" + String(Loadpower * 1000.0, 3);

  // Real battery SoC is calculated in Python from these measured I/O values.
  // The sketch only reports hard/EMS voltage limits for safety visibility.
  payload += ",batterySafetyMinDischargeVoltage=" + String(BATTERY_SAFETY_MIN_DISCHARGE_VOLTAGE, 5);
  payload += ",batterySafetyMaxChargeVoltage=" + String(BATTERY_SAFETY_MAX_CHARGE_VOLTAGE, 5);
  payload += ",batteryEMSMinDischargeVoltage=" + String(BATTERY_EMS_MIN_DISCHARGE_VOLTAGE, 5);
  payload += ",batteryEMSChargeStopVoltage=" + String(BATTERY_EMS_CHARGE_STOP_VOLTAGE, 5);
  payload += ",K1=" + String(digitalRead(K1));
  payload += ",K2=" + String(digitalRead(K2));
  payload += ",K3=" + String(digitalRead(K3));
  payload += ",K4=" + String(digitalRead(K4));
  payload += ",K5=" + String(digitalRead(K5));
  payload += ",K6=" + String(digitalRead(K6));
  payload += ",K7=" + String(digitalRead(K7));

  payload += ",loadTrigger=" + String(digitalRead(LOAD_SEQUENCE_TRIGGER_PIN));

  payload += ",scenarioReceived=" + String(scenarioReceived ? 1 : 0);
  payload += ",scenarioAccepted=" + String(scenarioAccepted ? 1 : 0);
  payload += ",requestedScenario=" + String(requestedScenario);
  payload += ",activeScenario=" + String(activeScenario);

  payload += ",mode=" + mode;
  payload += ",lastRejectReason=" + lastRejectReason;
  payload += ",lastError=" + lastError;

  return payload;
}

// Compact serial monitor printout for live bench testing. The full data stream
// is available through get_status(), so this line focuses on the key state.
void printValues() {
  Monitor.print("Mode: ");
  Monitor.print(mode);

  Monitor.print(" Price: ");
  Monitor.print(electricityprice, 5);

  Monitor.print(" Slot: ");
  Monitor.print(priceSlot);

  Monitor.print(" PV V: ");
  Monitor.print(panelVoltage, 3);

  Monitor.print(" Bat V: ");
  Monitor.print(batteryVoltage, 3);

  Monitor.print(" PEM V: ");
  Monitor.print(pemrfcVoltage, 3);

  Monitor.print(" Load mW: ");
  Monitor.print(Loadpower * 1000.0, 1);

  Monitor.print(" Load trigger: ");
  Monitor.print(digitalRead(LOAD_SEQUENCE_TRIGGER_PIN));

  Monitor.print(" Last error: ");
  Monitor.println(lastError);
}

// Scenario 1: grid supplies the load. This is the default safe standby mode.
void scenario1() {
  digitalWrite(K1, HIGH);
  digitalWrite(K2, LOW);
  digitalWrite(K3, HIGH);
  digitalWrite(K4, HIGH);
  digitalWrite(K5, HIGH);
  digitalWrite(K6, HIGH);
  digitalWrite(K7, HIGH);

  activeScenario = 1;
  mode = "S1 Grid -> Load";
  setScenarioLEDs(1);
}

// Scenario 2: grid supplies the load while PV charges the battery.
void scenario2() {
  digitalWrite(K1, HIGH);
  digitalWrite(K2, LOW);
  digitalWrite(K3, LOW);
  digitalWrite(K4, HIGH);
  digitalWrite(K5, HIGH);
  digitalWrite(K6, HIGH);
  digitalWrite(K7, LOW);

  activeScenario = 2;
  mode = "S2 Grid -> Load and PV -> Battery";
  setScenarioLEDs(2);
}

// Scenario 3: grid supplies the load while PV powers the PEM/RFC branch.
void scenario3() {
  digitalWrite(K1, HIGH);
  digitalWrite(K2, LOW);
  digitalWrite(K3, HIGH);
  digitalWrite(K4, LOW);
  digitalWrite(K5, HIGH);
  digitalWrite(K6, HIGH);
  digitalWrite(K7, LOW);

  activeScenario = 3;
  mode = "S3 Grid -> Load and PV -> PEMRFC";
  setScenarioLEDs(3);
}

// Scenario 4: PV supplies the load directly.
void scenario4() {
  digitalWrite(K1, LOW);
  digitalWrite(K2, HIGH);
  digitalWrite(K3, HIGH);
  digitalWrite(K4, HIGH);
  digitalWrite(K5, HIGH);
  digitalWrite(K6, HIGH);
  digitalWrite(K7, LOW);

  activeScenario = 4;
  mode = "S4 PV -> Load";
  setScenarioLEDs(4);
}

// Scenario 5: battery supplies the load.
void scenario5() {
  digitalWrite(K1, LOW);
  digitalWrite(K2, LOW);
  digitalWrite(K3, HIGH);
  digitalWrite(K4, HIGH);
  digitalWrite(K5, LOW);
  digitalWrite(K6, HIGH);
  digitalWrite(K7, HIGH);

  activeScenario = 5;
  mode = "S5 Battery -> Load";
  setScenarioLEDs(5);
}

// Scenario 6: PEM/RFC branch supplies the load.
void scenario6() {
  digitalWrite(K1, LOW);
  digitalWrite(K2, LOW);
  digitalWrite(K3, HIGH);
  digitalWrite(K4, HIGH);
  digitalWrite(K5, HIGH);
  digitalWrite(K6, LOW);
  digitalWrite(K7, HIGH);

  activeScenario = 6;
  mode = "S6 PEM -> Load";
  setScenarioLEDs(6);
}

// Update the scenario LEDs so only the active scenario indicator is lit.
void setScenarioLEDs(int scenario) {
  digitalWrite(LEDS1, scenario == 1 ? HIGH : LOW);
  digitalWrite(LEDS2, scenario == 2 ? HIGH : LOW);
  digitalWrite(LEDS3, scenario == 3 ? HIGH : LOW);
  digitalWrite(LEDS4, scenario == 4 ? HIGH : LOW);
  digitalWrite(LEDS5, scenario == 5 ? HIGH : LOW);
  digitalWrite(LEDS6, scenario == 6 ? HIGH : LOW);
}

// Clear all scenario LEDs, mainly used after manual relay commands.
void allScenarioLEDsOff() {
  digitalWrite(LEDS1, LOW);
  digitalWrite(LEDS2, LOW);
  digitalWrite(LEDS3, LOW);
  digitalWrite(LEDS4, LOW);
  digitalWrite(LEDS5, LOW);
  digitalWrite(LEDS6, LOW);
}

// Convert a relay name from a manual command to the corresponding Arduino pin.
int relayPinFromName(String relayName) {
  if (relayName == "K1") return K1;
  if (relayName == "K2") return K2;
  if (relayName == "K3") return K3;
  if (relayName == "K4") return K4;
  if (relayName == "K5") return K5;
  if (relayName == "K6") return K6;
  if (relayName == "K7") return K7;

  return -1;
}
