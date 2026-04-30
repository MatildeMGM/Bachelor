// #include <Arduino_RouterBridge.h>

// // Pin definitions
// const int K1 = 8;   // Relay1
// const int K2 = 2;   // Relay2
// const int K3 = 3;   // Relay3
// const int K4 = 4;   // Relay4
// const int K5 = 5;   // Relay5
// const int K6 = 7;   // Relay6
// const int K7 = 9;   // Relay7

// const int LEDS1 = 21;
// const int LEDS2 = 0;
// const int LEDS3 = 20;
// const int LEDS4 = 6;
// const int LEDS5 = 1;
// const int LEDS6 = 13;

// // Analog voltage pins
// const int batteryVoltagePin = A4;
// const int panelVoltagePin   = A2;
// const int pemrfcVoltagePin  = A5;
// const int loadVoltagePin    = A1;

// // Multiplexer pin definition
// const int selectPins[3] = {10, 11, 12}; // S0, S1, S2
// const int zInput = A0;                  // Common (Z) to A0

// // Electricity price time management
// unsigned long previousMillis = 0;
// const long period = 20000;   // kept from original logic
// int priceSlot = 0;           // 0..95 for 15-minute resolution
// float electricityprice = 0.0;
// bool priceReceived = false;

// // PEMRFC time management
// const long period2 = 60000;
// unsigned long starttime = 0;
// bool PEM_flag = false;

// // Voltage divider coefficients
// const float batteryVoltageDivider = 1.5557;
// const float panelVoltageDivider   = 1.5557;
// const float pemrfcVoltageDivider  = 1.5557;
// const float loadVoltageDivider    = 1.55416;
// const float nominalVoltageDivider = 1.45829;

// // Global variables for sensor data
// float nominalVoltage = 0.0;
// float panelVoltage = 0.0;
// float loadVoltage = 0.0;
// float pemrfcVoltage = 0.0;
// float batteryVoltage = 0.0;
// float batterySOC = 0.0;

// // Printing time
// unsigned long lastPrint = 0;
// const long printInterval = 2000; // 2 seconds

// unsigned int x = 0;
// float SensorValuePV   = 0.0, SamplesPV   = 0.0, AvgAcsPV   = 0.0, PVcurrent   = 0.0;
// float SensorValueLoad = 0.0, SamplesLoad = 0.0, AvgAcsLoad = 0.0, Loadcurrent = 0.0;
// float SensorValuePEM  = 0.0, SamplesPEM  = 0.0, AvgAcsPEM  = 0.0, PEMcurrent  = 0.0;
// float SensorValueBat  = 0.0, SamplesBat  = 0.0, AvgAcsBat  = 0.0, Batcurrent  = 0.0;

// float PVpower = 0.0;
// float Loadpower = 0.0;
// float PEMpower = 0.0;
// float Batterypower = 0.0;

// String mode = "";

// // Battery and PEM gets status charged when running script
// bool pemCharged = true;
// bool batCharged = true;

// // Function declarations
// void Scenario1();
// void Scenario2();
// void Scenario3();
// void Scenario4();
// void Scenario5();
// void Scenario6();

// void HighPriceScheme();
// void LowPriceScheme();

// void GetVoltage();
// void GetCurrent();
// void GetPower();
// void UpdatePrices();
// void PrintValues();
// void CSVPrintValues();
// void selectMuxPin(byte pin);

// bool apply_price_frame(String payload);
// String get_status();

// void setup() {
//   Monitor.begin();
//   delay(1000);
//   Monitor.println("EMS sketch started");

//   Bridge.begin();
//   Bridge.provide("apply_price_frame", apply_price_frame);
//   Bridge.provide("get_status", get_status);

//   // Initialize pin modes
//   pinMode(K1, OUTPUT);
//   pinMode(K2, OUTPUT);
//   pinMode(K3, OUTPUT);
//   pinMode(K4, OUTPUT);
//   pinMode(K5, OUTPUT);
//   pinMode(K6, OUTPUT);
//   pinMode(K7, OUTPUT);

