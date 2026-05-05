#include <Arduino_RouterBridge.h>
#include <Wire.h>
#include <INA226_WE.h>

#define ADDR_BAT  0x40
#define ADDR_LOAD 0x41
#define ADDR_PV   0x44
#define ADDR_PEM  0x45

INA226_WE inaBat(&Wire, ADDR_BAT);
INA226_WE inaLoad(&Wire, ADDR_LOAD);
INA226_WE inaPV(&Wire, ADDR_PV);
INA226_WE inaPEM(&Wire, ADDR_PEM);

// Relay pins
const int K1 = 8;
const int K2 = 2;
const int K3 = 3;
const int K4 = 4;
const int K5 = 5;
const int K6 = 7;
const int K7 = 9;

// LED signal pins
const int LEDS1 = 12;
const int LEDS2 = 0;
const int LEDS3 = 11;
const int LEDS4 = 6;
const int LEDS5 = 1;
const int LEDS6 = 13;

// Price and scheduler variables received from Python
int priceSlot = 0;
float electricityprice = 0.0;
bool priceReceived = false;
int requestedScenario = 1;
float requestedDemand_mW = 0.0;
bool scenarioReceived = false;
bool scenarioAccepted = true;
String lastRejectReason = "";

float PV_MIN_VOLTAGE_FOR_BATTERY_CHARGING = 0.0;
float PV_MIN_POWER_FOR_BATTERY_CHARGING = 0.0;
float PV_MIN_VOLTAGE_FOR_PEM_CHARGING = 0.0;
float PV_MIN_POWER_FOR_PEM_CHARGING = 0.0;
float PV_MIN_VOLTAGE_FOR_LOAD_SUPPLY = 0.0;
float PV_MIN_POWER_FOR_LOAD_SUPPLY = 0.0;

// Battery limits from test
const float BATTERY_MIN_VOLTAGE = 3.0;
const float BATTERY_MAX_VOLTAGE = 4.2;
const float BATTERY_EMPTY_TEST_VOLTAGE = 3.0;
const float BATTERY_FULL_TEST_VOLTAGE = 3.97;
const float BATTERY_USABLE_ENERGY_WH = 6.33;
const float BATTERY_MAX_CHARGE_CURRENT_A = 1.0;
const float BATTERY_MAX_DISCHARGE_CURRENT_A = 0.16;
const float BATTERY_LOW_SOC = 10.0;
const float BATTERY_FULL_SOC = 90.0;
const float PEM_MIN_USABLE_VOLTAGE = 0.4935;
const float PEM_MAX_DISCHARGE_POWER_W = 0.040;
float SAFETY_MARGIN_W = 0.005;
const float PV_VOLTAGE_CORRECTION_V = 0.180;
const float PV_CURRENT_CORRECTION_A = 0.000138;
const float PEM_VOLTAGE_CORRECTION_V = 0.064;
const float PEM_CURRENT_SCALE = 0.843;
const float PEM_CURRENT_OFFSET_A = 0.001;
const unsigned long PV_LOADED_SETTLING_MS = 1200;

// Measured values
float nominalVoltage = 0.0;
float panelVoltage = 0.0;
float loadVoltage = 0.0;
float pemrfcVoltage = 0.0;
float batteryVoltage = 0.0;

float PVcurrent = 0.0;
float Loadcurrent = 0.0;
float PEMcurrent = 0.0;
float Batcurrent = 0.0;

float PVshuntVoltage_mV = 0.0;
float LoadshuntVoltage_mV = 0.0;
float PEMshuntVoltage_mV = 0.0;
float BatshuntVoltage_mV = 0.0;

float PVpower = 0.0;
float Loadpower = 0.0;
float PEMpower = 0.0;
float Batterypower = 0.0;

bool inaBatOk = false;
bool inaLoadOk = false;
bool inaPVOk = false;
bool inaPEMOk = false;

// Battery SOC variables
float batterySOC = 0.0;
float batteryEnergyWh = 0.0;
unsigned long lastBatterySOCUpdate = 0;
String batteryChargeState = "";

