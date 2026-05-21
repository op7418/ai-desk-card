// ai-desk-card firmware entry point.
//
// Boot → load CJK font → enter Frame_WidgetDashboard (always-on副屏).
// Touch the top-right corner ⚙ to open settings. No dashboard mode, no
// approval cards, no buddy face. ai-desk-card is display-only.

#include <Arduino.h>
#include <M5EPD.h>
#include <LittleFS.h>
#include <ArduinoJson.h>
#include <rom/rtc.h>
#include <esp_sleep.h>
#include <ESPmDNS.h>

#include "ble_bridge.h"
#include "widgets.h"
#include "frame_receiver.h"
#include "wifi_bridge.h"
#include "http_server.h"

#ifndef CARD_VERSION
#define CARD_VERSION "0.6.4"
#endif

// Bumped each time the daemon-side protocol changes. Daemon's
// /firmware-probe compares this against its own to decide compatibility.
#define CARD_PROTO 1

// ----------------------------------------------------------------------------
// Serial / BLE protocol dispatch
// ----------------------------------------------------------------------------

static char btName[16] = "Card";
static char g_macStr[18] = "";          // cached "AA:BB:CC:DD:EE:FF"

static void startBt() {
    uint8_t mac[6] = {0};
    esp_read_mac(mac, ESP_MAC_BT);
    snprintf(btName, sizeof(btName), "Card-%02X%02X", mac[4], mac[5]);
    snprintf(g_macStr, sizeof(g_macStr), "%02X:%02X:%02X:%02X:%02X:%02X",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    bleInit(btName);
}

// Rough battery percentage from M5.getBatteryVoltage() (mV). The M5EPD
// pack is a 1S lipo: ~4200 mV full, ~3300 mV empty. We clamp to [0,100].
static int batteryPct(uint32_t* out_mv = nullptr) {
    uint32_t mv = M5.getBatteryVoltage();
    if (out_mv) *out_mv = mv;
    int pct = (int)((mv - 3300) * 100 / (4200 - 3300));
    if (pct < 0) pct = 0;
    if (pct > 100) pct = 100;
    return pct;
}

// Power mode (v0.8): is the device on USB-C power or running off battery?
// M5EPD library doesn't expose isCharging() on this version; we infer
// from battery voltage. A 1S lipo can never read above ~4200 mV while
// discharging, so >4150 mV with stable trend means the charger is
// holding the rail up. Imprecise but enough to pick architecture A
// (Wi-Fi always on) vs C (battery, Wi-Fi on-demand).
static bool g_was_charging = false;
static bool isOnUSBPower() {
    return M5.getBatteryVoltage() > 4150;
}

// mDNS — call when Wi-Fi just connected, tear down when it drops. The
// service name lets the daemon discover the device with `_ai-desk-card._tcp`.
static bool g_mdns_up = false;
static void startMDNSIfNeeded() {
    if (g_mdns_up || !wifiConnected()) return;
    uint8_t mac[6] = {0};
    esp_read_mac(mac, ESP_MAC_BT);
    char host[16];
    snprintf(host, sizeof(host), "card-%02x%02x", mac[4], mac[5]);
    if (!MDNS.begin(host)) {
        Serial.println("[mdns] begin FAILED");
        return;
    }
    MDNS.addService("ai-desk-card", "tcp", httpServerPort());
    MDNS.addServiceTxt("ai-desk-card", "tcp", "fw", CARD_VERSION);
    MDNS.addServiceTxt("ai-desk-card", "tcp", "proto", "1");
    g_mdns_up = true;
    Serial.printf("[mdns] advertising as %s.local — _ai-desk-card._tcp:%u\n",
                  host, httpServerPort());
}
static void stopMDNS() {
    if (!g_mdns_up) return;
    MDNS.end();
    g_mdns_up = false;
    Serial.println("[mdns] torn down");
}

// Emit a status_report JSON line. Daemon's RX parser picks it up and
// stores fields into DEVICE_TELEMETRY (battery for the bottom bar; fw /
// mac / uptime_s for the settings page; wifi info for arch C burst path).
// Safe to call on any cadence.
static void emitStatusReport() {
    uint32_t mv = 0;
    int pct = batteryPct(&mv);
    bool wifi = wifiConnected();
    char buf[384];
    int n = snprintf(buf, sizeof(buf),
        "{\"ack\":\"status\",\"fw\":\"%s\",\"proto\":%d,\"mac\":\"%s\","
        "\"uptime_s\":%lu,\"battery_pct\":%d,\"battery_mv\":%u,"
        "\"on_usb\":%s,\"wifi_connected\":%s,"
        "\"wifi_ssid\":\"%s\",\"wifi_ip\":\"%s\",\"wifi_rssi\":%d}\n",
        CARD_VERSION, CARD_PROTO, g_macStr,
        (unsigned long)(millis() / 1000), pct, (unsigned)mv,
        isOnUSBPower() ? "true" : "false",
        wifi ? "true" : "false",
        wifiSSID(), wifiIPStr(), wifiRSSI());
    if (n > 0) {
        Serial.print(buf);
        bleWrite((const uint8_t*)buf, (size_t)n);
    }
}

// JSON command dispatch — ai-desk-card only cares about widget_set + time + owner.
// Everything else from the daemon's heartbeat is ignored (we don't have a
// dashboard to update).
bool dispatchCmd(JsonDocument& doc) {
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
        if (strcmp(cmd, "ping") == 0) {
            // Synchronous health probe — daemon's /firmware-probe uses
            // this. Reply with the same telemetry as the periodic
            // status_report so a single ping gives the daemon everything
            // it needs for the settings page.
            emitStatusReport();
            return true;
        }
        if (strcmp(cmd, "restart") == 0) {
            // Soft restart via settings page → /restart endpoint. The 200 ms
            // delay lets the daemon log the ack and the serial buffer flush
            // before we ESP.restart().
            const char* response = "{\"ack\":\"restart\",\"ok\":true}\n";
            Serial.print(response);
            bleWrite((const uint8_t*)response, strlen(response));
            Serial.flush();
            delay(200);
            ESP.restart();
            return true;   // unreachable
        }
        if (strcmp(cmd, "wifi_set") == 0) {
            // v0.8: provision Wi-Fi over BLE (or serial). Daemon's
            // /provision-wifi forwards this. NVS-write is non-blocking;
            // reconnect happens in wifiPoll().
            const char* ssid = doc["ssid"] | "";
            const char* pass = doc["password"] | "";
            wifiSetCredentials(ssid, pass);
            char resp[64];
            snprintf(resp, sizeof(resp),
                     "{\"ack\":\"wifi_set\",\"ok\":true,\"ssid\":\"%s\"}\n",
                     ssid);
            Serial.print(resp);
            bleWrite((const uint8_t*)resp, strlen(resp));
            return true;
        }
        if (strcmp(cmd, "wifi_wake_now") == 0) {
            // Architecture C: battery mode keeps Wi-Fi off until the daemon
            // asks it to come up. Ack now; the ack:status that fires once
            // Wi-Fi connects carries the IP.
            wifiWakeNow();
            const char* response = "{\"ack\":\"wifi_wake_now\",\"ok\":true}\n";
            Serial.print(response);
            bleWrite((const uint8_t*)response, strlen(response));
            return true;
        }
        if (strcmp(cmd, "wifi_power_down") == 0) {
            // Architecture C: daemon finished pushing; let the radio sleep.
            wifiPowerDown();
            const char* response = "{\"ack\":\"wifi_power_down\",\"ok\":true}\n";
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

// Pairing overlay: when blePasskey() transitions to nonzero (peer requesting
// MITM SC pairing), we paint a big PIN over the current frame. After the
// pair completes, the next daemon connection's handshake re-pushes the
// widget frame and the panel returns to normal.
static void paintPasskeyOverlay(uint32_t pk) {
    M5EPD_Canvas c(&M5.EPD);
    c.createCanvas(540, 960);
    c.fillCanvas(0);   // white
    c.setTextColor(15);
    c.setTextDatum(CC_DATUM);

    c.setTextSize(36);
    c.drawString("BLE PAIRING", 270, 280);

    char pin[8];
    snprintf(pin, sizeof(pin), "%06lu", (unsigned long)pk);
    c.setTextSize(96);
    c.drawString(pin, 270, 450);

    c.setTextSize(24);
    c.drawString("enter this PIN on your Mac", 270, 620);
    c.setTextSize(20);
    c.drawString("(System Settings -> Bluetooth)", 270, 680);

    c.pushCanvas(0, 0, UPDATE_MODE_GC16);
    c.deleteCanvas();
    Serial.printf("[ble] passkey UI displayed: %06lu\n", (unsigned long)pk);
}

static void paintBootSplash() {
    M5EPD_Canvas c(&M5.EPD);
    c.createCanvas(540, 960);
    c.fillCanvas(0);   // white
    c.setTextColor(15);
    c.setTextDatum(CC_DATUM);
    c.setTextSize(28);
    c.drawString("ai-desk-card", 270, 440);
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

    Serial.printf("[boot] ai-desk-card v%s @ %lu baud  reset cpu0=%d cpu1=%d  heap=%u psram=%u\n",
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

    // v0.8: Wi-Fi. NVS-driven; if no credentials, stays off until cmd:wifi_set.
    // Architecture A (on USB power): try to connect at boot so HTTP push
    // works immediately. Architecture C (battery): stay off until the
    // daemon asks via cmd:wifi_wake_now.
    g_was_charging = isOnUSBPower();
    Serial.printf("[power] on_usb=%s\n", g_was_charging ? "yes" : "no");
    // v0.8: always load credentials from NVS so cmd:wifi_wake_now works
    // on battery boot. Only auto-connect when on USB (architecture A).
    wifiInit();
    if (g_was_charging) {
        wifiAutoConnect();
    } else {
        Serial.println("[wifi] battery mode — radio off until wake_now");
    }

    Serial.println("[boot] ready — awaiting first frame from daemon");

    // Initial status report so the daemon's DEVICE_TELEMETRY has data
    // immediately (settings page / battery in bar work from boot).
    emitStatusReport();
}

void loop() {
    cardPollSerial();    // drains serial / BLE, dispatches commands
    wifiPoll();          // drives reconnect retries
    httpServerPoll();    // accepts inbound HTTP connections (one at a time)

    // v0.8: power-mode tracking. If user plugs in USB while we were on
    // battery (radio off), bring Wi-Fi back up automatically. If they
    // unplug, leave the connection alone — wifiPoll handles drops.
    bool charging = isOnUSBPower();
    if (charging != g_was_charging) {
        g_was_charging = charging;
        Serial.printf("[power] state change: on_usb=%s\n", charging ? "yes" : "no");
        if (charging && !wifiConnected()) wifiWakeNow();
    }

    // v0.8: bring mDNS up/down to follow the Wi-Fi link state. Also fire
    // an extra status_report on Wi-Fi up so daemon learns the IP fast
    // (~5 s after wifi_wake_now, vs waiting 60 s for the next periodic).
    static bool s_wifi_was_up = false;
    bool wifi_up = wifiConnected();
    if (wifi_up) {
        if (!httpServerRunning()) httpServerStart();
        startMDNSIfNeeded();
        if (!s_wifi_was_up) {
            Serial.println("[wifi] link just came up — emitting status_report");
            emitStatusReport();
        }
    } else {
        if (httpServerRunning()) httpServerStop();
        if (g_mdns_up) stopMDNS();
    }
    s_wifi_was_up = wifi_up;

    // Periodic status_report every 60 s. Cheap (one JSON line), keeps the
    // daemon's DEVICE_TELEMETRY warm so the bottom-bar battery indicator
    // doesn't go stale.
    static uint32_t s_lastStatus = 0;
    uint32_t now = millis();
    if (now - s_lastStatus > 60000) {
        s_lastStatus = now;
        emitStatusReport();
    }

    // BLE pairing UI: when the BT stack emits a passkey (peer initiated
    // MITM Secure Connections pair), paint it big on the e-ink so the
    // user can type it into macOS' pair dialog. When it clears (auth
    // complete or aborted), the daemon's next handshake will re-push
    // the widget frame so the panel returns to normal.
    static uint32_t s_lastPk = 0;
    uint32_t pk = blePasskey();
    if (pk != s_lastPk) {
        s_lastPk = pk;
        if (pk != 0) {
            paintPasskeyOverlay(pk);
        } else {
            // Notify daemon so it triggers an immediate re-push instead
            // of waiting for the 5-minute keepalive.
            const char* msg = "{\"ack\":\"paired\",\"ok\":true}\n";
            Serial.print(msg);
            bleWrite((const uint8_t*)msg, strlen(msg));
        }
    }

    delay(2);             // tiny yield so WDT + BLE stack stay happy
}
