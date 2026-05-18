/*
File: NANO_LED.ino

Description:
    The code was originally written for the project 
    "Monitoring, control and data collection of the hydrogen-solar-battery unit
    through IoT embedded microcontroller" 
    by Authors: Nicoline Simone Sachmann & Sofie Davidsen

    Arduino NANO IDE LED Control Code

Institution:
    Technical University of Denmark (DTU)

Date:
    2023-06
*/

#include <FastLED.h>

#define LED_PIN 8
#define NUM_LEDS 60 // der bruges 35 LED'er

const int RECIEVE_PIN_1 = 7; // input pin for scenario 1
const int RECIEVE_PIN_2 = 4; // input pin for scenario 2
const int RECIEVE_PIN_3 = 3; // input pin for scenario 3
const int RECIEVE_PIN_4 = 6; // input pin for scenario 4
const int RECIEVE_PIN_5 = 5; // input pin for scenario 5
const int RECIEVE_PIN_6 = 2; // input pin for scenario 5

int x1 = 0;
int x2 = 0;
int x3 = 0;
int x4 = 0;
int x5 = 0;
int x6 = 0;

CRGB leds[NUM_LEDS];

void setup() {
  // Define the LED pin as Output
  pinMode(LED_PIN, OUTPUT);
  pinMode(RECIEVE_PIN_1, INPUT);
  pinMode(RECIEVE_PIN_2, INPUT);
  pinMode(RECIEVE_PIN_3, INPUT);
  pinMode(RECIEVE_PIN_4, INPUT);
  pinMode(RECIEVE_PIN_5, INPUT);
  pinMode(RECIEVE_PIN_6, INPUT);

  Serial.begin(9600);

  // LED setup
  FastLED.addLeds<WS2812, LED_PIN, GRB>(leds, NUM_LEDS);
  FastLED.setMaxPowerInVoltsAndMilliamps(5, 500);
  FastLED.clear();
  FastLED.show();
}

void loop() {
  x1 = digitalRead(RECIEVE_PIN_1);
  x2 = digitalRead(RECIEVE_PIN_2);
  x3 = digitalRead(RECIEVE_PIN_3);
  x4 = digitalRead(RECIEVE_PIN_4);
  x5 = digitalRead(RECIEVE_PIN_5);
  x6 = digitalRead(RECIEVE_PIN_6);

  // If value received is 0 blink LED for 200 ms
  if (x1 == 1) {
    S1_LED();

  } else if (x2 == 1) {
    S2_LED();

  } else if (x3 == 1) {
    S3_LED();

  } else if (x4 == 1) {
    S4_LED();

  } else if (x5 == 1) {
    S5_LED();

  } else if (x6 == 1) {
    S6_LED();
  }

  delay(1500);
}

void S1_LED() {
  for (int i = 0; i < 7; i++) {
    leds[35 - i] = CRGB(25, 25, 255);
    FastLED.show();
    delay(50);
  }
  FastLED.clear();
}

void S2_LED() {
  for (int i = 0; i < 24; i++) {
    leds[i] = CRGB(25, 25, 255);
    if (i < 7) {
      leds[35 - i] = CRGB(25, 25, 255);
    }
    FastLED.show();
    delay(50);
  }
  FastLED.clear();
}

void S3_LED() {
  for (int i = 0; i < 13; i++) {
    leds[i] = CRGB(25, 25, 255);
    if (i < 7) {
      leds[35 - i] = CRGB(25, 25, 255);
    }
    FastLED.show();
    delay(80);
  }
  FastLED.clear();
}

void S4_LED() {
  for (int i = 0; i < 30; i++) {
    leds[i] = CRGB(25, 25, 255);
    FastLED.show();
    delay(50);
  }
  FastLED.clear();
}

void S5_LED() {
  for (int i = 0; i < 8; i++) {
    leds[i + 22] = CRGB(25, 25, 255);
    FastLED.show();
    delay(50);
  }
  FastLED.clear();
}

void S6_LED() {
  for (int i = 0; i < 18; i++) {
    leds[i + 12] = CRGB(25, 25, 255);
    FastLED.show();
    delay(50);
  }
  FastLED.clear();
}