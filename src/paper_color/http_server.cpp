#include "http_server.h"
#include "wifi_bridge.h"
#include "sht40.h"
#include "feedback_led.h"
#include "audio.h"

#include <WiFi.h>
#include <WiFiClient.h>
#include <WiFiServer.h>
#include <M5Unified.h>
#include <ArduinoJson.h>
#include <esp_mac.h>
#include <esp_sleep.h>

// Forward — defined in frame_buffer.cpp. Receives a complete RGB565 frame
// (w*h*2 bytes) and renders to the M5Canvas.
extern bool frameAcceptRGB565(int x, int y, int w, int h,
                              const uint8_t* data, size_t len);

namespace {

constexpr uint16_t kPort       = 9880;
constexpr uint16_t kDaemonPort = 9877;
WiFiServer g_server(kPort);
bool       g_started   = false;
char       g_daemonIp[16] = {0};

String readLine(WiFiClient& c, uint32_t timeoutMs = 2000) {
    String s; s.reserve(256);
    uint32_t deadline = millis() + timeoutMs;
    while (millis() < deadline) {
        if (!c.connected()) break;
        int b = c.read();
        if (b < 0) { delay(1); continue; }
        if (b == '\n') {
            if (s.length() && s.charAt(s.length() - 1) == '\r')
                s.remove(s.length() - 1);
            return s;
        }
        s += (char)b;
        if (s.length() > 2048) break;
    }
    return s;
}

void writeStatus(WiFiClient& c, int code, const char* reason,
                 const char* ct, const String& body) {
    c.printf("HTTP/1.1 %d %s\r\n", code, reason);
    c.printf("Content-Type: %s\r\n", ct);
    c.printf("Content-Length: %u\r\n", (unsigned)body.length());
    c.print("Connection: close\r\n\r\n");
    c.print(body);
}

void writeError(WiFiClient& c, int code, const char* reason, const char* msg) {
    String b = String("{\"error\":\"") + (msg ? msg : reason) + "\"}";
    writeStatus(c, code, reason, "application/json", b);
}

// ---- /status ------------------------------------------------------------

void handleStatus(WiFiClient& c) {
    JsonDocument doc;
    doc["device"]       = "M5PaperColor";
    doc["firmware"]     = CARD_VERSION;
    doc["panel_w"]      = (int)M5.Display.width();
    doc["panel_h"]      = (int)M5.Display.height();
    doc["color_mode"]   = "spectra6";
    doc["battery_pct"]  = (int)M5.Power.getBatteryLevel();
    doc["uptime_s"]     = (uint32_t)(millis() / 1000);
    JsonObject wifi = doc["wifi"].to<JsonObject>();
    wifi["ssid"]     = wifiSSID();
    wifi["ip"]       = wifiIPStr();
    wifi["rssi"]     = wifiRSSI();

    // v0.10: SHT40 ambient readings (Paper Color exclusive — V1.1
    // has no temperature sensor on board)
    if (sht40LastReadMs() > 0) {
        JsonObject amb = doc["ambient"].to<JsonObject>();
        amb["temp_c"]   = sht40LastTempC();
        amb["humid_pct"] = sht40LastHumidPct();
        amb["age_s"]    = (uint32_t)((millis() - sht40LastReadMs()) / 1000);
    }
    String body; serializeJson(doc, body);
    writeStatus(c, 200, "OK", "application/json", body);
}

// ---- /provision-wifi ---------------------------------------------------

void handleProvisionWifi(WiFiClient& c, size_t contentLen) {
    if (contentLen == 0 || contentLen > 256) {
        writeError(c, 400, "Bad Request", "bad content length"); return;
    }
    String body; body.reserve(contentLen + 1);
    size_t got = 0;
    uint32_t deadline = millis() + 2000;
    while (got < contentLen && millis() < deadline) {
        int b = c.read();
        if (b < 0) { delay(1); continue; }
        body += (char)b; got++;
    }
    JsonDocument doc;
    if (deserializeJson(doc, body)) {
        writeError(c, 400, "Bad Request", "invalid JSON"); return;
    }
    const char* ssid = doc["ssid"] | "";
    const char* pwd  = doc["password"] | "";
    wifiSetCredentials(ssid, pwd);
    writeStatus(c, 200, "OK", "application/json",
                String("{\"ok\":true,\"ssid\":\"") + ssid + "\"}");
}

// ---- /frame -------------------------------------------------------------

void handleFrame(WiFiClient& c, const String& query, size_t contentLen) {
    // Region from query string. Default = full panel.
    int x = 0, y = 0, w = M5.Display.width(), h = M5.Display.height();
    int qi = query.indexOf('?');
    if (qi >= 0) {
        String qs = query.substring(qi + 1);
        int p = 0;
        while (p < (int)qs.length()) {
            int eq = qs.indexOf('=', p);
            int amp = qs.indexOf('&', p);
            if (eq < 0) break;
            String k = qs.substring(p, eq);
            String v = qs.substring(eq + 1, amp < 0 ? qs.length() : amp);
            int n = v.toInt();
            if      (k == "x") x = n;
            else if (k == "y") y = n;
            else if (k == "w") w = n;
            else if (k == "h") h = n;
            if (amp < 0) break;
            p = amp + 1;
        }
    }
    size_t expected = (size_t)w * h * 2;
    if (contentLen != expected) {
        writeError(c, 400, "Bad Request", "size != w*h*2");
        return;
    }
    // Allocate in PSRAM to avoid blowing DRAM on full 600×400×2 = 480KB
    uint8_t* buf = (uint8_t*)ps_malloc(expected);
    if (!buf) { writeError(c, 500, "Internal", "alloc fail"); return; }
    size_t got = 0;
    uint32_t deadline = millis() + 8000;
    while (got < expected && millis() < deadline) {
        int n = c.read(buf + got, expected - got);
        if (n > 0) got += n;
        else delay(1);
    }
    bool ok = (got == expected) && frameAcceptRGB565(x, y, w, h, buf, expected);
    free(buf);
    if (ok) writeStatus(c, 200, "OK", "application/json", "{\"ok\":true}");
    else    writeError(c, 500, "Internal", "frame accept failed");
}

// ---- request router -----------------------------------------------------

void handleClient(WiFiClient c) {
    IPAddress peer = c.remoteIP();
    snprintf(g_daemonIp, sizeof(g_daemonIp), "%u.%u.%u.%u",
             peer[0], peer[1], peer[2], peer[3]);

    String req = readLine(c);
    if (req.isEmpty()) { c.stop(); return; }
    int sp1 = req.indexOf(' '), sp2 = req.indexOf(' ', sp1 + 1);
    if (sp1 < 0 || sp2 < 0) {
        writeError(c, 400, "Bad Request", "bad req line"); c.stop(); return;
    }
    String method = req.substring(0, sp1);
    String path   = req.substring(sp1 + 1, sp2);

    size_t contentLen = 0;
    while (true) {
        String h = readLine(c);
        if (h.isEmpty()) break;
        int colon = h.indexOf(':');
        if (colon < 0) continue;
        String name = h.substring(0, colon); name.toLowerCase();
        if (name == "content-length") contentLen = h.substring(colon + 1).toInt();
    }

    String basePath = path;
    int qi = basePath.indexOf('?');
    if (qi >= 0) basePath = basePath.substring(0, qi);

    if (method == "GET"  && basePath == "/status")           handleStatus(c);
    else if (method == "POST" && basePath == "/provision-wifi") handleProvisionWifi(c, contentLen);
    else if (method == "POST" && basePath == "/frame")          handleFrame(c, path, contentLen);
    else if (method == "POST" && basePath == "/cmd") {
        String body; body.reserve(contentLen + 1);
        size_t got = 0;
        uint32_t deadline = millis() + 2000;
        while (got < contentLen && millis() < deadline) {
            int b = c.read();
            if (b < 0) { delay(1); continue; }
            body += (char)b; got++;
        }
        JsonDocument doc;
        if (deserializeJson(doc, body)) {
            writeError(c, 400, "Bad Request", "invalid JSON");
        } else {
            const char* cmd = doc["cmd"] | "";
            if (strcmp(cmd, "sleep_now") == 0) {
                // Reply BEFORE entering deep sleep, then let the panel
                // refresh settle, then sleep.
                writeStatus(c, 200, "OK", "application/json",
                            "{\"ack\":\"sleep_now\",\"ok\":true}");
                c.flush(); c.stop();
                Serial.println("[cmd] sleep_now — settling panel + deep sleep");
                // Spectra 6 needs ~2.5 s to finish its full refresh waveform
                // before we cut power; otherwise the panel can stop mid-cycle
                // and leave colored ghosts.
                delay(2500);
                Serial.flush();
                // Enable button A/B/C as wake source (RTC GPIO).
                // BtnA=G10, BtnB=G9, BtnC=G1. All three trigger on LOW.
                esp_sleep_enable_ext1_wakeup(
                    (1ULL << 10) | (1ULL << 9) | (1ULL << 1),
                    ESP_EXT1_WAKEUP_ANY_LOW);
                esp_deep_sleep_start();
                return;   // unreachable
            } else if (strcmp(cmd, "restart") == 0) {
                writeStatus(c, 200, "OK", "application/json",
                            "{\"ack\":\"restart\"}");
                c.flush(); c.stop();
                delay(200); ESP.restart();
                return;
            } else {
                writeError(c, 400, "Bad Request", "unknown cmd");
            }
        }
    }
    else if (method == "POST" && basePath == "/beep") {
        // Body: { "pattern": "chime|urgent|alert" }  or  { "freq": Hz, "ms": dur }
        String body; body.reserve(contentLen + 1);
        size_t got = 0;
        uint32_t deadline = millis() + 2000;
        while (got < contentLen && millis() < deadline) {
            int b = c.read();
            if (b < 0) { delay(1); continue; }
            body += (char)b; got++;
        }
        JsonDocument doc;
        deserializeJson(doc, body);
        const char* pat = doc["pattern"] | "";
        bool ok = true;
        if (strcmp(pat, "chime") == 0)  audioBeepChime();
        else if (strcmp(pat, "urgent") == 0) audioBeepUrgent();
        else if (strcmp(pat, "alert") == 0)  audioBeepAlert();
        else {
            int freq = doc["freq"] | 0;
            int ms   = doc["ms"]   | 200;
            if (freq > 0) audioTone((uint16_t)freq, (uint16_t)ms);
            else { ok = false; }
        }
        writeStatus(c, ok ? 200 : 400,
                    ok ? "OK" : "Bad Request",
                    "application/json",
                    ok ? String("{\"ok\":true,\"pattern\":\"") + pat + "\"}"
                       : String("{\"error\":\"need pattern or freq+ms\"}"));
    }
    else writeError(c, 404, "Not Found", "no such route");

    c.flush();
    c.stop();
}

}  // namespace

