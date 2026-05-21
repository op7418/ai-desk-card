// claude-card firmware entry point.
//
// Boot → load CJK font → enter Frame_WidgetDashboard (always-on副屏).
// Touch the top-right corner ⚙ to open settings. No dashboard mode, no
// approval cards, no buddy face. claude-card is display-only.

#include <Arduino.h>
#include <M5EPD.h>
#include <LittleFS.h>
#include <ArduinoJson.h>
#include <rom/rtc.h>
#include <esp_sleep.h>

#include "ble_bridge.h"
#include "widgets.h"
#include "frame_receiver.h"

#ifndef CARD_VERSION
#define CARD_VERSION "0.5-dev"
#endif

// ----------------------------------------------------------------------------
// Serial / BLE protocol dispatch
// ----------------------------------------------------------------------------

static char btName[16] = "Card";

static void startBt() {
    uint8_t mac[6] = {0};
    esp_read_mac(mac, ESP_MAC_BT);
    snprintf(btName, sizeof(btName), "Card-%02X%02X", mac[4], mac[5]);
    bleInit(btName);
}

// JSON command dispatch — claude-card only cares about widget_set + time + owner.
// Everything else from the daemon's heartbeat is ignored (we don't have a
// dashboard to update).
static bool dispatchCmd(JsonDocument& doc) {
    // Diagnostic: log every command we see (helps verify the daemon's
    // chunks actually reach + parse on device).
    const char* dbg_cmd = doc["cmd"];
    if (dbg_cmd) {
        if (strcmp(dbg_cmd, "frame_chunk") != 0) {   // chunks are noisy, skip
            Serial.printf("[rx] cmd=%s\n", dbg_cmd);
        }
    }
    // v0.6 server-side rendering path — pixels arrive in chunks.
    if (frameHandleCommand(doc)) return true;
    // v0.5 widget_set fallback (kept so daemons that still send widget JSON
    // don't crash; firmware just updates its cache, no rendering happens
    // since we deleted the painters).
    if (widgetsHandleCommand(doc)) return true;

    const char* cmd = doc["cmd"];
    if (cmd && strcmp(cmd, "sleep_now") == 0) {
        // The frame_chunk preceding this command has already painted the
        // panel (e.g., the name card). Now enter ESP32 deep sleep — but
        // CAREFULLY: GC16 full refresh takes ~1 s of particle transit to
        // settle into the final 16 grayscale levels. Cutting power
        // mid-transit leaves particles in intermediate / inverted state
        // (symptoms: black bg + white text, ghosting, blurry). Earlier
        // versions delayed only 200 ms here — too short — and the name
        // card came out as garbled inverse.
        uint32_t wake_sec = doc["wake_after_sec"] | 0;
        Serial.printf("[sleep_now] settling panel before deep sleep "
                      "(wake_after_sec=%u)\n", (unsigned)wake_sec);
        Serial.flush();

        // Re-trigger UpdateFull explicitly to make sure the LATEST
        // framebuffer is what's on screen (defensive — frame_end already
        // did one, but a second call is idempotent and the wait gives us
        // a known starting point).
        M5.EPD.UpdateFull(UPDATE_MODE_GC16);
        delay(2500);   // GC16 settling window

        // Park the panel via the driver's Sleep cmd so the driver IC
        // enters its own low-power state cleanly (vs. just yanking VCC).
        M5.EPD.Sleep();
        delay(300);

        if (wake_sec > 0) {
            esp_sleep_enable_timer_wakeup((uint64_t)wake_sec * 1000000ULL);
        }
        Serial.println("[sleep_now] entering ESP32 deep sleep");
        Serial.flush();
        delay(50);
        esp_deep_sleep_start();
        return true;   // unreachable
    }

    if (cmd) {
        if (strcmp(cmd, "owner") == 0) {
            // Ack so daemon's pair-status works. Owner name we ignore.
            const char* response = "{\"ack\":\"owner\",\"ok\":true}\n";
            Serial.print(response);
            bleWrite((const uint8_t*)response, strlen(response));
            return true;
        }
        if (strcmp(cmd, "unpair") == 0) {
            bleClearBonds();
            const char* response = "{\"ack\":\"unpair\",\"ok\":true}\n";
            Serial.print(response);
            bleWrite((const uint8_t*)response, strlen(response));
            return true;
        }
    }

    // Time sync (top-level "time": [epoch, tz_offset_sec]).
    JsonArray t = doc["time"];
    if (!t.isNull() && t.size() == 2) {
        time_t local = (time_t)t[0].as<uint32_t>() + (int32_t)t[1];
        struct tm lt; gmtime_r(&local, &lt);
        rtc_time_t tm;
        tm.hour = (int8_t)lt.tm_hour; tm.min = (int8_t)lt.tm_min; tm.sec = (int8_t)lt.tm_sec;
        rtc_date_t dt;
        dt.week = (int8_t)lt.tm_wday; dt.mon = (int8_t)(lt.tm_mon + 1);
        dt.day = (int8_t)lt.tm_mday;  dt.year = (int16_t)(lt.tm_year + 1900);
        M5.RTC.setTime(&tm);
        M5.RTC.setDate(&dt);
        return true;
    }
    return false;
}

