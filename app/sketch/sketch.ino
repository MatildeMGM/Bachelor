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
const int LEDS1 = 21;
const int LEDS2 = 0;
const int LEDS3 = 20;
const int LEDS4 = 6;
const int LEDS5 = 1;
const int LEDS6 = 13;

// Price variables
unsigned long previousMillis = 0;
const long period = 20000;
int priceSlot = 0;
float electricityprice = 0.0;
bool priceReceived = false;

// PEMRFC time variables
const long period2 = 60000;
unsigned long starttime = 0;
bool PEM_flag = false;

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

float PVpower = 0.0;
float Loadpower = 0.0;
float PEMpower = 0.0;
float Batterypower = 0.0;

// Battery SOC variables
float batterySOC = 0.0;
float batteryEnergyWh = 0.0;
unsigned long lastBatterySOCUpdate = 0;
String batteryChargeState = "";

// Printing variables
unsigned long lastPrint = 0;
const long printInterval = 2000;

String mode = "";

// Initial status
bool pemCharged = true;
bool batCharged = true;

// Function declarations
void Scenario1();
void Scenario2();
void Scenario3();
void Scenario4();
void Scenario5();
void Scenario6();

void HighPriceScheme();
void LowPriceScheme();

void GetVoltage();
void GetCurrent();
void GetPower();
void UpdateBatterySOC();
void UpdatePrices();
void PrintValues();
void CSVPrintValues();

void setupINA(INA226_WE &sensor, const char* name);
float EstimateBatterySOCFromVoltage(float voltage);
String GetBatteryChargeState(float soc);

bool apply_price_frame(String payload);
String get_status();

void setup() {
  Monitor.begin();
  delay(1000);
  Monitor.println("EMS sketch started");

  Bridge.begin();
  Bridge.provide("apply_price_frame", apply_price_frame);
  Bridge.provide("get_status", get_status);

  Wire.begin();
  delay(500);

  setupINA(inaBat, "INA226 Battery");
  setupINA(inaLoad, "INA226 Load");
  setupINA(inaPV, "INA226 PV");
  setupINA(inaPEM, "INA226 PEMRFC");

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
  Monitor.println("loop alive");
  delay(1000);

  UpdatePrices();

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

  // Select price scheme
  if (electricityprice >= 0.6) {
    HighPriceScheme();
  } else {
    LowPriceScheme();
  }

  delay(400);

  // Reset PEM charging timer when PEM is not charging
  if (digitalRead(K4) == HIGH) {
    starttime = 0;
    PEM_flag = false;
  }
}

