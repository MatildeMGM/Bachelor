#include <Arduino_RouterBridge.h>

// Built-in LED (for quick visual test)
const int TEST_LED = LED_BUILTIN;

// Variables for testing
float electricityprice = 0.0;
int hour = 0;
bool priceReceived = false;

// Function prototype
bool apply_price_frame(String payload);

void setup() {
  Serial.begin(9600);
  delay(1000);

  Serial.println("=== TEST SKETCH START ===");

  // Initialize LED
  pinMode(TEST_LED, OUTPUT);
  digitalWrite(TEST_LED, LOW);

  // Initialize Bridge
  Bridge.begin();
  Bridge.provide("apply_price_frame", apply_price_frame);

  Serial.println("Bridge initialized and ready");
}

void loop() {
  // Print status continuously
  Serial.print("Price: ");
  Serial.print(electricityprice, 5);
  Serial.print(" | Hour: ");
  Serial.print(hour);
  Serial.print(" | Received: ");
  Serial.print(priceReceived);

  // Simple logic test (simulate EMS behavior)
  if (electricityprice >= 0.6) {
    Serial.print(" | Mode: HIGH PRICE (LED ON)");
    digitalWrite(TEST_LED, HIGH);
  } else {
    Serial.print(" | Mode: LOW PRICE (LED OFF)");
    digitalWrite(TEST_LED, LOW);
  }

  Serial.println();

  delay(2000);
}


// Function that receives data from Python
bool apply_price_frame(String payload) {

  Serial.print("Received payload: ");
  Serial.println(payload);

  // Check correct format
  if (!payload.startsWith("PRICE,")) {
    Serial.println("ERROR: Invalid format");
    return false;
  }

  int firstComma = payload.indexOf(',');
  int secondComma = payload.indexOf(',', firstComma + 1);

  if (firstComma < 0 || secondComma < 0) {
    Serial.println("ERROR: Malformed payload");
    return false;
  }

  // Extract values
  electricityprice = payload.substring(firstComma + 1, secondComma).toFloat();
  hour = payload.substring(secondComma + 1).toInt();
  priceReceived = true;

  // Debug print
  Serial.print("Parsed price: ");
  Serial.print(electricityprice, 5);
  Serial.print(" | Parsed hour: ");
  Serial.println(hour);

  return true;
}