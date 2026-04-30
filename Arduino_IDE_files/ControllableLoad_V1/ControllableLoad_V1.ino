#include <Wire.h>
#include <INA226_WE.h>
#include <math.h>

#define INA226_ADDRESS 0x40

INA226_WE ina226(&Wire, INA226_ADDRESS);

// -------------------------
// DAC settings
// -------------------------
const int DAC_PIN = A0;          // UNO R4 WiFi DAC pin
const float DAC_REF_V = 5.0f;    // DAC full-scale reference
const float DAC_MAX_V = 2.5f;    // clamp DAC output to max 2.5 V
const int DAC_MAX_CODE = (int)((DAC_MAX_V / DAC_REF_V) * 4095.0f + 0.5f);

// -------------------------
// INA correction
// -------------------------
const float INA_CORRECTION_FACTOR = 0.856f;

// -------------------------
// Mode
// -------------------------
enum ControlMode {
  MODE_CURRENT,
  MODE_POWER
};

ControlMode controlMode = MODE_CURRENT;

// -------------------------
// User settings
// -------------------------
bool loadEnabled = false;

float setCurrent_A = 0.10f;
float setPower_W   = 0.50f;
float I_MAX_A      = 0.80f;
float P_MAX_W      = 3.00f;

// Optional low-voltage fault
bool enableBusLowFault = false;
float BUS_MIN_V = 0.10f;

// -------------------------
// Control behavior
// -------------------------
int dacCode = 0;

unsigned long controlIntervalMs = 40;
unsigned long printIntervalMs   = 500;

unsigned long lastControlMs = 0;
unsigned long lastPrintMs = 0;

// Dead-zone / knee handling
const int DAC_KNEE_CODE = 1400;
const int DAC_FAST_APPROACH_TARGET = 1360;
const float CURRENT_FLOW_THRESHOLD_A = 0.010f;

// Step sizes
const int STEP_FAST     = 60;
const int STEP_MEDIUM   = 6;
const int STEP_SMALL    = 2;
const int STEP_TINY     = 1;
const int STEP_BACKOFF  = 12;

// Filter / damping
float filteredCurrent_A = 0.0f;
float filteredPower_W   = 0.0f;
bool filterInitialized  = false;

const float CURRENT_FILTER_ALPHA = 0.18f;
const float POWER_FILTER_ALPHA   = 0.18f;
const float CURRENT_DEADBAND_A   = 0.003f;
const float POWER_DEADBAND_W     = 0.005f;

// Soft limit margin
const float SOFT_LIMIT_FRAC = 0.92f;

// Dynamic hard-fault margins above user limits
const float CURRENT_FAULT_MARGIN_A = 0.08f;
const float POWER_FAULT_MARGIN_W   = 0.20f;

// -------------------------
// Weak source collapse detection
// -------------------------
float healthyBusVoltage_V = 0.0f;
const float COLLAPSE_FRAC = 0.80f;   // collapse if bus < 80% of healthy voltage
const int COLLAPSE_BACKOFF = 100;     // stronger backoff in collapse

// -------------------------
// Measurements
// -------------------------
float shuntVoltage_mV = 0.0f;
float busVoltage_V    = 0.0f;
float current_mA      = 0.0f;
float power_mW        = 0.0f;

float current_A = 0.0f;
float power_W   = 0.0f;

// -------------------------
// Fault latch
// -------------------------
bool faultLatched = false;
String faultMessage = "";

// -------------------------
// Helpers
// -------------------------
void setDACCode(int value) {
  if (value < 0) value = 0;
  if (value > DAC_MAX_CODE) value = DAC_MAX_CODE;
  dacCode = value;
  analogWrite(DAC_PIN, dacCode);
}

float dacVoltageFromCode(int code) {
  return (code / 4095.0f) * DAC_REF_V;
}

