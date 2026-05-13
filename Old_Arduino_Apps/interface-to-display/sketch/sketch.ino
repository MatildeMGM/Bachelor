#include <LiquidCrystal.h>
#include <Arduino_RouterBridge.h>

LiquidCrystal lcd(12, 11, 5, 4, 3, 2);

static const int LCD_COLS = 16;
static const int LCD_ROWS = 2;

static String fit16(String s) {
  if ((int)s.length() > LCD_COLS) s = s.substring(0, LCD_COLS);
  while ((int)s.length() < LCD_COLS) s += ' ';
  return s;
}

// IMPORTANT: match types that RouterBridge can deserialize reliably.
// Using String is supported in many examples, but if this still fails,
// we’ll switch to `const char*` or `char*` buffers next.
bool lcd_print(String line1, String line2) {
  Monitor.print("lcd_print called: ");
  Monitor.print(line1);
  Monitor.print(" | ");
  Monitor.println(line2);
  
  lcd.setCursor(0, 0);
  lcd.print(fit16(line1));
  lcd.setCursor(0, 1);
  lcd.print(fit16(line2));
  return true;
}

void setup() {
  Monitor.begin();
  delay(1000);
  Monitor.println("MCU booting...");
  
  lcd.begin(LCD_COLS, LCD_ROWS);
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Web UI ready");

  Bridge.begin();
  Bridge.provide("lcd_print", lcd_print);
}

void loop() {
  // Many examples leave loop empty; RouterBridge services requests internally.
  // Keep the loop light.
  delay(5);
}