// Printing variables
unsigned long lastPrint = 0;
const long printInterval = 2000;

String mode = "";

// Function declarations
void Scenario1();
void Scenario2();
void Scenario3();
void Scenario4();
void Scenario5();
void Scenario6();

void GetVoltage();
void GetCurrent();
void GetPower();
void UpdateBatterySOC();
void PrintValues();

bool setupINA(INA226_WE &sensor, const char* name);
float EstimateBatterySOCFromVoltage(float voltage);
String GetBatteryChargeState(float soc);

bool apply_price_frame(String payload);
bool apply_scenario_frame(String payload);
String get_status();
String GetCsvField(String payload, int fieldIndex);
bool ApplyScenarioThresholds(String payload);
bool IsScenarioSafe(int scenario, float demandW);
String GetScenarioPreRejectReason(int scenario, float demandW);
String GetLoadedValidationRejectReason(int scenario, float demandW);
void ApplyScenario(int scenario);

void setup() {
  Monitor.begin();
  delay(1000);
  Monitor.println("EMS sketch started");

  Bridge.begin();
  Bridge.provide("apply_price_frame", apply_price_frame);
  Bridge.provide("apply_scenario_frame", apply_scenario_frame);
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

  pinMode(LEDS1, OUTPUT);
  pinMode(LEDS2, OUTPUT);
  pinMode(LEDS3, OUTPUT);
  pinMode(LEDS4, OUTPUT);
  pinMode(LEDS5, OUTPUT);
  pinMode(LEDS6, OUTPUT);

  Scenario1();
}

void loop() {
  // Read sensors and calculate power
  GetVoltage();
  GetCurrent();
  GetPower();

  // Estimate battery state
  UpdateBatterySOC();

  if (millis() - lastPrint >= printInterval) {
    lastPrint = millis();
    PrintValues();
  }

  delay(400);
}

bool setupINA(INA226_WE &sensor, const char* name) {
  Monitor.print("Initializing ");
  Monitor.print(name);
  Monitor.print(" ... ");

  if (!sensor.init()) {
    Monitor.println("FAILED");
    return false;
  }

  sensor.setAverage(INA226_AVERAGE_16);
  sensor.setConversionTime(INA226_CONV_TIME_1100);
  sensor.setMeasureMode(INA226_CONTINUOUS);
  sensor.waitUntilConversionCompleted();

  Monitor.println("OK");
  return true;
}

bool apply_price_frame(String payload) {
  if (!payload.startsWith("PRICE,")) {
    return false;
  }

  int firstComma = payload.indexOf(',');
  int secondComma = payload.indexOf(',', firstComma + 1);

  if (firstComma < 0 || secondComma < 0) {
    return false;
  }

  electricityprice = payload.substring(firstComma + 1, secondComma).toFloat();
  priceSlot = payload.substring(secondComma + 1).toInt();
  priceReceived = true;

  Monitor.print("Received price from main.py, slot: ");
  Monitor.print(priceSlot);
  Monitor.print(", price: ");
  Monitor.println(electricityprice, 5);

  return true;
}

bool apply_scenario_frame(String payload) {
  // Format:
  // SCENARIO,<slot>,<scenario>,<demand_mW>,
  // <pv_bat_V>,<pv_bat_mW>,<pv_pem_V>,<pv_pem_mW>,<pv_load_V>,<pv_load_mW>,<safety_mW>
  if (!payload.startsWith("SCENARIO,")) {
    return false;
  }

  if (!ApplyScenarioThresholds(payload)) {
    return false;
  }

  priceSlot = GetCsvField(payload, 1).toInt();
  requestedScenario = GetCsvField(payload, 2).toInt();
  requestedDemand_mW = GetCsvField(payload, 3).toFloat();
  scenarioReceived = true;

  // Use the latest measurements from loop() so the RPC handler stays responsive.
  float demandW = requestedDemand_mW / 1000.0;

  GetVoltage();
  GetCurrent();
  GetPower();

  lastRejectReason = GetScenarioPreRejectReason(requestedScenario, demandW);
  scenarioAccepted = lastRejectReason.length() == 0;

  if (!scenarioAccepted) {
    Scenario1();
    Monitor.print("Requested scenario rejected: ");
    Monitor.println(lastRejectReason);
    return false;
  }

  ApplyScenario(requestedScenario);

  if (requestedScenario == 2 || requestedScenario == 3 || requestedScenario == 4) {
    delay(PV_LOADED_SETTLING_MS);
    GetVoltage();
    GetCurrent();
    GetPower();
    UpdateBatterySOC();

    lastRejectReason = GetLoadedValidationRejectReason(requestedScenario, demandW);
    scenarioAccepted = lastRejectReason.length() == 0;

    if (!scenarioAccepted) {
      Scenario1();
      Monitor.print("Requested scenario rejected after loaded validation: ");
      Monitor.println(lastRejectReason);
      return false;
    }
  }

  Monitor.print("Applied Python scenario: S");
  Monitor.print(requestedScenario);
  Monitor.print(" demand_mW: ");
  Monitor.println(requestedDemand_mW, 1);

  return true;
}

