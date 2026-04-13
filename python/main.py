#include <Arduino_RouterBridge.h>

// Pin definitions
const int K1 = 8;   // Digital pin for Relay1 control
const int K2 = 2;   // Digital pin for Relay2 control
const int K3 = 3;   // Digital pin for Relay3 control
const int K4 = 4;   // Digital pin for Relay4 control
const int K5 = 5;   // Digital pin for Relay5 control
const int K6 = 7;   // Digital pin for Relay6 control
const int K7 = 6;   // Digital pin for Relay7 control

const int LEDS1 = 13;
const int LEDS2 = 12;
const int LEDS3 = 11;
const int LEDS4 = 10;
const int LEDS5 = 9;
const int LEDS6 = A4;

// Analog voltage pins
const int batteryVoltagePin = A1;  // analog input pin for battery voltage measurement
const int pemrfcVoltagePin  = A2;  // analog input pin for PEMRFC voltage measurement
const int panelVoltagePin   = A3;  // analog input pin for PV voltage measurement
const int loadVoltagePin    = A5;  // analog input pin for load voltage measurement

// Multiplexer pin definition
const int selectPins[3] = {10, 11, 12}; // S0, S1, S2
const int zInput = A0;                  // Connect common (Z) to A0 (analog input)

// Electricity price time management
unsigned long previousMillis = 0;
const long period = 20000; // Period at which energy prices should change if no fresh price arrives
int hour = 0;
float electricityprice = 0.0;
bool priceReceived = false;

// App start/stop heartbeat management
unsigned long lastHeartbeat = 0;
const unsigned long heartbeatTimeout = 2000;
bool appRunning = false;

// PEMRFC time management
const long period2 = 60000; // Period at which PEMRFC gets status charged
unsigned long starttime = 0;
bool PEM_flag = false;

// Voltage divider coefficients: (R1+R2)/R2
const float batteryVoltageDivider = 1.5557;  // voltage divider factor for battery voltage measurement
const float panelVoltageDivider   = 1.5557;  // voltage divider factor for PV panel voltage measurement
const float pemrfcVoltageDivider  = 1.5557;  // voltage divider factor for PEM RFC voltage measurement
const float loadVoltageDivider    = 1.55416; // voltage divider factor for load voltage measurement
const float nominalVoltageDivider = 1.45829; // voltage divider factor for nominal voltage measurement

// Declaring global variables for sensor data
float nominalVoltage = 5.0;
float panelVoltage = 0.0;
float loadVoltage = 0.0;
float pemrfcVoltage = 0.0;
float batteryVoltage = 0.0;
float batterySOC = 0.0;

unsigned int x = 0;
float SensorValuePV   = 0.0, SamplesPV   = 0.0, AvgAcsPV   = 0.0, PVcurrent   = 0.0;
float SensorValueLoad = 0.0, SamplesLoad = 0.0, AvgAcsLoad = 0.0, Loadcurrent = 0.0;
float SensorValuePEM  = 0.0, SamplesPEM  = 0.0, AvgAcsPEM  = 0.0, PEMcurrent  = 0.0;
float SensorValueBat  = 0.0, SamplesBat  = 0.0, AvgAcsBat  = 0.0, Batcurrent  = 0.0;

float PVpower = 0.0;
float Loadpower = 0.0;
float PEMpower = 0.0;
float Batterypower = 0.0;

int waterlevel = 0;
String mode = "";

// Battery and PEM gets status charged when running script
bool pemCharged = true;
bool batCharged = true;

// Optional manual scenario override
int manualScenario = 0;

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
void UpdatePrices();
void PrintValues();
void HMI();
void selectMuxPin(byte pin);
void SafeState();
void heartbeat();

bool apply_price_frame(String payload);
bool apply_override_frame(String payload);

void setup() {
  Serial.begin(9600);
  Serial.println("EMS sketch started");

  // Initialize Bridge
  Bridge.begin();
  Bridge.provide("apply_price_frame", apply_price_frame);
  Bridge.provide("apply_override_frame", apply_override_frame);
  Bridge.provide("heartbeat", heartbeat);

  // Initialize the pinmodes
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

  pinMode(batteryVoltagePin, INPUT);
  pinMode(pemrfcVoltagePin, INPUT);
  pinMode(loadVoltagePin, INPUT);
  pinMode(panelVoltagePin, INPUT);

  pinMode(selectPins[0], OUTPUT);
  pinMode(selectPins[1], OUTPUT);
  pinMode(selectPins[2], OUTPUT);
  pinMode(zInput, INPUT); // Set up Z as an input

  // Startup blink
  digitalWrite(LEDS1, HIGH);
  digitalWrite(LEDS2, HIGH);
  delay(1000);
  digitalWrite(LEDS1, LOW);
  digitalWrite(LEDS2, LOW);

  // Begin scenario 1
  Scenario1();
}

