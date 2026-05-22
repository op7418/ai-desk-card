// ai-desk-card · M5Paper Color port — Phase 2.
//
// Phase 1 (verified): boot splash on Spectra 6 panel via M5Unified + Canvas.
// Phase 2 (this file): Wi-Fi + HTTP server + frame receive end-to-end.
//
// Same /frame endpoint shape as V1.1, but body format is RGB565 raw bytes
// (M5GFX quantizes to the 6-color palette on push). No BLE yet, no
// status_report backchannel yet, no touch (panel has none).

#include <Arduino.h>
#include <ArduinoJson.h>
#include <M5Unified.h>

#include "wifi_bridge.h"
#include "http_server.h"

#ifndef CARD_VERSION
#define CARD_VERSION "0.10.0-color"
#endif

M5Canvas canvas(&M5.Display);

// Minimal JSON cmd dispatcher over USB CDC Serial. Only wifi_set + ping
// for v1 — enough to provision creds without needing a touch screen or
// BLE pairing UX. User runs `screen /dev/cu.usbmodem* 115200` and pastes
// `{"cmd":"wifi_set","ssid":"...","password":"..."}` + Enter.
static String s_lineBuf;
static void processSerialLine(const String& line) {
    if (line.length() < 3) return;
    JsonDocument doc;
    if (deserializeJson(doc, line)) return;
    const char* cmd = doc["cmd"];
    if (!cmd) return;
    if (strcmp(cmd, "wifi_set") == 0) {
        const char* ssid = doc["ssid"] | "";
        const char* pwd  = doc["password"] | "";
        Serial.printf("[cmd] wifi_set ssid='%s' (pwd %u chars)\n",
                      ssid, (unsigned)strlen(pwd));
        wifiSetCredentials(ssid, pwd);
        Serial.println("{\"ack\":\"wifi_set\",\"ok\":true}");
    } else if (strcmp(cmd, "ping") == 0) {
        Serial.printf("{\"ack\":\"pong\",\"fw\":\"%s\",\"ip\":\"%s\","
                      "\"ssid\":\"%s\"}\n",
                      CARD_VERSION, wifiIPStr(), wifiSSID());
    } else {
        Serial.printf("{\"ack\":\"unknown\",\"cmd\":\"%s\"}\n", cmd);
    }
}
static void pollSerialCmds() {
    while (Serial.available()) {
        int b = Serial.read();
        if (b < 0) break;
        if (b == '\n' || b == '\r') {
            if (s_lineBuf.length() > 0) {
                processSerialLine(s_lineBuf);
                s_lineBuf = "";
            }
        } else {
            s_lineBuf += (char)b;
            if (s_lineBuf.length() > 512) s_lineBuf = "";   // safety
        }
    }
}

static void paintBootSplash() {
    canvas.fillSprite(WHITE);
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

    canvas.fillRect(40, 160, canvas.width() - 80, 4, RED);

    canvas.setTextDatum(top_left);
    canvas.setFont(&fonts::FreeSansBold12pt7b);
    canvas.drawString("Connect Wi-Fi", 40, 185);

    canvas.setFont(&fonts::FreeSans9pt7b);
    canvas.drawString("POST /provision-wifi", 40, 220);
    canvas.drawString("  to daemon at this device IP", 40, 240);

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
    Serial.printf("[boot] panel %dx%d\n",
                  (int)M5.Display.width(), (int)M5.Display.height());

    M5.Display.setEpdMode(epd_mode_t::epd_fastest);
    M5.Display.setRotation(1);   // panel is 400×600 native portrait; 1 = 600×400 landscape
    canvas.createSprite(M5.Display.width(), M5.Display.height());
    Serial.printf("[boot] panel after rotation: %dx%d\n",
                  (int)M5.Display.width(), (int)M5.Display.height());

    paintBootSplash();
    Serial.println("[boot] splash pushed");

    wifiInit();
}

void loop() {
    M5.update();
    pollSerialCmds();
    wifiPoll();

    // Start HTTP server once Wi-Fi is up (and re-start if it dropped).
    static bool s_http_up = false;
    bool wifi_up = wifiConnected();
    if (wifi_up && !httpServerRunning()) {
        httpServerStart();
        s_http_up = true;
    } else if (!wifi_up && httpServerRunning()) {
        httpServerStop();
        s_http_up = false;
    }
    httpServerPoll();

    // Button stubs — log only for now. Phase 4 will wire to
    // settings / refresh / sleep daemon endpoints.
    if (M5.BtnA.wasClicked()) Serial.println("[btn] A clicked");
    if (M5.BtnB.wasClicked()) Serial.println("[btn] B clicked");
    if (M5.BtnC.wasClicked()) Serial.println("[btn] C clicked");

    delay(10);
}