String GetCsvField(String payload, int fieldIndex) {
  int start = 0;
  int end = -1;

  for (int i = 0; i <= fieldIndex; i++) {
    start = end + 1;
    end = payload.indexOf(',', start);

    if (i == fieldIndex) {
      if (end < 0) {
        return payload.substring(start);
      }
      return payload.substring(start, end);
    }

    if (end < 0) {
      return "";
    }
  }

  return "";
}

bool ApplyScenarioThresholds(String payload) {
  if (GetCsvField(payload, 3).length() == 0) {
    return false;
  }

  if (GetCsvField(payload, 10).length() == 0) {
    return true;
  }

  PV_MIN_VOLTAGE_FOR_BATTERY_CHARGING = GetCsvField(payload, 4).toFloat();
  PV_MIN_POWER_FOR_BATTERY_CHARGING = GetCsvField(payload, 5).toFloat() / 1000.0;
  PV_MIN_VOLTAGE_FOR_PEM_CHARGING = GetCsvField(payload, 6).toFloat();
  PV_MIN_POWER_FOR_PEM_CHARGING = GetCsvField(payload, 7).toFloat() / 1000.0;
  PV_MIN_VOLTAGE_FOR_LOAD_SUPPLY = GetCsvField(payload, 8).toFloat();
  PV_MIN_POWER_FOR_LOAD_SUPPLY = GetCsvField(payload, 9).toFloat() / 1000.0;
  SAFETY_MARGIN_W = GetCsvField(payload, 10).toFloat() / 1000.0;

  return true;
}

