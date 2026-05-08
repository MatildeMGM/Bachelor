#include <Wire.h>
#include <INA226_WE.h>
#include <math.h>
#include <stdlib.h>

#include "profile_csv.h"

#define INA226_ADDRESS 0x40

INA226_WE ina226(&Wire, INA226_ADDRESS);

// -------------------------
// DAC settings
// -------------------------
const int DAC_PIN = A0;          // UNO R4 WiFi DAC pin
const float DAC_REF_V = 5.0f;    // DAC full-scale reference
const float DAC_MAX_V = 5.0f;    // Clamp DAC output to max 2.5 V
const int DAC_MAX_CODE = (int)((DAC_MAX_V / DAC_REF_V) * 4095.0f + 0.5f);

// -------------------------
// Startup DAC behavior
// -------------------------
// Your measurements show that DAC=1000 is too low.
// DAC around 1450-1500 is much closer to the useful MOSFET region.
int DAC_START_CODE = 1450;
bool USE_DAC_START_PRELOAD = true;

// Only preload if the requested profile power is above this.
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

// Original data interval: 15 minutes.
// Playback interval: 7.5 seconds.
// 96 points therefore gives 12 minutes per simulated day.
const unsigned long PROFILE_STEP_INTERVAL_MS = 7500;

// Set this depending on the units in profile_csv.h.
// Current file uses power_mW, so this should remain true.
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

// Optional low-voltage fault
bool enableBusLowFault = false;
float BUS_MIN_V = 0.10f;

// Current power target
float setPower_W = 0.0f;

// -------------------------
// Control behavior
// -------------------------
int dacCode = 0;

unsigned long controlIntervalMs = 40;
unsigned long printIntervalMs = 500;

unsigned long lastControlMs = 0;
unsigned long lastPrintMs = 0;

// Dead-zone / knee handling
const int DAC_KNEE_CODE = 1400;

// Fast approach should go above the normal MOSFET knee.
// This prevents the controller from spending too long around DAC 1400-1500.
int DAC_FAST_APPROACH_TARGET = 1600;

// Threshold for deciding whether current has started flowing.
const float CURRENT_FLOW_THRESHOLD_A = 0.010f;

// Step sizes
int STEP_FAST = 80;
const int STEP_MEDIUM = 6;
const int STEP_SMALL = 2;
const int STEP_TINY = 1;
const int STEP_BACKOFF = 12;

// Relative power control step sizes.
// These are intentionally larger than the old tiny low-power steps.
const int STEP_POWER_VERY_FAR = 20;
const int STEP_POWER_FAR = 12;
const int STEP_POWER_MEDIUM = 6;
const int STEP_POWER_NEAR = 3;

// Filter / damping
float filteredCurrent_A = 0.0f;
float filteredPower_W = 0.0f;
bool filterInitialized = false;

const float CURRENT_FILTER_ALPHA = 0.18f;
const float POWER_FILTER_ALPHA = 0.18f;
const float POWER_DEADBAND_W = 0.005f;

// Soft limit margin
const float SOFT_LIMIT_FRAC = 0.92f;

// Dynamic hard-fault margins above user limits
const float CURRENT_FAULT_MARGIN_A = 0.08f;
const float POWER_FAULT_MARGIN_W = 0.20f;

// -------------------------
// Weak source collapse detection
// -------------------------
float healthyBusVoltage_V = 0.0f;

// Your faster script used 0.90 and smaller backoff.
// The original CSV script used 0.80 and larger backoff.
// This is a moderate setting.
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
// Helpers
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

float profileTimeHours(int index) {
  return index * 0.25f;
}

void stopLoad() {
  loadEnabled = false;
  profileRunning = false;
  setDACCode(0);
  healthyBusVoltage_V = 0.0f;
}

void tripFault(const String &msg) {
  faultLatched = true;
  faultMessage = msg;
  stopLoad();

  Serial.print("FAULT: ");
  Serial.println(faultMessage);
}

void clearFault() {
  faultLatched = false;
  faultMessage = "";
  stopLoad();
  filterInitialized = false;

  Serial.println("Fault cleared. Load remains OFF.");
}

