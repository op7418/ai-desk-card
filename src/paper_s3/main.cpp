#include <Arduino.h>
#include <ArduinoJson.h>
#include <esp_mac.h>
#include <string.h>

#include "paper_s3_frame_receiver.h"
#include "paper_s3_hw.h"

#ifndef CARD_VERSION
#define CARD_VERSION "0.10.1-paper-s3"
#endif

#define CARD_PROTO 1

#ifndef PAPER_S3_TOUCH_DEBUG
#define PAPER_S3_TOUCH_DEBUG 1
#endif

namespace {

char g_macStr[18] = "00:00:00:00:00:00";
char g_lineBuf[8192];
size_t g_lineLen = 0;

struct TouchChip {
    int16_t x = 0;
    int16_t y = 0;
    int16_t w = 0;
    int16_t h = 0;
    char id[16] = "";
};

TouchChip g_chips[8];
int g_chipCount = 0;

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

const char* touchEventName(paper_s3::TouchState::Event event) {
    switch (event) {
        case paper_s3::TouchState::Event::Down: return "down";
        case paper_s3::TouchState::Event::Move: return "move";
        case paper_s3::TouchState::Event::Up: return "up";
        default: return "none";
    }
}

int chipHitIndex(int32_t x, int32_t y) {
    for (int i = 0; i < g_chipCount; ++i) {
        const TouchChip& c = g_chips[i];
        if (x >= c.x && x < c.x + c.w &&
            y >= c.y && y < c.y + c.h) {
            return i;
        }
    }
    return -1;
}

void handleSetChips(JsonDocument& doc) {
    JsonArray arr = doc["rects"].as<JsonArray>();
    int n = 0;
    for (JsonObject r : arr) {
        if (n >= (int)(sizeof(g_chips) / sizeof(g_chips[0]))) break;
        TouchChip& c = g_chips[n];
        c.x = (int16_t)(r["x"] | 0);
        c.y = (int16_t)(r["y"] | 0);
        c.w = (int16_t)(r["w"] | 0);
        c.h = (int16_t)(r["h"] | 0);
        const char* id = r["id"] | "";
        strncpy(c.id, id, sizeof(c.id) - 1);
        c.id[sizeof(c.id) - 1] = '\0';
        n++;
    }
    g_chipCount = n;
    Serial.printf("{\"ack\":\"set_chips\",\"n\":%d}\n", n);
#if PAPER_S3_TOUCH_DEBUG
    Serial.printf("[touch] hit zones updated count=%d\n", n);
    for (int i = 0; i < n; ++i) {
        const TouchChip& c = g_chips[i];
        Serial.printf("[touch] hit zone id=%s rect=(%d,%d,%d,%d)\n",
                      c.id, c.x, c.y, c.w, c.h);
    }
#endif
}

void logTouchInitStatus() {
    const bool ready = paper_s3::touchReady();
    Serial.printf("[touch] init %s enabled=%s map=%s logical=%dx%d panel=%ldx%ld\n",
                  ready ? "success" : "failure",
                  ready ? "true" : "false",
                  paper_s3::touchMapName(),
                  paper_s3::kLogicalFrameWidth,
                  paper_s3::kLogicalFrameHeight,
                  (long)paper_s3::displayWidth(),
                  (long)paper_s3::displayHeight());
    if (ready) {
        Serial.println("[touch] subsystem ready");
    }
}

void logTouchEvent(const paper_s3::TouchState& touch) {
#if PAPER_S3_TOUCH_DEBUG
    if (touch.event == paper_s3::TouchState::Event::None) return;
    Serial.printf("[touch] event=%s count=%u raw=(%ld,%ld) screen=(%ld,%ld) mapped=(%ld,%ld)\n",
                  touchEventName(touch.event),
                  (unsigned)touch.count,
                  (long)touch.rawX, (long)touch.rawY,
                  (long)touch.screenX, (long)touch.screenY,
                  (long)touch.x, (long)touch.y);
#else
    (void)touch;
#endif
}

void emitTouchEvent(int32_t x, int32_t y, uint32_t holdMs) {
    Serial.printf("{\"event\":\"touch\",\"x\":%ld,\"y\":%ld,\"hold_ms\":%lu}\n",
                  (long)x, (long)y, (unsigned long)holdMs);
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

    if (strcmp(cmd, "set_chips") == 0) {
        handleSetChips(doc);
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

void pollTouchAndEmit() {
    static bool s_tracking = false;
    static bool s_haveAcceptedClick = false;
    static uint32_t s_downMs = 0;
    static uint32_t s_lastAcceptedMs = 0;
    static int32_t s_lastX = 0;
    static int32_t s_lastY = 0;

    constexpr uint32_t kTapMinMs = 30;
    constexpr uint32_t kTapMaxMs = 2000;
    constexpr uint32_t kClickDebounceMs = 250;

    const paper_s3::TouchState touch = paper_s3::readTouch();
    logTouchEvent(touch);

    const uint32_t now = millis();
    if (touch.event == paper_s3::TouchState::Event::Down) {
        s_tracking = true;
        s_downMs = now;
        s_lastX = touch.x;
        s_lastY = touch.y;
        return;
    }

    if (touch.event == paper_s3::TouchState::Event::Move) {
        if (s_tracking) {
            s_lastX = touch.x;
            s_lastY = touch.y;
        }
        return;
    }

    if (touch.event != paper_s3::TouchState::Event::Up) {
        return;
    }

    if (!s_tracking) {
#if PAPER_S3_TOUCH_DEBUG
        Serial.println("[touch] click ignored reason=up-without-down");
#endif
        return;
    }

    s_tracking = false;
    s_lastX = touch.x;
    s_lastY = touch.y;
    const uint32_t holdMs = now - s_downMs;
    const int hit = chipHitIndex(s_lastX, s_lastY);
    const char* target = hit >= 0 ? g_chips[hit].id : "none";

#if PAPER_S3_TOUCH_DEBUG
    if (hit >= 0) {
        const TouchChip& c = g_chips[hit];
        Serial.printf("[touch] hit target id=%s rect=(%d,%d,%d,%d)\n",
                      target, c.x, c.y, c.w, c.h);
    } else {
        Serial.println("[touch] hit target id=none");
    }
#endif

    if (holdMs < kTapMinMs) {
#if PAPER_S3_TOUCH_DEBUG
        Serial.printf("[touch] click ignored reason=too-short hold_ms=%lu min_ms=%lu target=%s\n",
                      (unsigned long)holdMs, (unsigned long)kTapMinMs, target);
#endif
        return;
    }

    if (holdMs > kTapMaxMs) {
#if PAPER_S3_TOUCH_DEBUG
        Serial.printf("[touch] click ignored reason=too-long hold_ms=%lu max_ms=%lu target=%s\n",
                      (unsigned long)holdMs, (unsigned long)kTapMaxMs, target);
#endif
        return;
    }

    if (s_haveAcceptedClick && now - s_lastAcceptedMs < kClickDebounceMs) {
#if PAPER_S3_TOUCH_DEBUG
        Serial.printf("[touch] click ignored reason=debounce elapsed_ms=%lu min_ms=%lu target=%s\n",
                      (unsigned long)(now - s_lastAcceptedMs),
                      (unsigned long)kClickDebounceMs, target);
#endif
        return;
    }

    s_haveAcceptedClick = true;
    s_lastAcceptedMs = now;
#if PAPER_S3_TOUCH_DEBUG
    Serial.printf("[touch] click accepted target=%s x=%ld y=%ld hold_ms=%lu\n",
                  target, (long)s_lastX, (long)s_lastY,
                  (unsigned long)holdMs);
#endif
    emitTouchEvent(s_lastX, s_lastY, holdMs);
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
    logTouchInitStatus();
    paper_s3_frame::begin();
    cacheMacAddress();
    logBootSummary();

    paper_s3::paintTouchCalibrationScreen(CARD_VERSION);
    Serial.println("[display] PaperS3 touch calibration screen pushed");
    Serial.println("[boot] ready; send {\"cmd\":\"ping\"} or frame_begin/frame_chunk/frame_end");
    emitStatusReport();
}

void loop() {
    paper_s3::update();
    pollSerialCommands();
    pollTouchAndEmit();

    static uint32_t s_lastStatusMs = 0;
    const uint32_t now = millis();
    if (!paper_s3_frame::isReceiving() && now - s_lastStatusMs > 60000) {
        s_lastStatusMs = now;
        emitStatusReport();
    }

    delay(20);
}
