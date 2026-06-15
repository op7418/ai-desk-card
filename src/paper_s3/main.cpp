#include <Arduino.h>
#include <ArduinoJson.h>
#include <esp_mac.h>

#include "paper_s3_frame_receiver.h"
#include "paper_s3_hw.h"

#ifndef CARD_VERSION
#define CARD_VERSION "0.10.1-paper-s3"
#endif

#define CARD_PROTO 1

namespace {

char g_macStr[18] = "00:00:00:00:00:00";
char g_lineBuf[8192];
size_t g_lineLen = 0;

void cacheMacAddress() {
    uint8_t mac[6] = {0};
    esp_read_mac(mac, ESP_MAC_WIFI_STA);
    snprintf(g_macStr, sizeof(g_macStr), "%02X:%02X:%02X:%02X:%02X:%02X",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
}

void emitStatusReport() {
    const paper_s3::PowerState power = paper_s3::readPower();
    char line[512];
    const int n = snprintf(
        line, sizeof(line),
        "{\"ack\":\"status\",\"device\":\"%s\",\"fw\":\"%s\",\"proto\":%d,"
        "\"mac\":\"%s\",\"uptime_s\":%lu,\"battery_pct\":%ld,"
        "\"battery_mv\":%d,\"on_usb\":%s,\"charging\":%s,"
        "\"wifi_connected\":false,\"wifi_ssid\":\"\",\"wifi_ip\":\"%s\","
        "\"wifi_rssi\":-127,\"frame_state\":\"%s\"}\n",
        paper_s3::kDeviceName, CARD_VERSION, CARD_PROTO, g_macStr,
        (unsigned long)(millis() / 1000), (long)power.batteryPercent,
        (int)power.batteryMillivolts, power.usbPresent ? "true" : "false",
        power.charging ? "true" : "false", paper_s3::kIpPlaceholder,
        paper_s3_frame::stateName());
    if (n > 0) Serial.print(line);
}

void processJsonLine(const char* line) {
    JsonDocument doc;
    const DeserializationError err = deserializeJson(doc, line);
    if (err) {
        Serial.printf("[rx] invalid json: %s\n", err.c_str());
        return;
    }

    const char* cmd = doc["cmd"];
    if (!cmd) {
        Serial.println("[rx] json without cmd ignored");
        return;
    }

    if (strcmp(cmd, "frame_chunk") != 0) {
        Serial.printf("[rx] cmd=%s\n", cmd);
    }
    if (paper_s3_frame::handleCommand(doc)) {
        return;
    }

    if (strcmp(cmd, "ping") == 0) {
        emitStatusReport();
        return;
    }

    if (strcmp(cmd, "restart") == 0) {
        Serial.println("{\"ack\":\"restart\",\"ok\":true}");
        Serial.flush();
        delay(200);
        ESP.restart();
        return;
    }

    Serial.printf("{\"ack\":\"ignored\",\"cmd\":\"%s\",\"phase\":\"paper-s3-bring-up\"}\n", cmd);
}

void pollSerialCommands() {
    while (Serial.available()) {
        if (paper_s3_frame::wantsRawBytes()) {
            uint8_t rawBuf[256];
            const int available = Serial.available();
            const size_t toRead = available < (int)sizeof(rawBuf)
                ? (size_t)available
                : sizeof(rawBuf);
            const int n = Serial.read(rawBuf, toRead);
            if (n > 0) {
                paper_s3_frame::appendRawBytes(rawBuf, (size_t)n);
            }
            continue;
        }

        const int b = Serial.read();
        if (b < 0) break;
        if (b == '\n' || b == '\r') {
            if (g_lineLen > 0) {
                g_lineBuf[g_lineLen] = '\0';
                processJsonLine(g_lineBuf);
                g_lineLen = 0;
            }
        } else if (g_lineLen < sizeof(g_lineBuf) - 1) {
            g_lineBuf[g_lineLen++] = (char)b;
        } else {
            g_lineLen = 0;
            Serial.printf("[rx] line too long; dropped limit=%u\n",
                          (unsigned)sizeof(g_lineBuf));
        }
    }
}

void logBootSummary() {
    const paper_s3::PowerState power = paper_s3::readPower();

    Serial.println();
    Serial.println("[boot] ai-desk-card PaperS3 bring-up");
    Serial.printf("[boot] fw=%s proto=%d device=%s\n",
                  CARD_VERSION, CARD_PROTO, paper_s3::kDeviceName);
    Serial.printf("[boot] mac=%s\n", g_macStr);
    Serial.printf("[boot] panel=%ldx%ld\n",
                  (long)paper_s3::displayWidth(), (long)paper_s3::displayHeight());
    Serial.printf("[boot] heap=%u psram=%u\n",
                  (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getPsramSize());
    Serial.printf("[frame] receiver=%s logical=%dx%d bytes=%u\n",
                  paper_s3_frame::stateName(),
                  paper_s3_frame::kFrameWidth,
                  paper_s3_frame::kFrameHeight,
                  (unsigned)paper_s3_frame::kFrameBytes4bpp);
    Serial.printf("[power] usb=%s charging=%s battery=%ld%% battery_mv=%d\n",
                  power.usbPresent ? "yes" : "no",
                  power.charging ? "yes" : "no",
                  (long)power.batteryPercent, (int)power.batteryMillivolts);
    Serial.printf("[net] wifi disabled in phase 1; ip placeholder=%s\n",
                  paper_s3::kIpPlaceholder);
    Serial.println("[feature] BLE disabled in phase 1");
    Serial.println("[feature] deep sleep disabled in phase 1");
}

void logTouchTransitions() {
    static bool s_wasPressed = false;
    const paper_s3::TouchState touch = paper_s3::readTouch();
    if (touch.pressed && !s_wasPressed) {
        Serial.printf("[touch] down x=%ld y=%ld\n", (long)touch.x, (long)touch.y);
    } else if (!touch.pressed && s_wasPressed) {
        Serial.println("[touch] up");
    }
    s_wasPressed = touch.pressed;
}

}  // namespace

void setup() {
    Serial.setRxBufferSize(16384);
    Serial.begin(115200);
    delay(1500);
    Serial.println();
    Serial.println("[probe] setup entered before M5.begin");
    Serial.printf("[probe] heap=%u psram=%u\n",
                  (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getPsramSize());
    Serial.flush();

    paper_s3::begin();
    Serial.println("[probe] M5.begin returned");
    Serial.flush();
    paper_s3_frame::begin();
    cacheMacAddress();
    logBootSummary();

    paper_s3::paintTestScreen(CARD_VERSION, paper_s3::kIpPlaceholder);
    Serial.println("[display] PaperS3 test screen pushed");
    Serial.println("[boot] ready; send {\"cmd\":\"ping\"} or frame_begin/frame_chunk/frame_end");
    emitStatusReport();
}

void loop() {
    paper_s3::update();
    pollSerialCommands();
    logTouchTransitions();

    static uint32_t s_lastStatusMs = 0;
    const uint32_t now = millis();
    if (!paper_s3_frame::isReceiving() && now - s_lastStatusMs > 60000) {
        s_lastStatusMs = now;
        emitStatusReport();
    }

    delay(20);
}