void loop() {
  // App stop / watchdog handling
  if (millis() - lastHeartbeat > heartbeatTimeout) {
    appRunning = false;
  }

  if (!appRunning) {
    SafeState();
    delay(100);
    return;
  }

  GetVoltage();     // Voltage measurements
  GetCurrent();     // Current measurements
  GetPower();       // Get power calculations
  UpdatePrices();   // Optional local time stepping if price updates stop coming
  PrintValues();    // Printing values
  HMI();            // Placeholder for serial/HMI output if needed later

  if (manualScenario >= 1 && manualScenario <= 6) {
    if (manualScenario == 1) Scenario1();
    else if (manualScenario == 2) Scenario2();
    else if (manualScenario == 3) Scenario3();
    else if (manualScenario == 4) Scenario4();
    else if (manualScenario == 5) Scenario5();
    else if (manualScenario == 6) Scenario6();
  } else {
    if (electricityprice >= 0.6) {
      HighPriceScheme(); // Discharge
    } else if (electricityprice < 0.6) {
      LowPriceScheme();  // Charge
    }
  }

  delay(400);

  // PEM charging time handling
  if (digitalRead(K4) == HIGH) {
    starttime = 0;
    PEM_flag = false;
  }
}

void heartbeat() {
  appRunning = true;
  lastHeartbeat = millis();
}

void SafeState() {
  // Keep all relay outputs HIGH/LOW exactly as desired for your fail-safe.
  // Here I use Scenario1 because it is the original "load from grid" fallback.
  Scenario1();
  mode = "App stopped / Safe state";
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
  hour = payload.substring(secondComma + 1).toInt();
  priceReceived = true;

  Serial.print("USED PRICE: ");
  Serial.println(electricityprice, 3);
  Serial.print("USED HOUR: ");
  Serial.println(hour);

  return true;
}

bool apply_override_frame(String payload) {
  if (!payload.startsWith("OVERRIDE,")) {
    return false;
  }

  int comma = payload.indexOf(',');
  if (comma < 0) {
    return false;
  }

  manualScenario = payload.substring(comma + 1).toInt();

  Serial.print("MANUAL SCENARIO: ");
  Serial.println(manualScenario);

  return true;
}