void setupINA(INA226_WE &sensor, const char* name) {
  Monitor.print("Initializing ");
  Monitor.print(name);
  Monitor.print(" ... ");

  if (!sensor.init()) {
    Monitor.println("FAILED");
    return;
  }

  sensor.setAverage(INA226_AVERAGE_16);
  sensor.setConversionTime(INA226_CONV_TIME_1100);
  sensor.setMeasureMode(INA226_CONTINUOUS);
  sensor.waitUntilConversionCompleted();

  Monitor.println("OK");
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

String get_status() {
  String payload = "";

  payload += "slot=" + String(priceSlot);
  payload += ",price=" + String(electricityprice, 5);

  payload += ",panelVoltage=" + String(panelVoltage, 5);
  payload += ",batteryVoltage=" + String(batteryVoltage, 5);
  payload += ",pemrfcVoltage=" + String(pemrfcVoltage, 5);
  payload += ",loadVoltage=" + String(loadVoltage, 5);

  payload += ",PVcurrent=" + String(PVcurrent, 5);
  payload += ",Batcurrent=" + String(Batcurrent, 5);
  payload += ",PEMcurrent=" + String(PEMcurrent, 5);
  payload += ",Loadcurrent=" + String(Loadcurrent, 5);

  payload += ",PVpower=" + String(PVpower, 5);
  payload += ",Batterypower=" + String(Batterypower, 5);
  payload += ",PEMpower=" + String(PEMpower, 5);
  payload += ",Loadpower=" + String(Loadpower, 5);

  payload += ",batterySOC=" + String(batterySOC, 2);
  payload += ",batteryEnergyWh=" + String(batteryEnergyWh, 4);
  payload += ",batteryChargeState=" + batteryChargeState;

  payload += ",mode=" + mode;
  payload += ",priceReceived=" + String(priceReceived ? 1 : 0);

  return payload;
}

void HighPriceScheme() {
  // High price: prefer PV, then battery, then PEM, then grid
  if ((digitalRead(K1) == LOW && digitalRead(K2) == HIGH && digitalRead(K7) == LOW && loadVoltage > 0.15) || panelVoltage > 2.0) {
    Scenario4();
  } else if (batCharged && batteryVoltage > BATTERY_MIN_VOLTAGE && batterySOC > BATTERY_LOW_SOC) {
    Scenario5();
  } else if ((digitalRead(K1) == LOW && digitalRead(K6) == LOW && loadVoltage > 0.2) || (pemCharged && pemrfcVoltage > 0.5)) {
    Scenario6();
    batCharged = false;
  } else {
    pemCharged = false;
    batCharged = false;
    Scenario1();
  }
}

void LowPriceScheme() {
  // Low price: use grid for load and charge storage from PV
  if (panelVoltage > 2.0 || PEM_flag == true) {
    if (((digitalRead(K3) == LOW && digitalRead(K5) == HIGH &&
          batteryVoltage < BATTERY_MAX_VOLTAGE &&
          batterySOC < BATTERY_FULL_SOC &&
          Batcurrent < BATTERY_MAX_CHARGE_CURRENT_A &&
          PEM_flag == false)) ||
        ((batteryVoltage < BATTERY_MAX_VOLTAGE &&
          batterySOC < BATTERY_FULL_SOC &&
          Batcurrent < BATTERY_MAX_CHARGE_CURRENT_A &&
          PEM_flag == false))) {

      Scenario2();

      if (batterySOC >= BATTERY_FULL_SOC || batteryVoltage >= BATTERY_FULL_TEST_VOLTAGE) {
        batCharged = true;
      }

    } else if (PEMcurrent >= -0.1) {
      Scenario3();
      PEM_flag = true;

      if (pemCharged == false && starttime == 0) {
        starttime = millis();
      }

      if (millis() - starttime >= period2) {
        pemCharged = true;
      }

    } else {
      Scenario1();
    }
  } else {
    Scenario1();
  }
}

void GetVoltage() {
  nominalVoltage = 5.0;

  batteryVoltage = inaBat.getBusVoltage_V();
  loadVoltage    = inaLoad.getBusVoltage_V();
  panelVoltage   = inaPV.getBusVoltage_V();
  pemrfcVoltage  = inaPEM.getBusVoltage_V();
}

void GetCurrent() {
  Batcurrent  = inaBat.getCurrent_mA() / 1000.0;
  Loadcurrent = inaLoad.getCurrent_mA() / 1000.0;
  PVcurrent   = inaPV.getCurrent_mA() / 1000.0;
  PEMcurrent  = inaPEM.getCurrent_mA() / 1000.0;
}

void GetPower() {
  PVpower      = PVcurrent * panelVoltage;
  Loadpower    = Loadcurrent * loadVoltage;
  PEMpower     = PEMcurrent * pemrfcVoltage;
  Batterypower = Batcurrent * batteryVoltage;
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

void UpdatePrices() {
  // Price and slot are provided by main.py through Bridge
}

void PrintValues() {
  Monitor.print("Nominal Voltage: ");
  Monitor.print(nominalVoltage);

  Monitor.print(" PV Current: ");
  Monitor.print(PVcurrent, 3);
  Monitor.print(" PV Voltage: ");
  Monitor.print(panelVoltage, 3);
  Monitor.print(" PV Power: ");
  Monitor.print(PVpower, 3);

  Monitor.print(" Battery Voltage: ");
  Monitor.print(batteryVoltage, 3);
  Monitor.print(" Battery Current: ");
  Monitor.print(Batcurrent, 3);
  Monitor.print(" Battery Power: ");
  Monitor.print(Batterypower, 3);
  Monitor.print(" Battery SOC: ");
  Monitor.print(batterySOC, 1);
  Monitor.print(" Battery State: ");
  Monitor.print(batteryChargeState);

  Monitor.print(" Load Current: ");
  Monitor.print(Loadcurrent, 3);
  Monitor.print(" Load Voltage: ");
  Monitor.print(loadVoltage, 3);
  Monitor.print(" Load Power: ");
  Monitor.print(Loadpower, 3);

  Monitor.print(" PEM RFC Current: ");
  Monitor.print(PEMcurrent, 3);
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

void CSVPrintValues() {
  Monitor.print(priceSlot);
  Monitor.print(",");
  Monitor.print(electricityprice);
  Monitor.print(",");
  Monitor.print(panelVoltage);
  Monitor.print(",");
  Monitor.print(PVcurrent);
  Monitor.print(",");
  Monitor.print(PVpower);
  Monitor.print(",");
  Monitor.print(batteryVoltage);
  Monitor.print(",");
  Monitor.print(Batcurrent);
  Monitor.print(",");
  Monitor.print(Batterypower);
  Monitor.print(",");
  Monitor.print(batterySOC);
  Monitor.print(",");
  Monitor.print(batteryEnergyWh);
  Monitor.print(",");
  Monitor.print(batteryChargeState);
  Monitor.print(",");
  Monitor.print(pemrfcVoltage);
  Monitor.print(",");
  Monitor.print(PEMcurrent);
  Monitor.print(",");
  Monitor.print(PEMpower);
  Monitor.print(",");
  Monitor.print(loadVoltage);
  Monitor.print(",");
  Monitor.print(Loadcurrent);
  Monitor.print(",");
  Monitor.print(Loadpower);
  Monitor.print(",");
  Monitor.print(batCharged);
  Monitor.print(",");
  Monitor.print(pemCharged);
  Monitor.print(",");
  Monitor.print(mode);
  Monitor.print("\n");
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