// -------------------------
// CSV parsing
// -------------------------
// This parser expects a CSV with the power value in the last column.
// For your file, the columns are:
// time_slot,time_of_day,power_mW
//
// It skips the header line automatically.
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

    // Skip header line if it contains letters.
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

    // Find last comma. The final CSV column is the power value.
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

  setPower_W = powerProfile_W[0];
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
// Time-series handling
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

void preloadDACForStartup() {
  if (!USE_DAC_START_PRELOAD) {
    return;
  }

  if (setPower_W <= START_PRELOAD_MIN_POWER_W) {
    setDACCode(0);
    return;
  }

  setDACCode(DAC_START_CODE);

  Serial.print("Startup DAC preload applied: DAC=");
  Serial.print(dacCode);
  Serial.print(" | Vdac=");
  Serial.print(dacVoltageFromCode(dacCode), 4);
  Serial.println(" V");
}

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
    profileIndex = 0;
  }

  if (profileIndex >= profileLength) {
    profileIndex = 0;
  }

  setPower_W = powerProfile_W[profileIndex];

  loadEnabled = true;
  profileRunning = true;
  filterInitialized = false;
  healthyBusVoltage_V = 0.0f;

  preloadDACForStartup();

  lastProfileStepMs = millis();

  Serial.println("Time-series profile started.");
  printProfilePoint();
}

void stopProfile() {
  stopLoad();
  Serial.println("Time-series profile stopped. Load disabled.");
}

void updateProfile() {
  if (!profileRunning) {
    return;
  }

  if (!loadEnabled) {
    return;
  }

  if (faultLatched) {
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
        stopLoad();
        Serial.println("Time-series profile completed. Load disabled.");
        return;
      }
    }

    setPower_W = powerProfile_W[profileIndex];
    printProfilePoint();
  }
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

  Serial.print(" | Ifilt=");
  Serial.print(filteredCurrent_A, 4);
  Serial.print(" A");

  Serial.print(" | P=");
  Serial.print(power_W, 4);
  Serial.print(" W");

  Serial.print(" | Pfilt=");
  Serial.print(filteredPower_W, 4);
  Serial.print(" W");

  Serial.print(" | Pset=");
  Serial.print(setPower_W, 4);
  Serial.print(" W");

  Serial.print(" | Vshunt=");
  Serial.print(shuntVoltage_mV, 4);
  Serial.print(" mV");

  Serial.print(" | DAC=");
  Serial.print(dacCode);

  Serial.print(" | Vdac=");
  Serial.print(dacVoltageFromCode(dacCode), 4);
  Serial.print(" V");

  Serial.print(" | StartDAC=");
  Serial.print(DAC_START_CODE);

  Serial.print(" | FastTarget=");
  Serial.print(DAC_FAST_APPROACH_TARGET);

  Serial.print(" | FastStep=");
  Serial.print(STEP_FAST);

  Serial.print(" | Repeat=");
  Serial.print(repeatProfile ? "ON" : "OFF");

  if (faultLatched) {
    Serial.print(" | Fault=");
    Serial.print(faultMessage);
  }

  Serial.println();
}