//   pinMode(LEDS1, OUTPUT);
//   pinMode(LEDS2, OUTPUT);
//   pinMode(LEDS3, OUTPUT);
//   pinMode(LEDS4, OUTPUT);
//   pinMode(LEDS5, OUTPUT);
//   pinMode(LEDS6, OUTPUT);

//   pinMode(batteryVoltagePin, INPUT);
//   pinMode(pemrfcVoltagePin, INPUT);
//   pinMode(loadVoltagePin, INPUT);
//   pinMode(panelVoltagePin, INPUT);

//   pinMode(selectPins[0], OUTPUT);
//   pinMode(selectPins[1], OUTPUT);
//   pinMode(selectPins[2], OUTPUT);
//   pinMode(zInput, INPUT);

//   // Begin in scenario 1
//   Scenario1();
// }

// void loop() {
//   Monitor.println("loop alive");
//   delay(1000);

//   UpdatePrices();   // kept for compatibility
//   GetVoltage();
//   GetCurrent();
//   GetPower();
  
//   if (millis() - lastPrint >= printInterval) {
//     lastPrint = millis();
//     PrintValues();
//   }

//   if (electricityprice >= 0.6) {
//     HighPriceScheme();
//   } else {
//     LowPriceScheme();
//   }

//   delay(400); // 2.5 times pr minute

//   // PEM charging time handling
//   if (digitalRead(K4) == HIGH) {
//     starttime = 0;
//     PEM_flag = false;
//   }
// }

// // -----------------------------------------------------------------------------
// // Bridge functions
// // -----------------------------------------------------------------------------

// bool apply_price_frame(String payload) {
//   // Expected format: PRICE,<price>,<slot>
//   if (!payload.startsWith("PRICE,")) {
//     return false;
//   }

//   int firstComma = payload.indexOf(',');
//   int secondComma = payload.indexOf(',', firstComma + 1);

//   if (firstComma < 0 || secondComma < 0) {
//     return false;
//   }

//   electricityprice = payload.substring(firstComma + 1, secondComma).toFloat();
//   priceSlot = payload.substring(secondComma + 1).toInt();
//   priceReceived = true;

//   Monitor.print("Received price from main.py -> slot: ");
//   Monitor.print(priceSlot);
//   Monitor.print(", price: ");
//   Monitor.println(electricityprice, 5);

//   return true;
// }

// String get_status() {
//   String payload = "";

//   payload += "slot=" + String(priceSlot);
//   payload += ",price=" + String(electricityprice, 5);

//   payload += ",panelVoltage=" + String(panelVoltage, 5);
//   payload += ",batteryVoltage=" + String(batteryVoltage, 5);
//   payload += ",pemrfcVoltage=" + String(pemrfcVoltage, 5);
//   payload += ",loadVoltage=" + String(loadVoltage, 5);

//   payload += ",PVcurrent=" + String(PVcurrent, 5);
//   payload += ",Batcurrent=" + String(Batcurrent, 5);
//   payload += ",PEMcurrent=" + String(PEMcurrent, 5);
//   payload += ",Loadcurrent=" + String(Loadcurrent, 5);

//   payload += ",PVpower=" + String(PVpower, 5);
//   payload += ",Batterypower=" + String(Batterypower, 5);
//   payload += ",PEMpower=" + String(PEMpower, 5);
//   payload += ",Loadpower=" + String(Loadpower, 5);

//   payload += ",mode=" + mode;
//   payload += ",priceReceived=" + String(priceReceived ? 1 : 0);

//   return payload;
// }

// // -----------------------------------------------------------------------------
// // EMS logic
// // -----------------------------------------------------------------------------

// void HighPriceScheme() {
//   if ((digitalRead(K1) == LOW && digitalRead(K2) == HIGH && digitalRead(K7) == LOW && loadVoltage > 0.15) || panelVoltage > 2.0) {
//     Scenario4();
//   } else if (batCharged && batteryVoltage > 2.6) {
//     Scenario5();
//   } else if ((digitalRead(K1) == LOW && digitalRead(K6) == LOW && loadVoltage > 0.2) || (pemCharged && pemrfcVoltage > 0.5)) {
//     Scenario6();
//     batCharged = false;
//   } else {
//     pemCharged = false;
//     batCharged = false;
//     Scenario1();
//   }
// }