// Line buffers for USB + BLE. Size 4 KB so the largest widget_set frame
// (6 widgets, ~1.5 KB JSON) has comfortable headroom.
template <size_t N>
struct LineBuf {
    char buf[N];
    uint16_t len = 0;
    void feed(Stream& s) {
        while (s.available()) {
            char c = s.read();
            if (c == '\n' || c == '\r') {
                if (len > 0) {
                    buf[len] = 0;
                    if (buf[0] == '{') {
                        JsonDocument doc;
                        if (deserializeJson(doc, buf) == DeserializationError::Ok) {
                            dispatchCmd(doc);
                        }
                    }
                    len = 0;
                }
            } else if (len < N - 1) {
                buf[len++] = c;
            }
        }
    }
};

// 8 KB buffer per stream — must be larger than the daemon's chunk JSON
// line (a 2 KB raw chunk encodes to ~2.7 KB base64 + JSON wrapper). 4 KB
// was too tight and silently truncated chunks → frame assembly failed
// without any visible error.
static LineBuf<8192> g_usbLine;
static LineBuf<8192> g_btLine;

extern "C" void cardPollSerial() {
    g_usbLine.feed(Serial);
    while (bleAvailable()) {
        int c = bleRead();
        if (c < 0) break;
        if (c == '\n' || c == '\r') {
            if (g_btLine.len > 0) {
                g_btLine.buf[g_btLine.len] = 0;
                if (g_btLine.buf[0] == '{') {
                    JsonDocument doc;
                    if (deserializeJson(doc, g_btLine.buf) == DeserializationError::Ok) {
                        dispatchCmd(doc);
                    }
                }
                g_btLine.len = 0;
            }
        } else if (g_btLine.len < sizeof(g_btLine.buf) - 1) {
            g_btLine.buf[g_btLine.len++] = (char)c;
        }
    }
}

// ----------------------------------------------------------------------------
// Setup / loop
// ----------------------------------------------------------------------------

// v0.6: server-side rendering. Daemon ships pre-rendered 4bpp pixel frames
// over USB serial at 921600 baud (~3.7 s per full frame). Device just
// receives, assembles, pushes to e-ink panel. No on-device renderer.
//
// On boot we paint a tiny "waiting for daemon" splash so the user has
// something to look at until the first real frame arrives.

// Stay at the default 115200 for v0.6 first cut. Bumping to 921600 caused
// some kind of TX baud mismatch (device received commands fine at 921600,
// but its Serial output was still at the wrong rate from the daemon's
// perspective — daemon read garbled bytes). Worth ~30s/frame at 115200,
// will revisit baud after confirming the rest of the architecture works.
static constexpr uint32_t kSerialBaud = 115200;

static void paintBootSplash() {
    M5EPD_Canvas c(&M5.EPD);
    c.createCanvas(540, 960);
    c.fillCanvas(0);   // white
    c.setTextColor(15);
    c.setTextDatum(CC_DATUM);
    c.setTextSize(28);
    c.drawString("claude-card", 270, 440);
    c.setTextSize(20);
    c.drawString("waiting for daemon...", 270, 490);
    c.setTextSize(16);
    c.drawString(CARD_VERSION, 270, 940);
    c.pushCanvas(0, 0, UPDATE_MODE_GC16);
    c.deleteCanvas();
}

void setup() {
    M5.begin(true, true, true, true, true);

    // No baud switch — stay at M5.begin's default 115200.
    delay(50);

    Serial.printf("[boot] claude-card v%s @ %lu baud  reset cpu0=%d cpu1=%d  heap=%u psram=%u\n",
                  CARD_VERSION, (unsigned long)kSerialBaud,
                  (int)rtc_get_reset_reason(0), (int)rtc_get_reset_reason(1),
                  ESP.getFreeHeap(), ESP.getPsramSize());

    M5.EPD.SetRotation(90);
    M5.TP.SetRotation(90);
    M5.EPD.Clear(true);

    if (!frameReceiverInit()) {
        Serial.println("[boot] frameReceiverInit FAILED — staying in waiting state");
    }

    paintBootSplash();

    startBt();
    Serial.printf("[ble] advertising as '%s'\n", btName);
    Serial.println("[boot] ready — awaiting first frame from daemon");
}

void loop() {
    cardPollSerial();   // drains serial / BLE, dispatches commands
    delay(2);            // tiny yield so WDT + BLE stack stay happy
}