void printHelp() {
  Serial.println();
  Serial.println("Commands:");
  Serial.println("  help              -> show commands");
  Serial.println("  status            -> print one status line");
  Serial.println("  start             -> start or continue time-series profile");
  Serial.println("  restart           -> start profile from first point");
  Serial.println("  stop              -> stop profile and disable load");
  Serial.println("  resetfault        -> clear fault latch");
  Serial.println("  maxp 3.00         -> set hard power limit in W");
  Serial.println("  maxi 0.80         -> set hard current limit in A");
  Serial.println("  interval 40       -> set control interval in ms");
  Serial.println("  print 500         -> set status print interval in ms");
  Serial.println("  busfault on       -> enable low-bus fault");
  Serial.println("  busfault off      -> disable low-bus fault");
  Serial.println("  repeat on         -> loop profile continuously");
  Serial.println("  repeat off        -> stop after one profile");
  Serial.println("  preload on        -> enable startup DAC preload");
  Serial.println("  preload off       -> disable startup DAC preload");
  Serial.println("  startdac 1450     -> set startup DAC preload code");
  Serial.println("  fasttarget 1600   -> set fast approach DAC target");
  Serial.println("  faststep 80       -> set fast approach DAC step");
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
    stopProfile();
    return;
  }

  if (cmd == "resetfault") {
    clearFault();
    return;
  }

  if (cmd == "busfault on") {
    enableBusLowFault = true;
    Serial.println("Low-bus fault enabled.");
    return;
  }

  if (cmd == "busfault off") {
    enableBusLowFault = false;
    Serial.println("Low-bus fault disabled.");
    return;
  }

  if (cmd == "repeat on") {
    repeatProfile = true;
    Serial.println("Profile repeat enabled.");
    return;
  }

  if (cmd == "repeat off") {
    repeatProfile = false;
    Serial.println("Profile repeat disabled.");
    return;
  }

  if (cmd == "preload on") {
    USE_DAC_START_PRELOAD = true;
    Serial.println("Startup DAC preload enabled.");
    return;
  }

  if (cmd == "preload off") {
    USE_DAC_START_PRELOAD = false;
    Serial.println("Startup DAC preload disabled.");
    return;
  }

  if (cmd.startsWith("maxi ")) {
    float v = cmd.substring(5).toFloat();

    if (v < 0.0f) {
      v = 0.0f;
    }

    I_MAX_A = v;

    Serial.print("Hard current limit set to ");
    Serial.print(I_MAX_A, 4);
    Serial.println(" A");
    return;
  }

  if (cmd.startsWith("maxp ")) {
    float v = cmd.substring(5).toFloat();

    if (v < 0.0f) {
      v = 0.0f;
    }

    P_MAX_W = v;

    Serial.print("Hard power limit set to ");
    Serial.print(P_MAX_W, 4);
    Serial.println(" W");
    return;
  }

  if (cmd.startsWith("interval ")) {
    int v = cmd.substring(9).toInt();

    if (v < 10) {
      v = 10;
    }

    controlIntervalMs = (unsigned long)v;

    Serial.print("Control interval set to ");
    Serial.print(controlIntervalMs);
    Serial.println(" ms");
    return;
  }

  if (cmd.startsWith("print ")) {
    int v = cmd.substring(6).toInt();

    if (v < 100) {
      v = 100;
    }

    printIntervalMs = (unsigned long)v;

    Serial.print("Print interval set to ");
    Serial.print(printIntervalMs);
    Serial.println(" ms");
    return;
  }

  if (cmd.startsWith("startdac ")) {
    int v = cmd.substring(9).toInt();

    if (v < 0) {
      v = 0;
    }

    if (v > DAC_MAX_CODE) {
      v = DAC_MAX_CODE;
    }

    DAC_START_CODE = v;

    Serial.print("Startup DAC code set to ");
    Serial.print(DAC_START_CODE);
    Serial.print(" | Vdac=");
    Serial.print(dacVoltageFromCode(DAC_START_CODE), 4);
    Serial.println(" V");
    return;
  }

  if (cmd.startsWith("fasttarget ")) {
    int v = cmd.substring(11).toInt();

    if (v < 0) {
      v = 0;
    }

    if (v > DAC_MAX_CODE) {
      v = DAC_MAX_CODE;
    }

    DAC_FAST_APPROACH_TARGET = v;

    Serial.print("Fast approach target set to DAC=");
    Serial.print(DAC_FAST_APPROACH_TARGET);
    Serial.print(" | Vdac=");
    Serial.print(dacVoltageFromCode(DAC_FAST_APPROACH_TARGET), 4);
    Serial.println(" V");
    return;
  }

  if (cmd.startsWith("faststep ")) {
    int v = cmd.substring(9).toInt();

    if (v < 1) {
      v = 1;
    }

    if (v > 500) {
      v = 500;
    }

    STEP_FAST = v;

    Serial.print("Fast approach step set to ");
    Serial.println(STEP_FAST);
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

  // Relative power tells us how far we are from the target.
  // This fixes the slow behavior at low targets such as 0.044 W.
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
    // Above target.
    // Back off more strongly if we overshot significantly.
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
    stopLoad();
    return;
  }

  if (!loadEnabled) {
    setDACCode(0);
    return;
  }

  // Update healthy source voltage estimate.
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

  // Hard faults.
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

  // If target is effectively zero, turn off the DAC.
  if (effectivePowerTarget <= 0.0f) {
    setDACCode(0);
    return;
  }

  // Dynamic current ceiling from power limit.
  float iAllowedByPower = I_MAX_A;

  if (busVoltage_V > 0.1f) {
    float pLimitedCurrent = P_MAX_W / busVoltage_V;

    if (pLimitedCurrent < iAllowedByPower) {
      iAllowedByPower = pLimitedCurrent;
    }
  }

  // Soft protection zones.
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

  // Fast ramp through MOSFET dead-zone.
  //
  // This intentionally does not require Pset > 0.20 W.
  // Your profile contains small targets around 0.04 W, and the old condition
  // made those points ramp far too slowly.
  if ((effectivePowerTarget > START_PRELOAD_MIN_POWER_W) &&
      (filteredCurrent_A < CURRENT_FLOW_THRESHOLD_A) &&
      (dacCode < DAC_FAST_APPROACH_TARGET)) {
    setDACCode(dacCode + STEP_FAST);
    return;
  }

  // Constant power control with relative-error based step size.
  applyRelativePowerControl(effectivePowerTarget);
}