// void LowPriceScheme() {
//   if (panelVoltage > 2.0 || PEM_flag == true) {
//     if (((digitalRead(K3) == LOW && digitalRead(K5) == HIGH && batteryVoltage < 3.805 && Batcurrent >= -0.1 && PEM_flag == false)) ||
//         ((Batcurrent >= -0.1 && batteryVoltage <= 3.66 && PEM_flag == false))) {
//       Scenario2();
//       if (batteryVoltage > 2.75) {
//         batCharged = true;
//       }
//     } else if (PEMcurrent >= -0.1) {
//       Scenario3();
//       PEM_flag = true;
//       if (pemCharged == false && starttime == 0) {
//         starttime = millis();
//       }
//       if (millis() - starttime >= period2) {
//         pemCharged = true;
//       }
//     } else {
//       Scenario1();
//     }
//   } else {
//     Scenario1();
//   }
// }

// // -----------------------------------------------------------------------------
// // Measurements
// // -----------------------------------------------------------------------------

// void GetVoltage() {
//   selectMuxPin(2);

//   nominalVoltage = (analogRead(zInput) / 1023.0) * 5 * nominalVoltageDivider;
//   loadVoltage    = (analogRead(loadVoltagePin) / 1023.0) * 5 * loadVoltageDivider;
//   panelVoltage   = (analogRead(panelVoltagePin) / 1023.0) * 5 * panelVoltageDivider;
//   pemrfcVoltage  = (analogRead(pemrfcVoltagePin) / 1023.0) * 5 * pemrfcVoltageDivider;
//   batteryVoltage = (analogRead(batteryVoltagePin) / 1023.0) * 5 * batteryVoltageDivider;
// }

// void GetCurrent() {
//   x = 0;
//   SensorValuePV = 0.0;   SamplesPV = 0.0;   AvgAcsPV = 0.0;   PVcurrent = 0.0;
//   SensorValueLoad = 0.0; SamplesLoad = 0.0; AvgAcsLoad = 0.0; Loadcurrent = 0.0;
//   SensorValuePEM = 0.0;  SamplesPEM = 0.0;  AvgAcsPEM = 0.0;  PEMcurrent = 0.0;
//   SensorValueBat = 0.0;  SamplesBat = 0.0;  AvgAcsBat = 0.0;  Batcurrent = 0.0;

//   for (int x = 0; x < 300; x++) {
//     // PEM current measurement
//     selectMuxPin(1);
//     SensorValuePEM = analogRead(zInput);

//     // Load current measurement
//     selectMuxPin(0);
//     SensorValueLoad = analogRead(zInput);

//     // PV current measurement
//     SensorValuePV = analogRead(A3);

//     // Battery current measurement
//     selectMuxPin(3);
//     SensorValueBat = analogRead(zInput);

//     // Add samples together
//     SamplesPV   += SensorValuePV;
//     SamplesLoad += SensorValueLoad;
//     SamplesPEM  += SensorValuePEM;
//     SamplesBat  += SensorValueBat;

//     delay(3);
//   }

//   // Taking average of samples
//   AvgAcsPV   = SamplesPV / 300.0;
//   AvgAcsLoad = SamplesLoad / 300.0;
//   AvgAcsPEM  = SamplesPEM / 300.0;
//   AvgAcsBat  = SamplesBat / 300.0;

//   // Calculating currents
//   PVcurrent   = ((AvgAcsPV   * (5 / 1023.0) - nominalVoltage / 2) / 0.4413) + 0.09;
//   Loadcurrent = ((AvgAcsLoad * (5 / 1023.0) - nominalVoltage / 2) / 0.2487) + 0.02;
//   PEMcurrent  = ((AvgAcsPEM  * (5 / 1023.0) - nominalVoltage / 2) / 0.4749) + 0.091;
//   Batcurrent  = ((AvgAcsBat  * (5 / 1023.0) - nominalVoltage / 2) / 0.3276) + 0.09;
// }

// void GetPower() {
//   PVpower      = PVcurrent * panelVoltage;
//   Loadpower    = Loadcurrent * loadVoltage;
//   PEMpower     = PEMcurrent * pemrfcVoltage;
//   Batterypower = Batcurrent * batteryVoltage;
// }