void stopLoad() {
  loadEnabled = false;
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

void readINA226() {
  shuntVoltage_mV = ina226.getShuntVoltage_mV();
  busVoltage_V    = ina226.getBusVoltage_V();
  current_mA      = ina226.getCurrent_mA();
  power_mW        = ina226.getBusPower();

  current_A = current_mA / 1000.0f;
  power_W   = power_mW / 1000.0f;

  if (shuntVoltage_mV < 0) shuntVoltage_mV = 0;
  if (busVoltage_V < 0) busVoltage_V = 0;
  if (current_A < 0) current_A = 0;
  if (power_W < 0) power_W = 0;

  if (!filterInitialized) {
    filteredCurrent_A = current_A;
    filteredPower_W   = power_W;
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

void printStatus() {
  float hardCurrentLimit = I_MAX_A + CURRENT_FAULT_MARGIN_A;
  float hardPowerLimit   = P_MAX_W + POWER_FAULT_MARGIN_W;

  float iAllowedByPower = I_MAX_A;
  if (busVoltage_V > 0.1f) {
    float pLimitedCurrent = P_MAX_W / busVoltage_V;
    if (pLimitedCurrent < iAllowedByPower) {
      iAllowedByPower = pLimitedCurrent;
    }
  }

  float effectiveCurrentTarget = setCurrent_A;
  if (effectiveCurrentTarget > iAllowedByPower) {
    effectiveCurrentTarget = iAllowedByPower;
  }

  float effectivePowerTarget = setPower_W;
  if (effectivePowerTarget > P_MAX_W) {
    effectivePowerTarget = P_MAX_W;
  }

  Serial.print("State=");
  if (faultLatched) Serial.print("FAULT");
  else if (loadEnabled) Serial.print("ON");
  else Serial.print("OFF");

  Serial.print(" | Mode=");
  Serial.print(controlMode == MODE_CURRENT ? "CURRENT" : "POWER");

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

  Serial.print(" | Vshunt=");
  Serial.print(shuntVoltage_mV, 4);
  Serial.print(" mV");

  Serial.print(" | DAC=");
  Serial.print(dacCode);

  Serial.print(" | Vdac=");
  Serial.print(dacVoltageFromCode(dacCode), 4);
  Serial.print(" V");

  Serial.print(" | Iset=");
  Serial.print(setCurrent_A, 4);
  Serial.print(" A");

  Serial.print(" | Ieff=");
  Serial.print(effectiveCurrentTarget, 4);
  Serial.print(" A");

  Serial.print(" | Pset=");
  Serial.print(setPower_W, 4);
  Serial.print(" W");

  Serial.print(" | Peff=");
  Serial.print(effectivePowerTarget, 4);
  Serial.print(" W");

  Serial.print(" | Imax=");
  Serial.print(I_MAX_A, 4);
  Serial.print(" A");

  Serial.print(" | Ihard=");
  Serial.print(hardCurrentLimit, 4);
  Serial.print(" A");

  Serial.print(" | Pmax=");
  Serial.print(P_MAX_W, 4);
  Serial.print(" W");

  Serial.print(" | Phard=");
  Serial.print(hardPowerLimit, 4);
  Serial.print(" W");

  Serial.print(" | Vhealthy=");
  Serial.print(healthyBusVoltage_V, 4);
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
  Serial.println("  help              -> show commands");
  Serial.println("  status            -> print one status line");
  Serial.println("  on                -> enable regulation");
  Serial.println("  off               -> disable load");
  Serial.println("  resetfault        -> clear fault latch");
  Serial.println("  mode i            -> constant current mode");
  Serial.println("  mode p            -> constant power mode");
  Serial.println("  seti 0.10         -> set current target in A");
  Serial.println("  setp 0.50         -> set power target in W");
  Serial.println("  maxi 0.80         -> set hard current limit in A");
  Serial.println("  maxp 3.00         -> set hard power limit in W");
  Serial.println("  dac 1.20          -> manually set DAC voltage (0 to 2.5 V)");
  Serial.println("  interval 40       -> set control interval in ms");
  Serial.println("  busfault on       -> enable low-bus fault");
  Serial.println("  busfault off      -> disable low-bus fault");
  Serial.println();
}

void handleSerial() {
  if (!Serial.available()) return;

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

  if (cmd == "on") {
    if (faultLatched) {
      Serial.println("Cannot enable: fault is latched. Use resetfault first.");
      return;
    }
    loadEnabled = true;
    Serial.println("Regulation enabled.");
    return;
  }

  if (cmd == "off") {
    stopLoad();
    Serial.println("Load disabled.");
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

  if (cmd == "mode i") {
    controlMode = MODE_CURRENT;
    Serial.println("Mode set to constant current.");
    return;
  }

  if (cmd == "mode p") {
    controlMode = MODE_POWER;
    Serial.println("Mode set to constant power.");
    return;
  }

  if (cmd.startsWith("seti ")) {
    float v = cmd.substring(5).toFloat();
    if (v < 0) v = 0;
    setCurrent_A = v;
    Serial.print("Current target set to ");
    Serial.print(setCurrent_A, 4);
    Serial.println(" A");
    return;
  }

  if (cmd.startsWith("setp ")) {
    float v = cmd.substring(5).toFloat();
    if (v < 0) v = 0;
    setPower_W = v;
    Serial.print("Power target set to ");
    Serial.print(setPower_W, 4);
    Serial.println(" W");
    return;
  }

  if (cmd.startsWith("maxi ")) {
    float v = cmd.substring(5).toFloat();
    if (v < 0) v = 0;
    I_MAX_A = v;
    Serial.print("Hard current limit set to ");
    Serial.print(I_MAX_A, 4);
    Serial.println(" A");
    return;
  }

  if (cmd.startsWith("maxp ")) {
    float v = cmd.substring(5).toFloat();
    if (v < 0) v = 0;
    P_MAX_W = v;
    Serial.print("Hard power limit set to ");
    Serial.print(P_MAX_W, 4);
    Serial.println(" W");
    return;
  }

  if (cmd.startsWith("dac ")) {
    if (faultLatched) {
      Serial.println("Cannot set DAC: fault is latched. Use resetfault first.");
      return;
    }

    float v = cmd.substring(4).toFloat();
    if (v < 0.0f) v = 0.0f;
    if (v > DAC_MAX_V) v = DAC_MAX_V;

    int code = (int)((v / DAC_REF_V) * 4095.0f + 0.5f);
    setDACCode(code);

    Serial.print("DAC set to ~");
    Serial.print(dacVoltageFromCode(dacCode), 4);
    Serial.println(" V");
    return;
  }

  if (cmd.startsWith("interval ")) {
    int v = cmd.substring(9).toInt();
    if (v < 10) v = 10;
    controlIntervalMs = (unsigned long)v;
    Serial.print("Control interval set to ");
    Serial.print(controlIntervalMs);
    Serial.println(" ms");
    return;
  }

  Serial.println("Unknown command. Type 'help'.");
}

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

  // Update healthy source voltage estimate
  if (healthyBusVoltage_V <= 0.0f) {
    healthyBusVoltage_V = busVoltage_V;
  }

  if (busVoltage_V > healthyBusVoltage_V) {
    healthyBusVoltage_V = busVoltage_V;
  } else {
    healthyBusVoltage_V = 0.995f * healthyBusVoltage_V + 0.005f * busVoltage_V;
  }

  float hardCurrentLimit = I_MAX_A + CURRENT_FAULT_MARGIN_A;
  float hardPowerLimit   = P_MAX_W + POWER_FAULT_MARGIN_W;

  // Hard faults
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

  // Dynamic current ceiling from power
  float iAllowedByPower = I_MAX_A;
  if (busVoltage_V > 0.1f) {
    float pLimitedCurrent = P_MAX_W / busVoltage_V;
    if (pLimitedCurrent < iAllowedByPower) {
      iAllowedByPower = pLimitedCurrent;
    }
  }

  float effectiveCurrentTarget = setCurrent_A;
  if (effectiveCurrentTarget > iAllowedByPower) {
    effectiveCurrentTarget = iAllowedByPower;
  }

  float effectivePowerTarget = setPower_W;
  if (effectivePowerTarget > P_MAX_W) {
    effectivePowerTarget = P_MAX_W;
  }

  // Soft protection zones
  float softCurrentLimit = SOFT_LIMIT_FRAC * iAllowedByPower;
  float softPowerLimit   = SOFT_LIMIT_FRAC * P_MAX_W;

  if (power_W >= softPowerLimit) {
    setDACCode(dacCode - STEP_BACKOFF);
    return;
  }

  if (filteredCurrent_A >= softCurrentLimit) {
    setDACCode(dacCode - STEP_BACKOFF);
    return;
  }

  // Fast ramp through dead zone
  if ((filteredCurrent_A < CURRENT_FLOW_THRESHOLD_A) && (dacCode < DAC_FAST_APPROACH_TARGET)) {
    setDACCode(dacCode + STEP_FAST);
    return;
  }

  // Constant current mode
  if (controlMode == MODE_CURRENT) {
    float error_A = effectiveCurrentTarget - filteredCurrent_A;
    float absError_A = fabs(error_A);

    if (absError_A <= CURRENT_DEADBAND_A) {
      return;
    }

    int step = STEP_TINY;
    if (absError_A > 0.080f) {
      step = STEP_MEDIUM;
    } else if (absError_A > 0.020f) {
      step = STEP_SMALL;
    } else {
      step = STEP_TINY;
    }

    if (error_A > 0) {
      setDACCode(dacCode + step);
    } else {
      setDACCode(dacCode - STEP_SMALL);
    }
  }

  // Constant power mode
  if (controlMode == MODE_POWER) {
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

    int step = STEP_TINY;
    if (absError_W > 0.30f) {
      step = STEP_MEDIUM;
    } else if (absError_W > 0.05f) {
      step = STEP_SMALL;
    } else {
      step = STEP_TINY;
    }

    if (error_W > 0) {
      setDACCode(dacCode + step);
    } else {
      setDACCode(dacCode - STEP_SMALL);
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  analogWriteResolution(12);
  setDACCode(0);

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

  Serial.println("UNO R4 WiFi DAC controller ready");
  Serial.println("DAC output on A0, clamped to 2.5 V max");
  Serial.println("Supports constant current and constant power");
  Serial.println("Includes weak-source collapse handling in power mode");
  printHelp();
}

void loop() {
  handleSerial();

  unsigned long now = millis();

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