void HighPriceScheme() {
  if ((digitalRead(K1) == LOW && digitalRead(K2) == HIGH && digitalRead(K7) == LOW && loadVoltage > 0.15) || panelVoltage > 2.0) {
    Scenario4();
  } else if (batCharged && batteryVoltage > 2.6) {
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
  if (panelVoltage > 2.0 || PEM_flag == true) {
    if ((digitalRead(K3) == LOW && digitalRead(K5) == HIGH && batteryVoltage < 3.805 && Batcurrent >= -0.1 && PEM_flag == false) ||
        (Batcurrent >= -0.1 && batteryVoltage <= 3.66 && PEM_flag == false)) {
      Scenario2();
      if (batteryVoltage > 2.75) {
        batCharged = true;
      }
    } else if (PEMcurrent >= -0.1) {
      Scenario3();
      PEM_flag = true;
      if (pemCharged == false && starttime == 0) {
        starttime = millis(); // store the current time
      }
      if (millis() - starttime >= period2) { // check if 60000ms have passed
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
  selectMuxPin(2);
  nominalVoltage = (analogRead(zInput) / 1023.0) * 5 * nominalVoltageDivider;      // Read nominal voltage
  loadVoltage    = (analogRead(loadVoltagePin) / 1023.0) * 5 * loadVoltageDivider;  // Read load voltage
  panelVoltage   = (analogRead(panelVoltagePin) / 1023.0) * 5 * panelVoltageDivider; // Read PV voltage
  pemrfcVoltage  = (analogRead(pemrfcVoltagePin) / 1023.0) * 5 * pemrfcVoltageDivider; // Read PEM RFC voltage
  batteryVoltage = (analogRead(batteryVoltagePin) / 1023.0) * 5 * batteryVoltageDivider; // Read battery voltage
}

void GetCurrent() {
  x = 0;
  SensorValuePV = 0.0;   SamplesPV = 0.0;   AvgAcsPV = 0.0;   PVcurrent = 0.0;
  SensorValueLoad = 0.0; SamplesLoad = 0.0; AvgAcsLoad = 0.0; Loadcurrent = 0.0;
  SensorValuePEM = 0.0;  SamplesPEM = 0.0;  AvgAcsPEM = 0.0;  PEMcurrent = 0.0;
  SensorValueBat = 0.0;  SamplesBat = 0.0;  AvgAcsBat = 0.0;  Batcurrent = 0.0;

  for (int x = 0; x < 300; x++) { // Get 300 samples
    // PEM current measurement
    selectMuxPin(1); // Select muxpin
    SensorValuePEM = analogRead(zInput); // and read Z

    // Load current measurement
    selectMuxPin(0); // Select muxpin
    SensorValueLoad = analogRead(zInput); // and read Z

    // PV current measurement
    SensorValuePV = analogRead(A3);

    // Battery current measurement
    selectMuxPin(3); // Select muxpin
    SensorValueBat = analogRead(zInput); // and read Z

    // Add samples together
    SamplesPV   += SensorValuePV;
    SamplesLoad += SensorValueLoad;
    SamplesPEM  += SensorValuePEM;
    SamplesBat  += SensorValueBat;

    delay(3); // let ADC settle before next sample 3ms
  }

  // Taking average of samples:
  AvgAcsPV   = SamplesPV / 300.0;
  AvgAcsLoad = SamplesLoad / 300.0;
  AvgAcsPEM  = SamplesPEM / 300.0;
  AvgAcsBat  = SamplesBat / 300.0;

  // Calculating currents
  PVcurrent   = ((AvgAcsPV   * (5 / 1023.0) - nominalVoltage / 2) / 0.4413) + 0.09;
  Loadcurrent = ((AvgAcsLoad * (5 / 1023.0) - nominalVoltage / 2) / 0.2487) + 0.02;
  PEMcurrent  = ((AvgAcsPEM  * (5 / 1023.0) - nominalVoltage / 2) / 0.4749) + 0.091;
  Batcurrent  = ((AvgAcsBat  * (5 / 1023.0) - nominalVoltage / 2) / 0.3276) + 0.09;
}

void GetPower() {
  // Calculating power:
  PVpower      = PVcurrent * panelVoltage;
  Loadpower    = Loadcurrent * loadVoltage;
  PEMpower     = PEMcurrent * pemrfcVoltage;
  Batterypower = Batcurrent * batteryVoltage;
}

void UpdatePrices() {
  // I dit nye setup er prisen i praksis styret af main.py.
  // Denne funktion bruges kun som fallback, hvis appen holder op med at sende nye værdier.
  unsigned long currentMillis = millis();
  if (currentMillis - previousMillis >= period) {
    previousMillis = currentMillis;

    if (hour == 23) {
      hour = 0;
    } else {
      hour = hour + 1;
    }
  }
}

void HMI() {
  // Placeholder:
  // Her kan du senere sende måleværdier tilbage via Serial/Bridge/WebUI hvis du ønsker.
}

void selectMuxPin(byte pin) {
  for (int i = 0; i < 3; i++) {
    if (pin & (1 << i)) {
      digitalWrite(selectPins[i], HIGH);
    } else {
      digitalWrite(selectPins[i], LOW);
    }
  }
}

void PrintValues() {
  Serial.print("Hour: ");
  Serial.print(hour);
  Serial.print(" Price: ");
  Serial.print(electricityprice, 3);
  Serial.print(" Price received: ");
  Serial.print(priceReceived);

  Serial.print(" Nominal Voltage: ");
  Serial.print(nominalVoltage, 3);

  Serial.print(" PV Current: ");
  Serial.print(PVcurrent, 3);
  Serial.print(" PV Voltage: ");
  Serial.print(panelVoltage, 3);
  Serial.print(" PV Power: ");
  Serial.print(PVpower, 3);

  Serial.print(" Battery Voltage: ");
  Serial.print(batteryVoltage, 3);
  Serial.print(" Battery Current: ");
  Serial.print(Batcurrent, 3);
  Serial.print(" Battery Power: ");
  Serial.print(Batterypower, 3);

  Serial.print(" Load Current: ");
  Serial.print(Loadcurrent, 3);
  Serial.print(" Load Voltage: ");
  Serial.print(loadVoltage, 3);
  Serial.print(" Load Power: ");
  Serial.print(Loadpower, 3);

  Serial.print(" PEM RFC Current: ");
  Serial.print(PEMcurrent, 3);
  Serial.print(" PEM RFC Voltage: ");
  Serial.print(pemrfcVoltage, 3);
  Serial.print(" PEM RFC Power: ");
  Serial.print(PEMpower, 3);

  Serial.print(" Mode: ");
  Serial.println(mode);
}

// Scenario 1:
// Load receives power from grid, PV OFF, Battery OFF, PEM RFC OFF
void Scenario1() {
  digitalWrite(K1, HIGH);
  digitalWrite(K2, LOW);
  digitalWrite(K3, HIGH);
  digitalWrite(K4, HIGH);
  digitalWrite(K5, HIGH);
  digitalWrite(K6, HIGH);
  digitalWrite(K7, HIGH);
  mode = "Load receives power from grid PV OFF Battery OFF PEM RFC OFF";
  digitalWrite(LEDS1, HIGH);
  digitalWrite(LEDS2, LOW);
  digitalWrite(LEDS3, LOW);
  digitalWrite(LEDS4, LOW);
  digitalWrite(LEDS5, LOW);
  digitalWrite(LEDS6, LOW);
}

// Scenario 2:
// Load receives power from grid, PV Charges battery, PEM RFC OFF
void Scenario2() {
  digitalWrite(K1, HIGH);
  digitalWrite(K2, LOW);
  digitalWrite(K3, LOW);
  digitalWrite(K4, HIGH);
  digitalWrite(K5, HIGH);
  digitalWrite(K6, HIGH);
  digitalWrite(K7, LOW);
  mode = "Load receives power from grid PV Charges battery PEM RFC OFF";
  digitalWrite(LEDS1, LOW);
  digitalWrite(LEDS2, HIGH);
  digitalWrite(LEDS3, LOW);
  digitalWrite(LEDS4, LOW);
  digitalWrite(LEDS5, LOW);
  digitalWrite(LEDS6, LOW);
}

// Scenario 3:
// Load receives power from grid, PV Charges PEM RFC, battery OFF
void Scenario3() {
  digitalWrite(K1, HIGH);
  digitalWrite(K2, LOW);
  digitalWrite(K3, HIGH);
  digitalWrite(K4, LOW);
  digitalWrite(K5, HIGH);
  digitalWrite(K6, HIGH);
  digitalWrite(K7, LOW);
  mode = "Load receives power from grid PV Charges PEM RFC battery OFF";
  digitalWrite(LEDS1, LOW);
  digitalWrite(LEDS2, LOW);
  digitalWrite(LEDS3, HIGH);
  digitalWrite(LEDS4, LOW);
  digitalWrite(LEDS5, LOW);
  digitalWrite(LEDS6, LOW);
}

// Scenario 4:
// Load receives power from PV only, battery OFF, PEM RFC OFF
void Scenario4() {
  digitalWrite(K1, LOW);
  digitalWrite(K2, HIGH);
  digitalWrite(K3, HIGH);
  digitalWrite(K4, HIGH);
  digitalWrite(K5, HIGH);
  digitalWrite(K6, HIGH);
  digitalWrite(K7, LOW);
  mode = "Load receives power from PV battery OFF PEM RFC OFF";
  digitalWrite(LEDS1, LOW);
  digitalWrite(LEDS2, LOW);
  digitalWrite(LEDS3, LOW);
  digitalWrite(LEDS4, HIGH);
  digitalWrite(LEDS5, LOW);
  digitalWrite(LEDS6, LOW);
}

// Scenario 5:
// Load receives power from battery, PEM RFC OFF, PV OFF
void Scenario5() {
  digitalWrite(K1, LOW);
  digitalWrite(K2, LOW);
  digitalWrite(K3, HIGH);
  digitalWrite(K4, HIGH);
  digitalWrite(K5, LOW);
  digitalWrite(K6, HIGH);
  digitalWrite(K7, HIGH);
  mode = "Load receives power from battery PEM RFC OFF PV OFF";
  digitalWrite(LEDS1, LOW);
  digitalWrite(LEDS2, LOW);
  digitalWrite(LEDS3, LOW);
  digitalWrite(LEDS4, LOW);
  digitalWrite(LEDS5, HIGH);
  digitalWrite(LEDS6, LOW);
}

// Scenario 6:
// Load receives power from PEM, Battery OFF, PV OFF
void Scenario6() {
  digitalWrite(K1, LOW);
  digitalWrite(K2, LOW);
  digitalWrite(K3, HIGH);
  digitalWrite(K4, HIGH);
  digitalWrite(K5, HIGH);
  digitalWrite(K6, LOW);
  digitalWrite(K7, HIGH);
  mode = "Load receives power from PEM Battery OFF PV OFF";
  digitalWrite(LEDS1, LOW);
  digitalWrite(LEDS2, LOW);
  digitalWrite(LEDS3, LOW);
  digitalWrite(LEDS4, LOW);
  digitalWrite(LEDS5, LOW);
  digitalWrite(LEDS6, HIGH);
}