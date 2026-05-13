#include <Arduino_RouterBridge.h>

float electricityprice = 0.0;
int hour = 0;
bool priceReceived = false;

bool apply_price_frame(String payload);

Serial.begin(9600);
delay(2000);
Serial.println("=== SKETCH BOOTED ===");

pinMode(LED_BUILTIN, OUTPUT);
for (int i = 0; i < 3; i++) {
  digitalWrite(LED_BUILTIN, HIGH);
  delay(300);
  digitalWrite(LED_BUILTIN, LOW);
  delay(300);
}

void loop() {
  if (electricityprice >= 0.6) {
    digitalWrite(LED_BUILTIN, HIGH);
  } else {
    digitalWrite(LED_BUILTIN, LOW);
  }

  Serial.print("Price: ");
  Serial.print(electricityprice, 5);
  Serial.print(" | Hour: ");
  Serial.print(hour);
  Serial.print(" | Received: ");
  Serial.println(priceReceived);

  delay(2000);
}

bool apply_price_frame(String payload) {
  Serial.print("Received payload: ");
  Serial.println(payload);

  if (!payload.startsWith("PRICE,")) {
    Serial.println("ERROR: Invalid payload format");
    return false;
  }

  int firstComma = payload.indexOf(',');
  int secondComma = payload.indexOf(',', firstComma + 1);

  if (firstComma < 0 || secondComma < 0) {
    Serial.println("ERROR: Malformed payload");
    return false;
  }

  electricityprice = payload.substring(firstComma + 1, secondComma).toFloat();
  hour = payload.substring(secondComma + 1).toInt();
  priceReceived = true;

  Serial.print("Updated price: ");
  Serial.println(electricityprice, 5);
  Serial.print("Updated hour: ");
  Serial.println(hour);

  return true;
}