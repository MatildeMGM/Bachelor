// sketch.ino
// Runs on the MCU side (Arduino sketch controlling IO)

#include <LiquidCrystal.h>
#include <Arduino_RouterBridge.h>

// LCD pins: rs, enable, d4, d5, d6, d7
LiquidCrystal lcd(12, 11, 5, 4, 3, 2);

const int switchPin = 6;

int switchState = 0;
int prevSwitchState = 0;

static void printReply(int reply) {
  switch (reply) {
    case 0: lcd.print("Yes"); break;
    case 1: lcd.print("Most likely"); break;
    case 2: lcd.print("Certainly"); break;
    case 3: lcd.print("Outlook good"); break;
    case 4: lcd.print("Unsure"); break;
    case 5: lcd.print("Ask again"); break;
    case 6: lcd.print("Doubtful"); break;
    case 7: lcd.print("No"); break;
    default: lcd.print("Unsure"); break;
  }
}

void setup() {
  lcd.begin(16, 2);
  pinMode(switchPin, INPUT);

  lcd.print("Ask the");
  lcd.setCursor(0, 1);
  lcd.print("Crystal Ball!");

  Bridge.begin();

  // Wait until Python side is ready
  bool started = false;
  while (!started) {
    Bridge.call("linux_started").result(started);
  }
}

void loop() {
  switchState = digitalRead(switchPin);

  // Detect state change (tilt)
  if (switchState != prevSwitchState) {
    // Trigger when it goes LOW (same behavior as your original)
    if (switchState == LOW) {

      int reply = 4;  // fallback = "Unsure"
      bool ok = Bridge.call("get_crystal_reply_index").result(reply);
      if (!ok) {
        reply = 4;
      }

      // Clamp to 0..7 in case Python returns something unexpected
      if (reply < 0) reply = 0;
      if (reply > 7) reply = 7;

      lcd.clear();
      lcd.setCursor(0, 0);
      lcd.print("the ball says:");
      lcd.setCursor(0, 1);
      printReply(reply);
    }
  }

  prevSwitchState = switchState;
}