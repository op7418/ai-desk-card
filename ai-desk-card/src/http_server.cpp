#include "http_server.h"
#include "frame_receiver.h"
#include "wifi_bridge.h"

#include <WiFi.h>
#include <WiFiClient.h>
#include <WiFiServer.h>
#include <ArduinoJson.h>
#include <M5EPD.h>
#include <esp_mac.h>

// Forward — defined in main.cpp. We borrow its JSON command dispatcher so
// /cmd reuses the same handler tree as serial/BLE.
extern bool dispatchCmd(JsonDocument& doc);

namespace {

constexpr uint16_t kPort = 9880;
WiFiServer g_server(kPort);
bool       g_started = false;

// --- minimal HTTP parsing -----------------------------------------------

// Read one line ending in CRLF. Trims trailing '\r'. Returns empty string
// on timeout or socket close. Caller-supplied buffer.
String readLine(WiFiClient& c, uint32_t timeoutMs = 2000) {
    String s; s.reserve(256);
    uint32_t deadline = millis() + timeoutMs;
    while (millis() < deadline) {
        if (!c.connected()) break;
        int b = c.read();
        if (b < 0) { delay(1); continue; }
        if (b == '\n') {
            if (s.length() > 0 && s.charAt(s.length() - 1) == '\r')
                s.remove(s.length() - 1);
            return s;
        }
        s += (char)b;
        if (s.length() > 2048) break;   // safety
    }
    return s;
}

void writeStatus(WiFiClient& c, int code, const char* reason,
                 const char* contentType, const String& body) {
    c.printf("HTTP/1.1 %d %s\r\n", code, reason);
    c.printf("Content-Type: %s\r\n", contentType);
    c.printf("Content-Length: %u\r\n", (unsigned)body.length());
    c.print("Connection: close\r\n\r\n");
    c.print(body);
}

void writeError(WiFiClient& c, int code, const char* reason, const char* msg) {
    String b = "{\"error\":\"";
    b += msg ? msg : reason;
    b += "\"}";
    writeStatus(c, code, reason, "application/json", b);
}

// --- /status ------------------------------------------------------------

void handleStatus(WiFiClient& c) {
    uint32_t mv = M5.getBatteryVoltage();
    int pct = (int)((mv - 3300) * 100 / 900);
    if (pct < 0) pct = 0; if (pct > 100) pct = 100;
    uint8_t mac[6] = {0};
    esp_read_mac(mac, ESP_MAC_BT);
    char macStr[18];
    snprintf(macStr, sizeof(macStr), "%02X:%02X:%02X:%02X:%02X:%02X",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);

    JsonDocument doc;
    doc["battery_pct"] = pct;
    doc["battery_mv"]  = mv;
    doc["firmware"]    = CARD_VERSION;
    doc["mac"]         = macStr;
    doc["uptime_s"]    = millis() / 1000UL;
    JsonObject wifi = doc["wifi"].to<JsonObject>();
    wifi["ssid"] = wifiSSID();
    wifi["ip"]   = wifiIPStr();
    wifi["rssi"] = wifiRSSI();
    String out;
    serializeJson(doc, out);
    writeStatus(c, 200, "OK", "application/json", out);
}

// --- /cmd ---------------------------------------------------------------

void handleCmd(WiFiClient& c, size_t contentLen) {
    if (contentLen == 0 || contentLen > 1024) {
        writeError(c, 400, "Bad Request", "bad content length");
        return;
    }
    String body; body.reserve(contentLen + 1);
    size_t got = 0;
    uint32_t deadline = millis() + 2000;
    while (got < contentLen && millis() < deadline) {
        int b = c.read();
        if (b < 0) { delay(1); continue; }
        body += (char)b;
        got++;
    }
    if (got != contentLen) {
        writeError(c, 408, "Request Timeout", "body short");
        return;
    }
    JsonDocument doc;
    if (deserializeJson(doc, body) != DeserializationError::Ok) {
        writeError(c, 400, "Bad Request", "json parse fail");
        return;
    }
    bool handled = dispatchCmd(doc);
    String resp = "{\"ok\":";
    resp += handled ? "true" : "false";
    resp += "}";
    writeStatus(c, handled ? 200 : 404, handled ? "OK" : "Not Found",
                "application/json", resp);
}

// --- /frame -------------------------------------------------------------

struct FrameQuery {
    bool is_region = false;
    int  x = 0, y = 0, w = 0, h = 0;
    bool ok = true;
};

FrameQuery parseFrameQuery(const String& path) {
    FrameQuery q;
    int qIdx = path.indexOf('?');
    if (qIdx < 0) return q;
    q.is_region = true;
    int start = qIdx + 1;
    while (start < (int)path.length()) {
        int eq = path.indexOf('=', start);
        int amp = path.indexOf('&', start);
        if (eq < 0) break;
        String key = path.substring(start, eq);
        String val = (amp < 0)
            ? path.substring(eq + 1)
            : path.substring(eq + 1, amp);
        int v = val.toInt();
        if      (key == "x") q.x = v;
        else if (key == "y") q.y = v;
        else if (key == "w") q.w = v;
        else if (key == "h") q.h = v;
        if (amp < 0) break;
        start = amp + 1;
    }
    if (q.w <= 0 || q.h <= 0) q.ok = false;
    return q;
}

void handleFrame(WiFiClient& c, const String& path, size_t contentLen) {
    FrameQuery q = parseFrameQuery(path);
    if (!q.ok) { writeError(c, 400, "Bad Request", "missing w/h"); return; }

    size_t expected = q.is_region
        ? (size_t)q.w * q.h / 2
        : frameBufferSize();
    if (contentLen != expected) {
        writeError(c, 400, "Bad Request", "content-length mismatch");
        return;
    }
    if (!frameAcquireBuffer()) {
        writeError(c, 503, "Service Unavailable", "buffer busy");
        return;
    }
    uint8_t* buf = frameBuffer();
    if (!buf) {
        frameReleaseBuffer();
        writeError(c, 500, "Internal Server Error", "no frame buffer");
        return;
    }
    // Stream body directly into PSRAM. 250 KB at WiFi LAN speeds = << 1 s.
    size_t got = 0;
    uint32_t deadline = millis() + 20000;
    while (got < contentLen && millis() < deadline) {
        int avail = c.available();
        if (avail <= 0) { delay(1); continue; }
        size_t toRead = (size_t)avail;
        if (toRead > contentLen - got) toRead = contentLen - got;
        int n = c.read(buf + got, toRead);
        if (n <= 0) { delay(1); continue; }
        got += (size_t)n;
    }
    if (got != contentLen) {
        frameReleaseBuffer();
        writeError(c, 408, "Request Timeout", "body short");
        return;
    }
    if (q.is_region) {
        Serial.printf("[http] frame region (%d,%d %dx%d) %u bytes — pushing\n",
                      q.x, q.y, q.w, q.h, (unsigned)got);
        frameDisplay(q.x, q.y, q.w, q.h);
    } else {
        Serial.printf("[http] full frame %u bytes — pushing\n", (unsigned)got);
        frameDisplay(0, 0, 540, 960);
    }
    frameReleaseBuffer();
    writeStatus(c, 200, "OK", "application/json", "{\"ok\":true}");
}

// --- main per-connection handler ----------------------------------------

void handleClient(WiFiClient c) {
    // Parse request line: METHOD PATH HTTP/x.x
    String reqLine = readLine(c);
    if (reqLine.isEmpty()) { c.stop(); return; }
    int sp1 = reqLine.indexOf(' ');
    int sp2 = reqLine.indexOf(' ', sp1 + 1);
    if (sp1 < 0 || sp2 < 0) {
        writeError(c, 400, "Bad Request", "bad request line"); c.stop(); return;
    }
    String method = reqLine.substring(0, sp1);
    String path   = reqLine.substring(sp1 + 1, sp2);

    // Read headers until blank line. We only care about Content-Length.
    size_t contentLen = 0;
    while (true) {
        String h = readLine(c);
        if (h.isEmpty()) break;
        int colon = h.indexOf(':');
        if (colon < 0) continue;
        String name = h.substring(0, colon);
        name.toLowerCase();
        if (name == "content-length") {
            contentLen = h.substring(colon + 1).toInt();
        }
    }

    // Route. Path may carry ?query for /frame.
    String basePath = path;
    int qi = basePath.indexOf('?');
    if (qi >= 0) basePath = basePath.substring(0, qi);

    if (method == "GET" && basePath == "/status") {
        handleStatus(c);
    } else if (method == "POST" && basePath == "/cmd") {
        handleCmd(c, contentLen);
    } else if (method == "POST" && basePath == "/frame") {
        handleFrame(c, path, contentLen);
    } else {
        writeError(c, 404, "Not Found", "no such route");
    }
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
    g_server.end();
    g_started = false;
    Serial.println("[http] stopped");
}

void httpServerPoll() {
    if (!g_started) return;
    WiFiClient c = g_server.available();
    if (c) handleClient(c);
}

bool httpServerRunning() { return g_started; }
uint16_t httpServerPort() { return kPort; }
