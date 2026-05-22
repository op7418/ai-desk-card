// ai-desk-card · M5Paper Color port — Phase 1 (canonical M5Unified
// init pattern per https://docs.m5stack.com/en/arduino/papercolor/display).
//
// Key differences vs. my first attempt:
//   - cfg.clear_display = false (skip default clear)
//   - M5.Display.setEpdMode(epd_fastest)  ← REQUIRED to set refresh strategy
//   - Draw via M5Canvas sprite, push with canvas.pushSprite()  ← not display()
//
// Without setEpdMode, M5GFX doesn't know what refresh waveform to use on
// the Spectra 6 panel and silently skips pushing pixels.

#include <Arduino.h>
#include <M5Unified.h>

#ifndef CARD_VERSION
#define CARD_VERSION "0.10.0-color"
#endif

M5Canvas canvas(&M5.Display);

static void paintBootSplash() {
    canvas.fillSprite(WHITE);

    // Title
    canvas.setTextColor(BLACK);
    canvas.setFont(&fonts::FreeSansBold18pt7b);
    canvas.setTextDatum(middle_center);
    canvas.drawString("AI Desk Card", canvas.width() / 2, 60);

    canvas.setFont(&fonts::FreeSans12pt7b);
    canvas.setTextColor(BLUE);
    canvas.drawString("Paper Color port", canvas.width() / 2, 100);

    canvas.setFont(&fonts::FreeSans9pt7b);
    canvas.setTextColor(BLACK);
    canvas.drawString(CARD_VERSION, canvas.width() / 2, 130);

    // Red divider — proves color rendering reaches the panel
    canvas.fillRect(40, 160, canvas.width() - 80, 4, RED);

    // Setup hint
    canvas.setTextDatum(top_left);
    canvas.setFont(&fonts::FreeSansBold12pt7b);
    canvas.setTextColor(BLACK);
    canvas.drawString("First time setup", 40, 185);

    canvas.setFont(&fonts::FreeSans9pt7b);
    canvas.drawString("1. Install the Skill on your AI Agent:", 40, 220);

    canvas.drawRect(40, 250, canvas.width() - 80, 40, BLUE);
    canvas.drawString("github.com/op7418/ai-desk-card", 50, 263);

    canvas.drawString("2. Ask the agent to set up the card.", 40, 305);

    canvas.setTextDatum(bottom_center);
    canvas.setTextColor(GREEN);
    canvas.drawString("waiting for daemon...", canvas.width() / 2,
                      canvas.height() - 10);

    canvas.pushSprite(0, 0);
}

void setup() {
    auto cfg = M5.config();
    cfg.clear_display = false;
    M5.begin(cfg);

    Serial.begin(115200);
    delay(500);
    Serial.printf("[boot] ai-desk-card paper-color v%s\n", CARD_VERSION);
    Serial.printf("[boot] panel %d x %d\n",
                  (int)M5.Display.width(), (int)M5.Display.height());

    M5.Display.setEpdMode(epd_mode_t::epd_fastest);
    M5.Display.setRotation(0);

    canvas.createSprite(M5.Display.width(), M5.Display.height());
    Serial.printf("[boot] canvas created %d x %d\n",
                  (int)canvas.width(), (int)canvas.height());

    paintBootSplash();
    Serial.println("[boot] splash pushed — should be visible in ~15s");
}

void loop() {
    M5.update();

    if (M5.BtnA.wasClicked()) Serial.println("[btn] A clicked");
    if (M5.BtnB.wasClicked()) Serial.println("[btn] B clicked");
    if (M5.BtnC.wasClicked()) Serial.println("[btn] C clicked");

    delay(50);
}
