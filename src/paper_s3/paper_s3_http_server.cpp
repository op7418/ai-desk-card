#include "paper_s3_http_server.h"

// PaperS3 Wi-Fi transport endpoints:
//   GET  /status
//   POST /cmd
//   POST /frame  (raw 540x960 4bpp, headers include X-Frame-Crc)
//
// This is intentionally profile-local and does not depend on the V1.1 driver.

#include "paper_s3_frame_receiver.h"
#include "paper_s3_hw.h"
#include "paper_s3_wifi_bridge.h"

#include <ArduinoJson.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <WiFiServer.h>
#include <esp_mac.h>

extern bool dispatchCmd(JsonDocument& doc);

namespace {

constexpr uint16_t kPort = 9880;
constexpr uint16_t kDaemonPort = 9877;
WiFiServer g_server(kPort);
bool g_started = false;
char g_daemonIp[16] = "";

struct RequestHeaders {
    size_t contentLen = 0;
    uint32_t frameFid = 0;
    uint32_t frameCrc = 0;
    uint32_t frameBytes = 0;
    int frameWidth = 0;
    int frameHeight = 0;
    int frameBpp = 0;
};

String readLine(WiFiClient& c, uint32_t timeoutMs = 2000) {
    String s;
    s.reserve(256);
    const uint32_t deadline = millis() + timeoutMs;
    while (millis() < deadline) {
        if (!c.connected()) break;
        const int b = c.read();
        if (b < 0) {
            delay(1);
            continue;
        }
        if (b == '\n') {
            if (s.length() > 0 && s.charAt(s.length() - 1) == '\r') {
                s.remove(s.length() - 1);
            }
            return s;
        }
        s += (char)b;
        if (s.length() > 2048) break;
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
    String body = "{\"error\":\"";
    body += msg ? msg : reason;
    body += "\"}";
    writeStatus(c, code, reason, "application/json", body);
}

uint32_t parseU32(const String& value, int base = 10) {
    return (uint32_t)strtoul(value.c_str(), nullptr, base);
}

void parseHeaderLine(const String& line, RequestHeaders& headers) {
    const int colon = line.indexOf(':');
    if (colon < 0) return;
    String name = line.substring(0, colon);
    String value = line.substring(colon + 1);
    name.toLowerCase();
    value.trim();
    if (name == "content-length") {
        headers.contentLen = (size_t)value.toInt();
    } else if (name == "x-frame-fid") {
        headers.frameFid = parseU32(value);
    } else if (name == "x-frame-crc") {
        headers.frameCrc = parseU32(value, 16);
    } else if (name == "x-frame-width") {
        headers.frameWidth = value.toInt();
    } else if (name == "x-frame-height") {
        headers.frameHeight = value.toInt();
    } else if (name == "x-frame-bpp") {
        headers.frameBpp = value.toInt();
    } else if (name == "x-frame-bytes") {
        headers.frameBytes = parseU32(value);
    }
}

void rememberPeer(WiFiClient& c) {
    const IPAddress peer = c.remoteIP();
    snprintf(g_daemonIp, sizeof(g_daemonIp), "%u.%u.%u.%u",
             peer[0], peer[1], peer[2], peer[3]);
}

void setNullableBool(JsonDocument& doc, const char* key, int8_t value) {
    if (value > 0) {
        doc[key] = true;
    } else if (value == 0) {
        doc[key] = false;
    } else {
        doc[key] = nullptr;
    }
}

void setNullableBool(JsonObject obj, const char* key, int8_t value) {
    if (value > 0) {
        obj[key] = true;
    } else if (value == 0) {
        obj[key] = false;
    } else {
        obj[key] = nullptr;
    }
}

void handleStatus(WiFiClient& c) {
    const paper_s3::PowerState power = paper_s3::readPower();
    uint8_t mac[6] = {0};
    esp_read_mac(mac, ESP_MAC_WIFI_STA);
    char macStr[18];
    snprintf(macStr, sizeof(macStr), "%02X:%02X:%02X:%02X:%02X:%02X",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);

    JsonDocument doc;
    doc["device"] = paper_s3::kDeviceName;
    doc["firmware"] = CARD_VERSION;
    doc["proto"] = 1;
    doc["mac"] = macStr;
    doc["uptime_s"] = millis() / 1000UL;
    doc["battery_pct"] = power.batteryPercent;
    doc["battery_mv"] = power.batteryMillivolts;
    doc["vbus_mv"] = power.vbusMillivolts;
    doc["power_source"] = power.source;
    doc["power_mode"] = "always-on";
    doc["deep_sleep_enabled"] = false;
    doc["wake_reason"] = "boot";
    doc["last_power_read_ms"] = power.lastReadMs;
    setNullableBool(doc, "on_usb", power.usbPresent);
    setNullableBool(doc, "charging", power.charging);
    JsonObject powerObj = doc["power"].to<JsonObject>();
    powerObj["mode"] = "always-on";
    powerObj["source"] = power.source;
    powerObj["battery_pct"] = power.batteryPercent;
    powerObj["battery_mv"] = power.batteryMillivolts;
    powerObj["vbus_mv"] = power.vbusMillivolts;
    powerObj["deep_sleep_enabled"] = false;
    powerObj["wake_reason"] = "boot";
    powerObj["last_power_read_ms"] = power.lastReadMs;
    setNullableBool(powerObj, "on_usb", power.usbPresent);
    setNullableBool(powerObj, "charging", power.charging);
    doc["frame_state"] = paper_s3_frame::stateName();
    JsonObject wifi = doc["wifi"].to<JsonObject>();
    wifi["state"] = wifiStateName();
    wifi["connected"] = wifiConnected();
    wifi["ssid"] = wifiMaskedSSID();
    wifi["ip"] = wifiIPStr();
    wifi["rssi"] = wifiRSSI();
    wifi["last_error"] = wifiLastError();
    wifi["status"] = wifiLastStatus();
    String body;
    serializeJson(doc, body);
    writeStatus(c, 200, "OK", "application/json", body);
}

bool readBody(WiFiClient& c, uint8_t* buf, size_t len, uint32_t timeoutMs) {
    size_t got = 0;
    const uint32_t deadline = millis() + timeoutMs;
    while (got < len && millis() < deadline) {
        const int avail = c.available();
        if (avail <= 0) {
            delay(1);
            continue;
        }
        size_t toRead = (size_t)avail;
        if (toRead > len - got) toRead = len - got;
        const int n = c.read(buf + got, toRead);
        if (n <= 0) {
            delay(1);
            continue;
        }
        got += (size_t)n;
    }
    return got == len;
}

void handleFrame(WiFiClient& c, const RequestHeaders& headers) {
    const size_t expected = paper_s3_frame::kFrameBytes4bpp;
    if (headers.contentLen != expected) {
        Serial.printf("[http] bad frame bytes got=%u expected=%u\n",
                      (unsigned)headers.contentLen, (unsigned)expected);
        paper_s3_frame::setErrorState("http-content-length-mismatch");
        writeError(c, 400, "Bad Request", "content-length mismatch");
        return;
    }
    if (headers.frameBytes && headers.frameBytes != expected) {
        paper_s3_frame::setErrorState("http-frame-bytes-mismatch");
        writeError(c, 400, "Bad Request", "x-frame-bytes mismatch");
        return;
    }
    if ((headers.frameWidth && headers.frameWidth != paper_s3_frame::kFrameWidth) ||
        (headers.frameHeight && headers.frameHeight != paper_s3_frame::kFrameHeight) ||
        (headers.frameBpp && headers.frameBpp != 4)) {
        paper_s3_frame::setErrorState("http-frame-format-mismatch");
        writeError(c, 400, "Bad Request", "frame format mismatch");
        return;
    }

    uint8_t* buf = (uint8_t*)ps_malloc(expected);
    if (!buf) {
        paper_s3_frame::setErrorState("http-frame-alloc-failed");
        writeError(c, 500, "Internal Server Error", "frame alloc failed");
        return;
    }
    Serial.printf("[http] frame transfer started fid=%u bytes=%u\n",
                  (unsigned)headers.frameFid, (unsigned)expected);
    const bool bodyOk = readBody(c, buf, expected, 20000);
    if (!bodyOk) {
        free(buf);
        paper_s3_frame::setErrorState("http-frame-timeout");
        Serial.println("[http] frame transfer aborted reason=timeout");
        writeError(c, 408, "Request Timeout", "frame body timeout");
        return;
    }
    const bool ok = paper_s3_frame::drawHttpFrame(
        buf, expected, headers.frameFid, headers.frameCrc);
    free(buf);
    if (!ok) {
        Serial.println("[http] bad frame; previous display retained");
        writeError(c, 400, "Bad Request", "bad frame");
        return;
    }
    Serial.printf("[http] frame transfer completed fid=%u bytes=%u\n",
                  (unsigned)headers.frameFid, (unsigned)expected);
    writeStatus(c, 200, "OK", "application/json", "{\"ok\":true}");
}

void handleCmd(WiFiClient& c, const RequestHeaders& headers) {
    if (headers.contentLen == 0 || headers.contentLen > 2048) {
        writeError(c, 400, "Bad Request", "bad content length");
        return;
    }
    char* body = (char*)malloc(headers.contentLen + 1);
    if (!body) {
        writeError(c, 500, "Internal Server Error", "cmd alloc failed");
        return;
    }
    const bool ok = readBody(c, (uint8_t*)body, headers.contentLen, 2000);
    body[headers.contentLen] = '\0';
    if (!ok) {
        free(body);
        writeError(c, 408, "Request Timeout", "cmd body timeout");
        return;
    }
    JsonDocument doc;
    if (deserializeJson(doc, body) != DeserializationError::Ok) {
        free(body);
        writeError(c, 400, "Bad Request", "invalid JSON");
        return;
    }
    free(body);
    const bool handled = dispatchCmd(doc);
    writeStatus(c, handled ? 200 : 404, handled ? "OK" : "Not Found",
                "application/json", handled ? "{\"ok\":true}" : "{\"ok\":false}");
}

void handleClient(WiFiClient c) {
    rememberPeer(c);
    const String reqLine = readLine(c);
    if (reqLine.isEmpty()) {
        c.stop();
        return;
    }
    const int sp1 = reqLine.indexOf(' ');
    const int sp2 = reqLine.indexOf(' ', sp1 + 1);
    if (sp1 < 0 || sp2 < 0) {
        writeError(c, 400, "Bad Request", "bad request line");
        c.stop();
        return;
    }
    const String method = reqLine.substring(0, sp1);
    String path = reqLine.substring(sp1 + 1, sp2);
    RequestHeaders headers;
    while (true) {
        const String line = readLine(c);
        if (line.isEmpty()) break;
        parseHeaderLine(line, headers);
    }

    String basePath = path;
    const int query = basePath.indexOf('?');
    if (query >= 0) basePath = basePath.substring(0, query);

    if (method == "GET" && basePath == "/status") {
        handleStatus(c);
    } else if (method == "POST" && basePath == "/frame") {
        handleFrame(c, headers);
    } else if (method == "POST" && basePath == "/cmd") {
        handleCmd(c, headers);
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
    WiFiClient client = g_server.available();
    if (client) {
        Serial.println("[http] client connected");
        handleClient(client);
        Serial.println("[http] client disconnected");
    }
}

bool httpServerRunning() {
    return g_started;
}

uint16_t httpServerPort() {
    return kPort;
}

const char* httpDaemonIp() {
    return g_daemonIp;
}

bool httpPostJsonToDaemon(const char* path, const char* json) {
    if (g_daemonIp[0] == '\0' || !wifiConnected()) return false;
    WiFiClient c;
    if (!c.connect(g_daemonIp, kDaemonPort)) {
        Serial.printf("[http] daemon post failed path=%s target=%s:%u\n",
                      path, g_daemonIp, (unsigned)kDaemonPort);
        return false;
    }
    const size_t n = strlen(json);
    c.printf("POST %s HTTP/1.1\r\n", path);
    c.printf("Host: %s:%u\r\n", g_daemonIp, (unsigned)kDaemonPort);
    c.print("Content-Type: application/json\r\n");
    c.printf("Content-Length: %u\r\n", (unsigned)n);
    c.print("Connection: close\r\n\r\n");
    c.write((const uint8_t*)json, n);
    const uint32_t deadline = millis() + 1500;
    while (c.connected() && millis() < deadline) {
        if (c.available()) c.read();
        else delay(2);
    }
    c.stop();
    return true;
}
