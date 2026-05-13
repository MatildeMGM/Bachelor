#include <Wire.h>
#include <INA226_WE.h>
#include <math.h>
#include <stdlib.h>

#include "profile_csv.h"

#define INA226_ADDRESS 0x40

INA226_WE ina226(&Wire, INA226_ADDRESS);

// -------------------------
// Digital start signal
// -------------------------
const int START_SIGNAL_PIN = 2;      // Digital input pin on UNO R4
const bool START_SIGNAL_ACTIVE = HIGH;

// If your external signal is floating when inactive, use INPUT_PULLUP instead.
// For a true external HIGH/LOW signal, INPUT is normally correct.
const int START_SIGNAL_PIN_MODE = INPUT;

bool previousStartSignalState = LOW;

// -------------------------
// DAC settings
// -------------------------
const int DAC_PIN = A0;              // UNO R4 WiFi DAC pin
const float DAC_REF_V = 5.0f;
const float DAC_MAX_V = 5.0f;
const int DAC_MAX_CODE = (int)((DAC_MAX_V / DAC_REF_V) * 4095.0f + 0.5f);

// -------------------------
// Startup DAC behavior
// -------------------------
int DAC_START_CODE = 1450;
bool USE_DAC_START_PRELOAD = true;

const float START_PRELOAD_MIN_POWER_W = 0.005f;

// -------------------------
// INA correction
// -------------------------
const float INA_CORRECTION_FACTOR = 0.856f;

// -------------------------
// CSV profile settings
// -------------------------
const int MAX_PROFILE_POINTS = 192;

float powerProfile_W[MAX_PROFILE_POINTS];
int profileLength = 0;

const unsigned long PROFILE_STEP_INTERVAL_MS = 15000;
const bool CSV_POWER_IS_MW = true;

// -------------------------
// Time-series state
// -------------------------
bool loadEnabled = false;
bool profileRunning = false;
bool repeatProfile = false;

int profileIndex = 0;
unsigned long lastProfileStepMs = 0;

// -------------------------
// User limits
// -------------------------
float I_MAX_A = 0.80f;
float P_MAX_W = 3.00f;

bool enableBusLowFault = false;
float BUS_MIN_V = 0.10f;

float setPower_W = 0.0f;

// -------------------------
// Control behavior
// -------------------------
int dacCode = 0;

unsigned long controlIntervalMs = 40;
unsigned long printIntervalMs = 500;

unsigned long lastControlMs = 0;
unsigned long lastPrintMs = 0;

const int DAC_KNEE_CODE = 1400;
int DAC_FAST_APPROACH_TARGET = 1600;

const float CURRENT_FLOW_THRESHOLD_A = 0.010f;

int STEP_FAST = 80;
const int STEP_SMALL = 2;
const int STEP_TINY = 1;
const int STEP_BACKOFF = 12;

const int STEP_POWER_VERY_FAR = 20;
const int STEP_POWER_FAR = 12;
const int STEP_POWER_MEDIUM = 6;
const int STEP_POWER_NEAR = 3;

// -------------------------
// Filter / damping
// -------------------------
float filteredCurrent_A = 0.0f;
float filteredPower_W = 0.0f;
bool filterInitialized = false;

const float CURRENT_FILTER_ALPHA = 0.18f;
const float POWER_FILTER_ALPHA = 0.18f;
const float POWER_DEADBAND_W = 0.005f;

// -------------------------
// Limits and protection
// -------------------------
const float SOFT_LIMIT_FRAC = 0.92f;

const float CURRENT_FAULT_MARGIN_A = 0.08f;
const float POWER_FAULT_MARGIN_W = 0.20f;

// -------------------------
// Weak source collapse detection
// -------------------------
float healthyBusVoltage_V = 0.0f;

const float COLLAPSE_FRAC = 0.85f;
const int COLLAPSE_BACKOFF = 50;

// -------------------------
// Measurements
// -------------------------
float shuntVoltage_mV = 0.0f;
float busVoltage_V = 0.0f;
float current_mA = 0.0f;
float power_mW = 0.0f;

float current_A = 0.0f;
float power_W = 0.0f;

// -------------------------
// Fault latch
// -------------------------
bool faultLatched = false;
String faultMessage = "";

// -------------------------
// DAC helper functions
// -------------------------
void setDACCode(int value) {
  if (value < 0) {
    value = 0;
  }

  if (value > DAC_MAX_CODE) {
    value = DAC_MAX_CODE;
  }

  dacCode = value;
  analogWrite(DAC_PIN, dacCode);
}