// void UpdatePrices() {
//   // Price and slot are provided by main.py through Bridge
// }

// void selectMuxPin(byte pin) {
//   for (int i = 0; i < 3; i++) {
//     if (pin & (1 << i)) {
//       digitalWrite(selectPins[i], HIGH);
//     } else {
//       digitalWrite(selectPins[i], LOW);
//     }
//   }
// }

// // -----------------------------------------------------------------------------
// // Serial output
// // -----------------------------------------------------------------------------

// void PrintValues() {
//   Monitor.print("Nominal Voltage: ");
//   Monitor.print(nominalVoltage);
//   Monitor.print(" PVCurrent: ");
//   Monitor.print(PVcurrent, 3);
//   Monitor.print(" PV Voltage: ");
//   Monitor.print(panelVoltage, 3);
//   Monitor.print(" PV Power: ");
//   Monitor.print(PVpower);
//   Monitor.print(" Battery Voltage: ");
//   Monitor.print(batteryVoltage);
//   Monitor.print(" Battery Current: ");
//   Monitor.print(Batcurrent, 3);
//   Monitor.print(" Load Current: ");
//   Monitor.print(Loadcurrent, 3);
//   Monitor.print(" Load Voltage: ");
//   Monitor.print(loadVoltage, 3);
//   Monitor.print(" Load Power: ");
//   Monitor.print(Loadpower);
//   Monitor.print(" PEM RFC Current: ");
//   Monitor.print(PEMcurrent, 3);
//   Monitor.print(" PEM RFC Voltage: ");
//   Monitor.println(pemrfcVoltage, 3);
//   Monitor.print(" PEM RFC Power: ");
//   Monitor.println(PEMpower);
//   Monitor.print(" Electricity price: ");
//   Monitor.println(electricityprice, 5);
//   Monitor.print(" Price slot: ");
//   Monitor.println(priceSlot);
//   Monitor.print(" Mode: ");
//   Monitor.println(mode);
// }

// void CSVPrintValues() {
//   Monitor.print(priceSlot);
//   Monitor.print(",");
//   Monitor.print(electricityprice);
//   Monitor.print(",");
//   Monitor.print(panelVoltage);
//   Monitor.print(",");
//   Monitor.print(PVcurrent);
//   Monitor.print(",");
//   Monitor.print(PVpower);
//   Monitor.print(",");
//   Monitor.print(batteryVoltage);
//   Monitor.print(",");
//   Monitor.print(Batcurrent);
//   Monitor.print(",");
//   Monitor.print(Batterypower);
//   Monitor.print(",");
//   Monitor.print(pemrfcVoltage);
//   Monitor.print(",");
//   Monitor.print(PEMcurrent);
//   Monitor.print(",");
//   Monitor.print(PEMpower);
//   Monitor.print(",");
//   Monitor.print(loadVoltage);
//   Monitor.print(",");
//   Monitor.print(Loadcurrent);
//   Monitor.print(",");
//   Monitor.print(Loadpower);
//   Monitor.print(",");
//   Monitor.print(batCharged);
//   Monitor.print(",");
//   Monitor.print(pemCharged);
//   Monitor.print(",");
//   Monitor.print(mode);
//   Monitor.print("\n");
// }

// // -----------------------------------------------------------------------------
// // Scenarios
// // -----------------------------------------------------------------------------

// // Scenario 1:
// // Load receives power from grid, PV OFF, Battery OFF, PEM RFC OFF
// void Scenario1() {
//   digitalWrite(K1, HIGH);
//   digitalWrite(K2, LOW);
//   digitalWrite(K3, HIGH);
//   digitalWrite(K4, HIGH);
//   digitalWrite(K5, HIGH);
//   digitalWrite(K6, HIGH);
//   digitalWrite(K7, HIGH);
//   mode = "S1 - Load receives power from grid PV OFF Battery OFF PEM RFC OFF";
//   digitalWrite(LEDS1, HIGH);
//   digitalWrite(LEDS2, LOW);
//   digitalWrite(LEDS3, LOW);
//   digitalWrite(LEDS4, LOW);
//   digitalWrite(LEDS5, LOW);
//   digitalWrite(LEDS6, LOW);
// }