void httpServerStart() {
    if (g_started) return;
    g_server.begin();
    g_started = true;
    Serial.printf("[http] listening on :%u\n", kPort);
}
void httpServerStop() {
    if (!g_started) return;
    g_server.end(); g_started = false;
    Serial.println("[http] stopped");
}
void httpServerPoll() {
    if (!g_started) return;
    WiFiClient c = g_server.available();
    if (c) handleClient(c);
}
bool httpServerRunning() { return g_started; }
uint16_t httpServerPort() { return kPort; }

const char* httpDaemonIp() { return g_daemonIp; }

bool httpPostJsonToDaemon(const char* path, const char* json) {
    if (g_daemonIp[0] == 0 || !WiFi.isConnected()) return false;
    WiFiClient c;
    if (!c.connect(g_daemonIp, kDaemonPort)) return false;
    size_t n = strlen(json);
    c.printf("POST %s HTTP/1.1\r\nHost: %s:%u\r\n", path, g_daemonIp,
             (unsigned)kDaemonPort);
    c.print("Content-Type: application/json\r\n");
    c.printf("Content-Length: %u\r\nConnection: close\r\n\r\n", (unsigned)n);
    c.write((const uint8_t*)json, n);
    uint32_t deadline = millis() + 1500;
    while (c.connected() && millis() < deadline) {
        if (c.available()) c.read(); else delay(2);
    }
    c.stop();
    return true;
}
