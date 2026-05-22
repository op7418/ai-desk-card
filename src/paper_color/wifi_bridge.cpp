#include "wifi_bridge.h"
#include <WiFi.h>
#include <Preferences.h>

namespace {
Preferences g_prefs;
String      g_ssid;
String      g_pwd;
char        g_ipStr[16] = "";
bool        g_initialized = false;

void loadCreds() {
    g_prefs.begin("wifi", true);
    g_ssid = g_prefs.getString("ssid", "");
    g_pwd  = g_prefs.getString("pwd", "");
    g_prefs.end();
}

void saveCreds(const char* ssid, const char* pwd) {
    g_prefs.begin("wifi", false);
    g_prefs.putString("ssid", ssid);
    g_prefs.putString("pwd",  pwd);
    g_prefs.end();
    g_ssid = ssid; g_pwd = pwd;
}

void beginConnect() {
    if (g_ssid.isEmpty()) {
        Serial.println("[wifi] no credentials — staying off");
        return;
    }
    Serial.printf("[wifi] connecting to '%s'\n", g_ssid.c_str());
    WiFi.mode(WIFI_STA);
    WiFi.begin(g_ssid.c_str(), g_pwd.c_str());
}
}   // namespace

void wifiInit() {
    if (g_initialized) return;
    g_initialized = true;
    loadCreds();
    if (!g_ssid.isEmpty()) {
        Serial.printf("[wifi] credentials loaded (ssid='%s'); awaiting connect\n",
                      g_ssid.c_str());
        beginConnect();
    } else {
        Serial.println("[wifi] no NVS creds; use POST /provision-wifi");
    }
}

void wifiPoll() {
    static bool s_was_up = false;
    static uint32_t s_lastReconnectAttempt = 0;
    bool up = (WiFi.status() == WL_CONNECTED);
    if (up != s_was_up) {
        s_was_up = up;
        if (up) {
            snprintf(g_ipStr, sizeof(g_ipStr), "%s",
                     WiFi.localIP().toString().c_str());
            Serial.printf("[wifi] connected: ip=%s rssi=%d\n",
                          g_ipStr, (int)WiFi.RSSI());
        } else {
            g_ipStr[0] = 0;
            Serial.println("[wifi] disconnected");
        }
    }
    // Reconnect every 10 s if we have creds but aren't online.
    if (!up && !g_ssid.isEmpty()) {
        uint32_t now = millis();
        if (now - s_lastReconnectAttempt > 10000) {
            s_lastReconnectAttempt = now;
            WiFi.disconnect(true, false);
            delay(50);
            beginConnect();
        }
    }
}

bool wifiConnected()       { return WiFi.status() == WL_CONNECTED; }
const char* wifiSSID()     { return g_ssid.c_str(); }
const char* wifiIPStr()    { return g_ipStr; }
int wifiRSSI()             {
    return WiFi.status() == WL_CONNECTED ? (int)WiFi.RSSI() : -127;
}

void wifiSetCredentials(const char* ssid, const char* pwd) {
    saveCreds(ssid ? ssid : "", pwd ? pwd : "");
    WiFi.disconnect(true, false);
    delay(100);
    beginConnect();
}