String get_status() {
  String payload = "";

  payload += "slot=" + String(priceSlot);
  payload += ",price=" + String(electricityprice, 5);

  payload += ",inaBatOk=" + String(inaBatOk ? 1 : 0);
  payload += ",inaLoadOk=" + String(inaLoadOk ? 1 : 0);
  payload += ",inaPVOk=" + String(inaPVOk ? 1 : 0);
  payload += ",inaPEMOk=" + String(inaPEMOk ? 1 : 0);

  payload += ",panelVoltage=" + String(panelVoltage, 5);
  payload += ",batteryVoltage=" + String(batteryVoltage, 5);
  payload += ",pemrfcVoltage=" + String(pemrfcVoltage, 5);
  payload += ",loadVoltage=" + String(loadVoltage, 5);

  payload += ",PVcurrent=" + String(PVcurrent, 5);
  payload += ",Batcurrent=" + String(Batcurrent, 5);
  payload += ",PEMcurrent=" + String(PEMcurrent, 5);
  payload += ",Loadcurrent=" + String(Loadcurrent, 5);

  payload += ",PVshunt_mV=" + String(PVshuntVoltage_mV, 5);
  payload += ",Batshunt_mV=" + String(BatshuntVoltage_mV, 5);
  payload += ",PEMshunt_mV=" + String(PEMshuntVoltage_mV, 5);
  payload += ",Loadshunt_mV=" + String(LoadshuntVoltage_mV, 5);

  payload += ",PVpower=" + String(PVpower, 5);
  payload += ",Batterypower=" + String(Batterypower, 5);
  payload += ",PEMpower=" + String(PEMpower, 5);
  payload += ",Loadpower=" + String(Loadpower, 5);

  payload += ",batterySOC=" + String(batterySOC, 2);
  payload += ",batteryEnergyWh=" + String(batteryEnergyWh, 4);
  payload += ",batteryChargeState=" + batteryChargeState;

  payload += ",mode=" + mode;
  payload += ",priceReceived=" + String(priceReceived ? 1 : 0);
  payload += ",scenarioReceived=" + String(scenarioReceived ? 1 : 0);
  payload += ",scenarioAccepted=" + String(scenarioAccepted ? 1 : 0);
  payload += ",requestedScenario=" + String(requestedScenario);
  payload += ",requestedDemand_mW=" + String(requestedDemand_mW, 1);
  payload += ",pvMinVoltageBatteryCharging=" + String(PV_MIN_VOLTAGE_FOR_BATTERY_CHARGING, 5);
  payload += ",pvMinPowerBatteryCharging=" + String(PV_MIN_POWER_FOR_BATTERY_CHARGING, 5);
  payload += ",pvMinVoltagePEMCharging=" + String(PV_MIN_VOLTAGE_FOR_PEM_CHARGING, 5);
  payload += ",pvMinPowerPEMCharging=" + String(PV_MIN_POWER_FOR_PEM_CHARGING, 5);
  payload += ",pvMinVoltageLoadSupply=" + String(PV_MIN_VOLTAGE_FOR_LOAD_SUPPLY, 5);
  payload += ",pvMinPowerLoadSupply=" + String(PV_MIN_POWER_FOR_LOAD_SUPPLY, 5);
  payload += ",lastRejectReason=" + lastRejectReason;

  return payload;
}

bool IsScenarioSafe(int scenario, float demandW) {
  return GetScenarioPreRejectReason(scenario, demandW).length() == 0;
}

String GetScenarioPreRejectReason(int scenario, float demandW) {
  if (scenario == 1) {
    return "";
  }

  // Open-circuit PV voltage can be measured when PV is disconnected.
  // Open-circuit PV power is approximately zero and cannot represent
  // available power. PV power is only valid after PV is connected.
  if (scenario == 2) {
    if (panelVoltage < PV_MIN_VOLTAGE_FOR_BATTERY_CHARGING) return "PV voltage too low to try battery charging";
    if (batteryVoltage >= BATTERY_MAX_VOLTAGE) return "battery voltage already high";
    if (batterySOC >= BATTERY_FULL_SOC) return "battery SOC already full";
    return "";
  }

  if (scenario == 3) {
    if (panelVoltage < PV_MIN_VOLTAGE_FOR_PEM_CHARGING) return "PV voltage too low to try PEM charging";
    return "";
  }

  if (scenario == 4) {
    if (panelVoltage < PV_MIN_VOLTAGE_FOR_LOAD_SUPPLY) return "PV voltage too low to try load supply";
    return "";
  }

  if (scenario == 5) {
    if (batteryVoltage < BATTERY_MIN_VOLTAGE) return "battery voltage too low";
    if (batterySOC <= BATTERY_LOW_SOC) return "battery SOC too low";
    if (demandW > BATTERY_MAX_DISCHARGE_CURRENT_A * batteryVoltage) return "demand above battery test limit";
    return "";
  }

  if (scenario == 6) {
    if (pemrfcVoltage < PEM_MIN_USABLE_VOLTAGE) return "PEM voltage too low";
    if (demandW > PEM_MAX_DISCHARGE_POWER_W) return "demand above PEM test limit";
    return "";
  }

  return "unknown scenario";
}

