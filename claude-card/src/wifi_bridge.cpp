#include "wifi_bridge.h"
#include <WiFi.h>
#include <Preferences.h>

namespace {

constexpr const char* kNvsNamespace = "wifi";
constexpr const char* kNvsSsidKey   = "ssid";
constexpr const char* kNvsPassKey   = "pass";

// State machine. CONNECTING blocks the next connect attempt while one is
// already in flight. SLEPT means the radio is intentionally off (battery
// mode); we won't auto-reconnect until wifiWakeNow().
enum State {
    STATE_UNCONFIGURED,
    STATE_CONNECTING,
    STATE_CONNECTED,
    STATE_DISCONNECTED,
    STATE_SLEPT,
};

State    g_state = STATE_UNCONFIGURED;
char     g_ssid[33] = "";
char     g_pass[65] = "";
uint32_t g_lastAttemptMs = 0;
uint32_t g_connectStartMs = 0;
IPAddress g_ip(0,0,0,0);

constexpr uint32_t kConnectTimeoutMs = 12000;   // give up one attempt after 12 s
constexpr uint32_t kRetryGapMs       = 30000;   // 30 s between attempts

void loadCreds() {
    Preferences prefs;
    if (!prefs.begin(kNvsNamespace, true)) {
        Serial.println("[wifi] no NVS namespace");
        return;
    }
    String s = prefs.getString(kNvsSsidKey, "");
    String p = prefs.getString(kNvsPassKey, "");
    prefs.end();
    strlcpy(g_ssid, s.c_str(), sizeof(g_ssid));
    strlcpy(g_pass, p.c_str(), sizeof(g_pass));
}

void beginConnect() {
    if (g_ssid[0] == 0) { g_state = STATE_UNCONFIGURED; return; }
    Serial.printf("[wifi] connecting to '%s'\n", g_ssid);
    WiFi.mode(WIFI_STA);
    WiFi.disconnect(true, true);  // drop stale state
    delay(50);
    WiFi.begin(g_ssid, g_pass);
    g_state = STATE_CONNECTING;
    g_connectStartMs = millis();
    g_lastAttemptMs  = g_connectStartMs;
}

}  // namespace

void wifiInit() {
    loadCreds();
    if (g_ssid[0] != 0) {
        beginConnect();
    } else {
        Serial.println("[wifi] no credentials in NVS — staying off until "
                       "cmd:wifi_set arrives");
        g_state = STATE_UNCONFIGURED;
    }
}

void wifiPoll() {
    switch (g_state) {
    case STATE_UNCONFIGURED:
    case STATE_SLEPT:
        return;
    case STATE_CONNECTING: {
        wl_status_t st = WiFi.status();
        if (st == WL_CONNECTED) {
            g_ip = WiFi.localIP();
            g_state = STATE_CONNECTED;
            Serial.printf("[wifi] connected: ip=%s rssi=%d\n",
                          g_ip.toString().c_str(), WiFi.RSSI());
            return;
        }
        if (millis() - g_connectStartMs > kConnectTimeoutMs) {
            Serial.printf("[wifi] connect timeout (status=%d)\n", (int)st);
            WiFi.disconnect(true);
            g_state = STATE_DISCONNECTED;
        }
        return;
    }
    case STATE_CONNECTED:
        if (!WiFi.isConnected()) {
            Serial.println("[wifi] link dropped");
            g_state = STATE_DISCONNECTED;
            g_ip = IPAddress(0, 0, 0, 0);
        }
        return;
    case STATE_DISCONNECTED:
        if (millis() - g_lastAttemptMs > kRetryGapMs) {
            beginConnect();
        }
        return;
    }
}

bool wifiConnected() { return g_state == STATE_CONNECTED; }

const char* wifiSSID() { return g_ssid; }

static char s_ipBuf[16];
const char* wifiIPStr() {
    if (!wifiConnected()) { s_ipBuf[0] = 0; return s_ipBuf; }
    snprintf(s_ipBuf, sizeof(s_ipBuf), "%u.%u.%u.%u",
             g_ip[0], g_ip[1], g_ip[2], g_ip[3]);
    return s_ipBuf;
}

int wifiRSSI() {
    return wifiConnected() ? WiFi.RSSI() : -127;
}

void wifiSetCredentials(const char* ssid, const char* password) {
    if (!ssid) ssid = "";
    if (!password) password = "";
    Preferences prefs;
    if (!prefs.begin(kNvsNamespace, false)) {
        Serial.println("[wifi] NVS open failed for write");
        return;
    }
    if (ssid[0] == 0) {
        prefs.remove(kNvsSsidKey);
        prefs.remove(kNvsPassKey);
        prefs.end();
        g_ssid[0] = 0; g_pass[0] = 0;
        WiFi.disconnect(true, true);
        g_state = STATE_UNCONFIGURED;
        Serial.println("[wifi] credentials cleared");
        return;
    }
    prefs.putString(kNvsSsidKey, ssid);
    prefs.putString(kNvsPassKey, password);
    prefs.end();
    strlcpy(g_ssid, ssid, sizeof(g_ssid));
    strlcpy(g_pass, password, sizeof(g_pass));
    Serial.printf("[wifi] credentials saved: ssid='%s' pass_len=%u\n",
                  g_ssid, (unsigned)strlen(g_pass));
    beginConnect();
}

void wifiWakeNow() {
    if (g_state == STATE_CONNECTED || g_state == STATE_CONNECTING) return;
    if (g_ssid[0] == 0) {
        Serial.println("[wifi] wake_now but no credentials");
        return;
    }
    beginConnect();
}

void wifiPowerDown() {
    if (g_state == STATE_SLEPT) return;
    Serial.println("[wifi] powering down radio");
    WiFi.disconnect(true, true);
    WiFi.mode(WIFI_OFF);
    g_ip = IPAddress(0, 0, 0, 0);
    g_state = STATE_SLEPT;
}