// // Scenario 2:
// // Load receives power from grid, PV charges battery, PEM RFC OFF
// void Scenario2() {
//   digitalWrite(K1, HIGH);
//   digitalWrite(K2, LOW);
//   digitalWrite(K3, LOW);
//   digitalWrite(K4, HIGH);
//   digitalWrite(K5, HIGH);
//   digitalWrite(K6, HIGH);
//   digitalWrite(K7, LOW);
//   mode = "S2 - Load receives power from grid PV Charges battery PEM RFC OFF";
//   digitalWrite(LEDS1, LOW);
//   digitalWrite(LEDS2, HIGH);
//   digitalWrite(LEDS3, LOW);
//   digitalWrite(LEDS4, LOW);
//   digitalWrite(LEDS5, LOW);
//   digitalWrite(LEDS6, LOW);
// }

// // Scenario 3:
// // Load receives power from grid, PV charges PEM RFC, battery OFF
// void Scenario3() {
//   digitalWrite(K1, HIGH);
//   digitalWrite(K2, LOW);
//   digitalWrite(K3, HIGH);
//   digitalWrite(K4, LOW);
//   digitalWrite(K5, HIGH);
//   digitalWrite(K6, HIGH);
//   digitalWrite(K7, LOW);
//   mode = "S3 - Load receives power from grid PV Charges PEM RFC battery OFF";
//   digitalWrite(LEDS1, LOW);
//   digitalWrite(LEDS2, LOW);
//   digitalWrite(LEDS3, HIGH);
//   digitalWrite(LEDS4, LOW);
//   digitalWrite(LEDS5, LOW);
//   digitalWrite(LEDS6, LOW);
// }

// // Scenario 4:
// // Load receives power from PV only, battery OFF, PEM RFC OFF
// void Scenario4() {
//   digitalWrite(K1, LOW);
//   digitalWrite(K2, HIGH);
//   digitalWrite(K3, HIGH);
//   digitalWrite(K4, HIGH);
//   digitalWrite(K5, HIGH);
//   digitalWrite(K6, HIGH);
//   digitalWrite(K7, LOW);
//   mode = "S4 - Load receives power from PV battery OFF PEM RFC OFF";
//   digitalWrite(LEDS1, LOW);
//   digitalWrite(LEDS2, LOW);
//   digitalWrite(LEDS3, LOW);
//   digitalWrite(LEDS4, HIGH);
//   digitalWrite(LEDS5, LOW);
//   digitalWrite(LEDS6, LOW);
// }

// // Scenario 5:
// // Load receives power from battery, PEM RFC OFF, PV OFF
// void Scenario5() {
//   digitalWrite(K1, LOW);
//   digitalWrite(K2, LOW);
//   digitalWrite(K3, HIGH);
//   digitalWrite(K4, HIGH);
//   digitalWrite(K5, LOW);
//   digitalWrite(K6, HIGH);
//   digitalWrite(K7, HIGH);
//   mode = "S5 - Load receives power from battery PEM RFC OFF PV OFF";
//   digitalWrite(LEDS1, LOW);
//   digitalWrite(LEDS2, LOW);
//   digitalWrite(LEDS3, LOW);
//   digitalWrite(LEDS4, LOW);
//   digitalWrite(LEDS5, HIGH);
//   digitalWrite(LEDS6, LOW);
// }

// // Scenario 6:
// // Load receives power from PEM, Battery OFF, PV OFF
// void Scenario6() {
//   digitalWrite(K1, LOW);
//   digitalWrite(K2, LOW);
//   digitalWrite(K3, HIGH);
//   digitalWrite(K4, HIGH);
//   digitalWrite(K5, HIGH);
//   digitalWrite(K6, LOW);
//   digitalWrite(K7, HIGH);
//   mode = "S6 - Load receives power from PEM Battery OFF PV OFF";
//   digitalWrite(LEDS1, LOW);
//   digitalWrite(LEDS2, LOW);
//   digitalWrite(LEDS3, LOW);
//   digitalWrite(LEDS4, LOW);
//   digitalWrite(LEDS5, LOW);
//   digitalWrite(LEDS6, HIGH);
// }