String GetLoadedValidationRejectReason(int scenario, float demandW) {
  // After switching S2/S3/S4, the PV is loaded by battery, PEM or load.
  // Corrected PV current and power now represent what the panel can deliver.
  if (scenario == 2) {
    if (PVcurrent <= 0.0) return "PV failed loaded validation for battery charging";
    if (PVpower < PV_MIN_POWER_FOR_BATTERY_CHARGING) return "PV failed loaded validation for battery charging";
    if (batteryVoltage >= BATTERY_MAX_VOLTAGE) return "battery voltage already high";
    if (batterySOC >= BATTERY_FULL_SOC) return "battery SOC already full";
    return "";
  }

  if (scenario == 3) {
    if (PVcurrent <= 0.0) return "PV failed loaded validation for PEM charging";
    if (PVpower < PV_MIN_POWER_FOR_PEM_CHARGING) return "PV failed loaded validation for PEM charging";
    return "";
  }

  if (scenario == 4) {
    if (PVcurrent <= 0.0) return "PV failed loaded validation for load supply";
    if (PVpower < PV_MIN_POWER_FOR_LOAD_SUPPLY) return "PV failed loaded validation for load supply";
    if (PVpower < demandW + SAFETY_MARGIN_W) return "PV cannot cover requested demand after loaded validation";
    return "";
  }

  return "";
}

void ApplyScenario(int scenario) {
  if (scenario == 1) {
    Scenario1();
  } else if (scenario == 2) {
    Scenario2();
  } else if (scenario == 3) {
    Scenario3();
  } else if (scenario == 4) {
    Scenario4();
  } else if (scenario == 5) {
    Scenario5();
  } else if (scenario == 6) {
    Scenario6();
  } else {
    Scenario1();
  }
}

void GetVoltage() {
  nominalVoltage = 5.0;

  if (inaBatOk) {
    inaBat.readAndClearFlags();
    batteryVoltage = inaBat.getBusVoltage_V();
  }

  if (inaLoadOk) {
    inaLoad.readAndClearFlags();
    loadVoltage = inaLoad.getBusVoltage_V();
  }

  if (inaPVOk) {
    inaPV.readAndClearFlags();
    panelVoltage = inaPV.getBusVoltage_V() - PV_VOLTAGE_CORRECTION_V;
  }

  if (inaPEMOk) {
    inaPEM.readAndClearFlags();
    pemrfcVoltage = inaPEM.getBusVoltage_V() - PEM_VOLTAGE_CORRECTION_V;
  }
}

void GetCurrent() {
  if (inaBatOk) {
    BatshuntVoltage_mV = inaBat.getShuntVoltage_mV();
    Batcurrent = inaBat.getCurrent_mA() / 1000.0;
  }

  if (inaLoadOk) {
    LoadshuntVoltage_mV = inaLoad.getShuntVoltage_mV();
    Loadcurrent = inaLoad.getCurrent_mA() / 1000.0;
  }

  if (inaPVOk) {
    PVshuntVoltage_mV = inaPV.getShuntVoltage_mV();
    PVcurrent = (inaPV.getCurrent_mA() / 1000.0) + PV_CURRENT_CORRECTION_A;
  }

  if (inaPEMOk) {
    PEMshuntVoltage_mV = inaPEM.getShuntVoltage_mV();
    PEMcurrent = PEM_CURRENT_SCALE * (inaPEM.getCurrent_mA() / 1000.0) + PEM_CURRENT_OFFSET_A;
  }
}

void GetPower() {
  if (inaPVOk) {
    PVpower = panelVoltage * PVcurrent;
  }

  if (inaLoadOk) {
    Loadpower = inaLoad.getBusPower() / 1000.0;
  }

  if (inaPEMOk) {
    PEMpower = pemrfcVoltage * PEMcurrent;
  }

  if (inaBatOk) {
    Batterypower = inaBat.getBusPower() / 1000.0;
  }
}

float EstimateBatterySOCFromVoltage(float voltage) {
  float soc = (voltage - BATTERY_EMPTY_TEST_VOLTAGE) * 100.0;
  soc = soc / (BATTERY_FULL_TEST_VOLTAGE - BATTERY_EMPTY_TEST_VOLTAGE);

  if (soc < 0.0) {
    soc = 0.0;
  }

  if (soc > 100.0) {
    soc = 100.0;
  }

  return soc;
}