float dacVoltageFromCode(int code) {
  return (code / 4095.0f) * DAC_REF_V;
}

// -------------------------
// Profile helper functions
// -------------------------
float profileTimeHours(int index) {
  return index * 0.25f;
}

void resetProfileState() {
  profileIndex = 0;

  if (profileLength > 0) {
    setPower_W = powerProfile_W[0];
  } else {
    setPower_W = 0.0f;
  }

  lastProfileStepMs = millis();
}

void stopLoadOnly() {
  loadEnabled = false;
  profileRunning = false;
  setDACCode(0);
  healthyBusVoltage_V = 0.0f;
  filterInitialized = false;
}

void stopAndResetProfile() {
  stopLoadOnly();
  resetProfileState();
}

void tripFault(const String &msg) {
  faultLatched = true;
  faultMessage = msg;
  stopLoadOnly();

  Serial.print("FAULT: ");
  Serial.println(faultMessage);
}

void clearFault() {
  faultLatched = false;
  faultMessage = "";
  stopAndResetProfile();

  Serial.println("Fault cleared. Load stopped and profile reset.");
}

// -------------------------
// CSV parsing
// -------------------------
bool loadProfileFromCSV() {
  profileLength = 0;

  const char *p = PROFILE_CSV;

  while (*p != '\0' && profileLength < MAX_PROFILE_POINTS) {
    const char *lineStart = p;

    while (*p != '\0' && *p != '\n' && *p != '\r') {
      p++;
    }

    const char *lineEnd = p;

    while (*p == '\n' || *p == '\r') {
      p++;
    }

    int lineLength = lineEnd - lineStart;

    if (lineLength <= 0) {
      continue;
    }

    bool containsLetter = false;

    for (const char *q = lineStart; q < lineEnd; q++) {
      if ((*q >= 'A' && *q <= 'Z') || (*q >= 'a' && *q <= 'z')) {
        containsLetter = true;
        break;
      }
    }

    if (containsLetter) {
      continue;
    }

    const char *lastComma = nullptr;

    for (const char *q = lineStart; q < lineEnd; q++) {
      if (*q == ',') {
        lastComma = q;
      }
    }

    if (lastComma == nullptr || lastComma + 1 >= lineEnd) {
      continue;
    }

    char numberBuffer[24];
    int n = 0;

    for (const char *q = lastComma + 1; q < lineEnd && n < 23; q++) {
      numberBuffer[n++] = *q;
    }

    numberBuffer[n] = '\0';

    float value = atof(numberBuffer);

    if (value < 0.0f) {
      value = 0.0f;
    }

    if (CSV_POWER_IS_MW) {
      value = value / 1000.0f;
    }

    powerProfile_W[profileLength] = value;
    profileLength++;
  }

  if (profileLength <= 0) {
    return false;
  }

  resetProfileState();
  return true;
}

// -------------------------
// INA226 measurements
// -------------------------
void readINA226() {
  shuntVoltage_mV = ina226.getShuntVoltage_mV();
  busVoltage_V = ina226.getBusVoltage_V();
  current_mA = ina226.getCurrent_mA();
  power_mW = ina226.getBusPower();

  current_A = current_mA / 1000.0f;
  power_W = power_mW / 1000.0f;

  if (shuntVoltage_mV < 0.0f) {
    shuntVoltage_mV = 0.0f;
  }

  if (busVoltage_V < 0.0f) {
    busVoltage_V = 0.0f;
  }

  if (current_A < 0.0f) {
    current_A = 0.0f;
  }

  if (power_W < 0.0f) {
    power_W = 0.0f;
  }

  if (!filterInitialized) {
    filteredCurrent_A = current_A;
    filteredPower_W = power_W;
    filterInitialized = true;
  } else {
    filteredCurrent_A =
      CURRENT_FILTER_ALPHA * current_A +
      (1.0f - CURRENT_FILTER_ALPHA) * filteredCurrent_A;

    filteredPower_W =
      POWER_FILTER_ALPHA * power_W +
      (1.0f - POWER_FILTER_ALPHA) * filteredPower_W;
  }
}

// -------------------------
// Profile printing
// -------------------------
void printProfilePoint() {
  Serial.print("Profile step ");
  Serial.print(profileIndex + 1);
  Serial.print("/");
  Serial.print(profileLength);

  Serial.print(" | SimTime=");
  Serial.print(profileTimeHours(profileIndex), 2);
  Serial.print(" h");

  Serial.print(" | Pset=");
  Serial.print(setPower_W, 4);
  Serial.println(" W");
}