// -------------------------
// Setup
// -------------------------
void setup() {
  Serial.begin(115200);
  delay(1000);

  analogWriteResolution(12);
  setDACCode(0);

  if (!loadProfileFromCSV()) {
    Serial.println("ERROR: Failed to load CSV profile.");
    while (1) {}
  }

  Wire.begin();
  delay(100);

  if (!ina226.init()) {
    Serial.println("INA226 not detected");
    while (1) {}
  }

  ina226.setCorrectionFactor(INA_CORRECTION_FACTOR);
  ina226.setAverage(INA226_AVERAGE_16);
  ina226.setConversionTime(INA226_CONV_TIME_1100);
  ina226.setMeasureMode(INA226_CONTINUOUS);
  ina226.waitUntilConversionCompleted();

  Serial.println("UNO R4 WiFi DAC CSV time-series load controller ready");
  Serial.println("DAC output on A0, clamped to 2.5 V max");

  Serial.print("DAC max code: ");
  Serial.print(DAC_MAX_CODE);
  Serial.print(" | DAC max voltage: ");
  Serial.print(dacVoltageFromCode(DAC_MAX_CODE), 4);
  Serial.println(" V");

  Serial.print("Startup DAC preload: ");
  Serial.print(USE_DAC_START_PRELOAD ? "ON" : "OFF");
  Serial.print(" | StartDAC=");
  Serial.print(DAC_START_CODE);
  Serial.print(" | Vdac=");
  Serial.print(dacVoltageFromCode(DAC_START_CODE), 4);
  Serial.println(" V");

  Serial.print("Fast approach target: DAC=");
  Serial.print(DAC_FAST_APPROACH_TARGET);
  Serial.print(" | Vdac=");
  Serial.print(dacVoltageFromCode(DAC_FAST_APPROACH_TARGET), 4);
  Serial.print(" V");
  Serial.print(" | FastStep=");
  Serial.println(STEP_FAST);

  Serial.print("Loaded CSV profile points: ");
  Serial.println(profileLength);

  Serial.println("Each 15-minute profile point is played for 7.5 seconds.");
  Serial.println("One 96-point simulated day takes 12 minutes.");
  Serial.println("Type 'start' to begin, 'restart' to restart, 'stop' to disable, or 'help' for commands.");

  printHelp();
}

// -------------------------
// Main loop
// -------------------------
void loop() {
  handleSerial();

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