void UpdateBatterySOC() {
  unsigned long currentTime = millis();

  // First estimate is based on measured voltage
  if (lastBatterySOCUpdate == 0) {
    batterySOC = EstimateBatterySOCFromVoltage(batteryVoltage);
    batteryEnergyWh = BATTERY_USABLE_ENERGY_WH * batterySOC / 100.0;
    lastBatterySOCUpdate = currentTime;
    batteryChargeState = GetBatteryChargeState(batterySOC);
    return;
  }

  float dtHours = (currentTime - lastBatterySOCUpdate) / 3600000.0;
  lastBatterySOCUpdate = currentTime;

  // Positive battery power charges, negative battery power discharges
  batteryEnergyWh += Batterypower * dtHours;

  if (batteryEnergyWh < 0.0) {
    batteryEnergyWh = 0.0;
  }

  if (batteryEnergyWh > BATTERY_USABLE_ENERGY_WH) {
    batteryEnergyWh = BATTERY_USABLE_ENERGY_WH;
  }

  batterySOC = 100.0 * batteryEnergyWh / BATTERY_USABLE_ENERGY_WH;
  batteryChargeState = GetBatteryChargeState(batterySOC);
}

String GetBatteryChargeState(float soc) {
  if (soc <= 10.0) {
    return "empty";
  } else if (soc <= 30.0) {
    return "low";
  } else if (soc <= 70.0) {
    return "medium";
  } else if (soc <= 90.0) {
    return "high";
  } else {
    return "full";
  }
}

void PrintValues() {
  Monitor.print("INA OK Bat/Load/PV/PEM: ");
  Monitor.print(inaBatOk ? 1 : 0);
  Monitor.print("/");
  Monitor.print(inaLoadOk ? 1 : 0);
  Monitor.print("/");
  Monitor.print(inaPVOk ? 1 : 0);
  Monitor.print("/");
  Monitor.print(inaPEMOk ? 1 : 0);

  Monitor.print(" Nominal Voltage: ");
  Monitor.print(nominalVoltage);

  Monitor.print(" PV Current: ");
  Monitor.print(PVcurrent, 3);
  Monitor.print(" PV Shunt mV: ");
  Monitor.print(PVshuntVoltage_mV, 3);
  Monitor.print(" PV Voltage: ");
  Monitor.print(panelVoltage, 3);
  Monitor.print(" PV Power: ");
  Monitor.print(PVpower, 3);

  Monitor.print(" Battery Voltage: ");
  Monitor.print(batteryVoltage, 3);
  Monitor.print(" Battery Current: ");
  Monitor.print(Batcurrent, 3);
  Monitor.print(" Battery Shunt mV: ");
  Monitor.print(BatshuntVoltage_mV, 3);
  Monitor.print(" Battery Power: ");
  Monitor.print(Batterypower, 3);
  Monitor.print(" Battery SOC: ");
  Monitor.print(batterySOC, 1);
  Monitor.print(" Battery State: ");
  Monitor.print(batteryChargeState);

  Monitor.print(" Load Current: ");
  Monitor.print(Loadcurrent, 3);
  Monitor.print(" Load Shunt mV: ");
  Monitor.print(LoadshuntVoltage_mV, 3);
  Monitor.print(" Load Voltage: ");
  Monitor.print(loadVoltage, 3);
  Monitor.print(" Load Power: ");
  Monitor.print(Loadpower, 3);

  Monitor.print(" PEM RFC Current: ");
  Monitor.print(PEMcurrent, 3);
  Monitor.print(" PEM RFC Shunt mV: ");
  Monitor.print(PEMshuntVoltage_mV, 3);
  Monitor.print(" PEM RFC Voltage: ");
  Monitor.print(pemrfcVoltage, 3);
  Monitor.print(" PEM RFC Power: ");
  Monitor.print(PEMpower, 3);

  Monitor.print(" Electricity price: ");
  Monitor.print(electricityprice, 5);
  Monitor.print(" Price slot: ");
  Monitor.print(priceSlot);
  Monitor.print(" Mode: ");
  Monitor.println(mode);
}