// -------------------------
// Startup DAC preload
// -------------------------
void preloadDACForStartup() {
  if (!USE_DAC_START_PRELOAD) {
    return;
  }

  if (setPower_W <= START_PRELOAD_MIN_POWER_W) {
    setDACCode(0);
    return;
  }

  setDACCode(DAC_START_CODE);

  Serial.print("Startup DAC preload: DAC=");
  Serial.print(dacCode);
  Serial.print(" | Vdac=");
  Serial.print(dacVoltageFromCode(dacCode), 4);
  Serial.println(" V");
}

// -------------------------
// Profile control
// -------------------------
void startProfile(bool restartFromBeginning) {
  if (faultLatched) {
    Serial.println("Cannot start: fault is latched. Use resetfault first.");
    return;
  }

  if (profileLength <= 0) {
    Serial.println("Cannot start: no valid CSV profile loaded.");
    return;
  }

  if (restartFromBeginning) {
    resetProfileState();
  }

  if (profileIndex >= profileLength) {
    resetProfileState();
  }

  setPower_W = powerProfile_W[profileIndex];

  loadEnabled = true;
  profileRunning = true;
  filterInitialized = false;
  healthyBusVoltage_V = 0.0f;

  preloadDACForStartup();

  lastProfileStepMs = millis();

  Serial.println("Profile started.");
  printProfilePoint();
}

void stopProfileManual() {
  stopLoadOnly();
  Serial.println("Profile stopped. Load disabled.");
}

void resetProfileManual() {
  stopAndResetProfile();
  Serial.println("Profile stopped and reset to first point.");
  printProfilePoint();
}

void updateProfile() {
  if (!profileRunning || !loadEnabled || faultLatched) {
    return;
  }

  unsigned long now = millis();

  if (now - lastProfileStepMs >= PROFILE_STEP_INTERVAL_MS) {
    lastProfileStepMs += PROFILE_STEP_INTERVAL_MS;

    profileIndex++;

    if (profileIndex >= profileLength) {
      if (repeatProfile) {
        profileIndex = 0;
      } else {
        stopAndResetProfile();
        Serial.println("Profile completed. Load disabled and profile reset.");
        return;
      }
    }

    setPower_W = powerProfile_W[profileIndex];
    printProfilePoint();
  }
}

// -------------------------
// Digital input control
// -------------------------
void handleStartSignalInput() {
  bool currentStartSignalState = digitalRead(START_SIGNAL_PIN);

  bool wasActive = previousStartSignalState == START_SIGNAL_ACTIVE;
  bool isActive = currentStartSignalState == START_SIGNAL_ACTIVE;

  if (!wasActive && isActive) {
    Serial.println("Digital start signal HIGH detected.");
    startProfile(true);
  }

  if (wasActive && !isActive) {
    Serial.println("Digital start signal LOW detected. Stopping and resetting.");
    stopAndResetProfile();
  }

  previousStartSignalState = currentStartSignalState;
}

// -------------------------
// Serial output
// -------------------------
void printStatus() {
  Serial.print("State=");

  if (faultLatched) {
    Serial.print("FAULT");
  } else if (loadEnabled) {
    Serial.print("ON");
  } else {
    Serial.print("OFF");
  }

  Serial.print(" | DigitalIn=");
  Serial.print(digitalRead(START_SIGNAL_PIN) == START_SIGNAL_ACTIVE ? "HIGH" : "LOW");

  Serial.print(" | Profile=");
  Serial.print(profileRunning ? "RUNNING" : "STOPPED");

  Serial.print(" | Step=");
  Serial.print(profileIndex + 1);
  Serial.print("/");
  Serial.print(profileLength);

  Serial.print(" | SimTime=");
  Serial.print(profileTimeHours(profileIndex), 2);
  Serial.print(" h");

  Serial.print(" | V=");
  Serial.print(busVoltage_V, 4);
  Serial.print(" V");

  Serial.print(" | I=");
  Serial.print(current_A, 4);
  Serial.print(" A");

  Serial.print(" | P=");
  Serial.print(power_W, 4);
  Serial.print(" W");

  Serial.print(" | Pset=");
  Serial.print(setPower_W, 4);
  Serial.print(" W");

  Serial.print(" | DAC=");
  Serial.print(dacCode);

  Serial.print(" | Vdac=");
  Serial.print(dacVoltageFromCode(dacCode), 4);
  Serial.print(" V");

  if (faultLatched) {
    Serial.print(" | Fault=");
    Serial.print(faultMessage);
  }

  Serial.println();
}

