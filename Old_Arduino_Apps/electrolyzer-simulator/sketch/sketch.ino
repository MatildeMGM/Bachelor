#include <Arduino_RouterBridge.h>
#include <LiquidCrystal.h>

LiquidCrystal lcd(12, 11, 5, 4, 3, 2);

static const int LCD_COLS = 16;
static const int LCD_ROWS = 2;

struct SimFrame {
  unsigned long step = 0;
  float windKW = 0.0f;
  float usedKW = 0.0f;
  float h2TotalKG = 0.0f;
  float efficiency = 0.0f;
  String state[4] = {"OFF", "OFF", "OFF", "OFF"};
};

SimFrame currentFrame;

String fit16(String s) {
  s.replace("\n", " ");
  s.replace("\r", " ");
  if ((int)s.length() > LCD_COLS) s = s.substring(0, LCD_COLS);
  while ((int)s.length() < LCD_COLS) s += ' ';
  return s;
}

String shortState(const String &s) {
  if (s == "PRODUCTION") return "P";
  if (s == "STANDBY") return "S";
  if (s == "HOT_START") return "H";
  if (s == "COLD_START") return "C";
  return "O";
}

bool parseLine(const String &line, SimFrame &frame) {
  if (!line.startsWith("SIM,")) return false;

  int idx[10];
  int found = 0;
  for (int i = 0; i < line.length() && found < 10; i++) {
    if (line.charAt(i) == ',') idx[found++] = i;
  }
  if (found < 9) return false;

  frame.step = line.substring(idx[0] + 1, idx[1]).toInt();
  frame.windKW = line.substring(idx[1] + 1, idx[2]).toFloat();
  frame.usedKW = line.substring(idx[2] + 1, idx[3]).toFloat();
  frame.h2TotalKG = line.substring(idx[3] + 1, idx[4]).toFloat();
  frame.efficiency = line.substring(idx[4] + 1, idx[5]).toFloat();
  frame.state[0] = line.substring(idx[5] + 1, idx[6]);
  frame.state[1] = line.substring(idx[6] + 1, idx[7]);
  frame.state[2] = line.substring(idx[7] + 1, idx[8]);
  frame.state[3] = line.substring(idx[8] + 1);
  return true;
}

void renderLCD(const SimFrame &frame) {
  String line1 = "W" + String((int)frame.windKW) + " U" + String((int)frame.usedKW);
  String line2 = shortState(frame.state[0]) + shortState(frame.state[1]) + shortState(frame.state[2]) + shortState(frame.state[3]);
  line2 += " H" + String(frame.h2TotalKG, 1);

  lcd.setCursor(0, 0);
  lcd.print(fit16(line1));
  lcd.setCursor(0, 1);
  lcd.print(fit16(line2));
}

bool apply_sim_frame(String payload) {
  SimFrame parsed;
  if (!parseLine(payload, parsed)) {
    Monitor.print("Bad frame: ");
    Monitor.println(payload);
    return false;
  }

  currentFrame = parsed;
  Monitor.print("SIM step ");
  Monitor.print(currentFrame.step);
  Monitor.print(" wind=");
  Monitor.print(currentFrame.windKW, 1);
  Monitor.print(" used=");
  Monitor.print(currentFrame.usedKW, 1);
  Monitor.print(" h2=");
  Monitor.println(currentFrame.h2TotalKG, 3);

  renderLCD(currentFrame);
  return true;
}

void setup() {
  Monitor.begin();
  delay(1000);
  Monitor.println("Wind-H2 MCU bridge booting...");

  lcd.begin(LCD_COLS, LCD_ROWS);
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Wind-H2 ready");
  lcd.setCursor(0, 1);
  lcd.print("Awaiting input..");

  Bridge.begin();
  Bridge.provide("apply_sim_frame", apply_sim_frame);
}

void loop() {
  delay(5);
}