void Scenario1() {
  // Grid supplies load
  digitalWrite(K1, HIGH);
  digitalWrite(K2, LOW);
  digitalWrite(K3, HIGH);
  digitalWrite(K4, HIGH);
  digitalWrite(K5, HIGH);
  digitalWrite(K6, HIGH);
  digitalWrite(K7, HIGH);

  mode = "S1 Load from grid PV off battery off PEM off";

  digitalWrite(LEDS1, HIGH);
  digitalWrite(LEDS2, LOW);
  digitalWrite(LEDS3, LOW);
  digitalWrite(LEDS4, LOW);
  digitalWrite(LEDS5, LOW);
  digitalWrite(LEDS6, LOW);
}

void Scenario2() {
  // Grid supplies load and PV charges battery
  digitalWrite(K1, HIGH);
  digitalWrite(K2, LOW);
  digitalWrite(K3, LOW);
  digitalWrite(K4, HIGH);
  digitalWrite(K5, HIGH);
  digitalWrite(K6, HIGH);
  digitalWrite(K7, LOW);

  mode = "S2 Load from grid PV charges battery PEM off";

  digitalWrite(LEDS1, LOW);
  digitalWrite(LEDS2, HIGH);
  digitalWrite(LEDS3, LOW);
  digitalWrite(LEDS4, LOW);
  digitalWrite(LEDS5, LOW);
  digitalWrite(LEDS6, LOW);
}

void Scenario3() {
  // Grid supplies load and PV charges PEM
  digitalWrite(K1, HIGH);
  digitalWrite(K2, LOW);
  digitalWrite(K3, HIGH);
  digitalWrite(K4, LOW);
  digitalWrite(K5, HIGH);
  digitalWrite(K6, HIGH);
  digitalWrite(K7, LOW);

  mode = "S3 Load from grid PV charges PEM battery off";

  digitalWrite(LEDS1, LOW);
  digitalWrite(LEDS2, LOW);
  digitalWrite(LEDS3, HIGH);
  digitalWrite(LEDS4, LOW);
  digitalWrite(LEDS5, LOW);
  digitalWrite(LEDS6, LOW);
}

void Scenario4() {
  // PV supplies load
  digitalWrite(K1, LOW);
  digitalWrite(K2, HIGH);
  digitalWrite(K3, HIGH);
  digitalWrite(K4, HIGH);
  digitalWrite(K5, HIGH);
  digitalWrite(K6, HIGH);
  digitalWrite(K7, LOW);

  mode = "S4 Load from PV battery off PEM off";

  digitalWrite(LEDS1, LOW);
  digitalWrite(LEDS2, LOW);
  digitalWrite(LEDS3, LOW);
  digitalWrite(LEDS4, HIGH);
  digitalWrite(LEDS5, LOW);
  digitalWrite(LEDS6, LOW);
}

void Scenario5() {
  // Battery supplies load
  digitalWrite(K1, LOW);
  digitalWrite(K2, LOW);
  digitalWrite(K3, HIGH);
  digitalWrite(K4, HIGH);
  digitalWrite(K5, LOW);
  digitalWrite(K6, HIGH);
  digitalWrite(K7, HIGH);

  mode = "S5 Load from battery PEM off PV off";

  digitalWrite(LEDS1, LOW);
  digitalWrite(LEDS2, LOW);
  digitalWrite(LEDS3, LOW);
  digitalWrite(LEDS4, LOW);
  digitalWrite(LEDS5, HIGH);
  digitalWrite(LEDS6, LOW);
}

void Scenario6() {
  // PEM supplies load
  digitalWrite(K1, LOW);
  digitalWrite(K2, LOW);
  digitalWrite(K3, HIGH);
  digitalWrite(K4, HIGH);
  digitalWrite(K5, HIGH);
  digitalWrite(K6, LOW);
  digitalWrite(K7, HIGH);

  mode = "S6 Load from PEM battery off PV off";

  digitalWrite(LEDS1, LOW);
  digitalWrite(LEDS2, LOW);
  digitalWrite(LEDS3, LOW);
  digitalWrite(LEDS4, LOW);
  digitalWrite(LEDS5, LOW);
  digitalWrite(LEDS6, HIGH);
}