void printHelp() {
  Serial.println();
  Serial.println("Commands:");
  Serial.println("  help        -> show commands");
  Serial.println("  status      -> print one status line");
  Serial.println("  start       -> start or continue profile manually");
  Serial.println("  restart     -> start profile manually from first point");
  Serial.println("  stop        -> stop profile and disable load");
  Serial.println("  reset       -> stop profile and reset to first point");
  Serial.println("  resetfault  -> clear fault latch");
  Serial.println();
  Serial.println("Digital trigger:");
  Serial.print("  D");
  Serial.print(START_SIGNAL_PIN);
  Serial.println(" HIGH -> start profile from first point");
  Serial.print("  D");
  Serial.print(START_SIGNAL_PIN);
  Serial.println(" LOW  -> stop and reset profile");
  Serial.println();
}

// -------------------------
// Serial command handling
// -------------------------
void handleSerial() {
  if (!Serial.available()) {
    return;
  }

  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  cmd.toLowerCase();

  if (cmd == "help") {
    printHelp();
    return;
  }

  if (cmd == "status") {
    readINA226();
    printStatus();
    return;
  }

  if (cmd == "start") {
    startProfile(false);
    return;
  }

  if (cmd == "restart") {
    startProfile(true);
    return;
  }

  if (cmd == "stop") {
    stopProfileManual();
    return;
  }

  if (cmd == "reset") {
    resetProfileManual();
    return;
  }

  if (cmd == "resetfault") {
    clearFault();
    return;
  }

  Serial.println("Unknown command. Type 'help'.");
}

// -------------------------
// Power-control helper
// -------------------------
void applyRelativePowerControl(float effectivePowerTarget) {
  float error_W = effectivePowerTarget - filteredPower_W;
  float absError_W = fabs(error_W);

  if (absError_W <= POWER_DEADBAND_W) {
    return;
  }

  bool sourceCollapsed =
    (healthyBusVoltage_V > 0.0f) &&
    (busVoltage_V < COLLAPSE_FRAC * healthyBusVoltage_V) &&
    (dacCode > DAC_KNEE_CODE);

  if (sourceCollapsed) {
    setDACCode(dacCode - COLLAPSE_BACKOFF);
    return;
  }

  float relativePower = 0.0f;

  if (effectivePowerTarget > 0.001f) {
    relativePower = filteredPower_W / effectivePowerTarget;
  }

  if (error_W > 0.0f) {
    int step = STEP_TINY;

    if (relativePower < 0.25f) {
      step = STEP_POWER_VERY_FAR;
    } else if (relativePower < 0.50f) {
      step = STEP_POWER_FAR;
    } else if (relativePower < 0.75f) {
      step = STEP_POWER_MEDIUM;
    } else if (relativePower < 0.90f) {
      step = STEP_POWER_NEAR;
    } else {
      step = STEP_TINY;
    }

    setDACCode(dacCode + step);
  } else {
    if (filteredPower_W > 1.25f * effectivePowerTarget) {
      setDACCode(dacCode - STEP_BACKOFF);
    } else {
      setDACCode(dacCode - STEP_SMALL);
    }
  }
}

// -------------------------
// Main control loop
// -------------------------
void controlLoop() {
  readINA226();

  if (faultLatched) {
    stopLoadOnly();
    return;
  }

  if (!loadEnabled) {
    setDACCode(0);
    return;
  }

  if (healthyBusVoltage_V <= 0.0f) {
    healthyBusVoltage_V = busVoltage_V;
  }

  if (busVoltage_V > healthyBusVoltage_V) {
    healthyBusVoltage_V = busVoltage_V;
  } else {
    healthyBusVoltage_V =
      0.995f * healthyBusVoltage_V +
      0.005f * busVoltage_V;
  }

  float hardCurrentLimit = I_MAX_A + CURRENT_FAULT_MARGIN_A;
  float hardPowerLimit = P_MAX_W + POWER_FAULT_MARGIN_W;

  if (current_A > hardCurrentLimit) {
    tripFault("Overcurrent");
    return;
  }

  if (power_W > hardPowerLimit) {
    tripFault("Overpower");
    return;
  }

  if (shuntVoltage_mV > 80.0f) {
    tripFault("INA226 shunt near saturation");
    return;
  }

  if (enableBusLowFault && busVoltage_V < BUS_MIN_V && current_A > 0.05f) {
    tripFault("Bus voltage collapsed");
    return;
  }

  float effectivePowerTarget = setPower_W;

  if (effectivePowerTarget > P_MAX_W) {
    effectivePowerTarget = P_MAX_W;
  }

  if (effectivePowerTarget <= 0.0f) {
    setDACCode(0);
    return;
  }

  float iAllowedByPower = I_MAX_A;

  if (busVoltage_V > 0.1f) {
    float pLimitedCurrent = P_MAX_W / busVoltage_V;

    if (pLimitedCurrent < iAllowedByPower) {
      iAllowedByPower = pLimitedCurrent;
    }
  }

  float softCurrentLimit = SOFT_LIMIT_FRAC * iAllowedByPower;
  float softPowerLimit = SOFT_LIMIT_FRAC * P_MAX_W;

  if (power_W >= softPowerLimit) {
    setDACCode(dacCode - STEP_BACKOFF);
    return;
  }

  if (filteredCurrent_A >= softCurrentLimit) {
    setDACCode(dacCode - STEP_BACKOFF);
    return;
  }

  if ((effectivePowerTarget > START_PRELOAD_MIN_POWER_W) &&
      (filteredCurrent_A < CURRENT_FLOW_THRESHOLD_A) &&
      (dacCode < DAC_FAST_APPROACH_TARGET)) {
    setDACCode(dacCode + STEP_FAST);
    return;
  }

  applyRelativePowerControl(effectivePowerTarget);
}

// -------------------------
// Setup
// -------------------------
void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(START_SIGNAL_PIN, START_SIGNAL_PIN_MODE);
  previousStartSignalState = digitalRead(START_SIGNAL_PIN);

  analogWriteResolution(12);
  setDACCode(0);

  if (!loadProfileFromCSV()) {
    Serial.println("ERROR: Failed to load CSV profile.");
    while (1) {}
  }

  Wire.begin();
  delay(100);

  if (!ina226.init()) {
    Serial.println("INA226 not detected.");
    while (1) {}
  }

  ina226.setCorrectionFactor(INA_CORRECTION_FACTOR);
  ina226.setAverage(INA226_AVERAGE_16);
  ina226.setConversionTime(INA226_CONV_TIME_1100);
  ina226.setMeasureMode(INA226_CONTINUOUS);
  ina226.waitUntilConversionCompleted();

  Serial.println("UNO R4 WiFi DAC CSV time-series load controller ready.");
  Serial.print("DAC output pin: A0");
  Serial.print(" | DAC max code: ");
  Serial.print(DAC_MAX_CODE);
  Serial.print(" | DAC max voltage: ");
  Serial.print(dacVoltageFromCode(DAC_MAX_CODE), 4);
  Serial.println(" V");

  Serial.print("Digital start input: D");
  Serial.print(START_SIGNAL_PIN);
  Serial.print(" | Current state: ");
  Serial.println(previousStartSignalState == START_SIGNAL_ACTIVE ? "HIGH" : "LOW");

  Serial.print("Startup DAC preload: ");
  Serial.print(USE_DAC_START_PRELOAD ? "ON" : "OFF");
  Serial.print(" | StartDAC=");
  Serial.print(DAC_START_CODE);
  Serial.print(" | Vdac=");
  Serial.print(dacVoltageFromCode(DAC_START_CODE), 4);
  Serial.println(" V");

  Serial.print("Loaded CSV profile points: ");
  Serial.println(profileLength);

  Serial.println("Each 15-minute profile point is played for 7.5 seconds.");
  Serial.println("Digital HIGH starts profile. Digital LOW stops and resets profile.");

  printHelp();

  // If the signal is already HIGH at boot, start immediately.
  if (previousStartSignalState == START_SIGNAL_ACTIVE) {
    Serial.println("Start signal already HIGH at boot. Starting profile.");
    startProfile(true);
  }
}

// -------------------------
// Main loop
// -------------------------
void loop() {
  handleSerial();
  handleStartSignalInput();

  unsigned long now = millis();

  updateProfile();

  if (now - lastControlMs >= controlIntervalMs) {
    lastControlMs = now;
    controlLoop();
  }

  if (now - lastPrintMs >= printIntervalMs) {
    lastPrintMs = now;
    readINA226();
    printStatus();
  }
}