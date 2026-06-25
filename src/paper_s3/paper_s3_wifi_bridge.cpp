#include "paper_s3_wifi_bridge.h"

#include <Preferences.h>
#include <WiFi.h>

namespace {

constexpr const char* kNvsNamespace = "wifi";
constexpr const char* kNvsSsidKey = "ssid";
constexpr const char* kNvsPassKey = "pass";
constexpr uint32_t kConnectTimeoutMs = 12000;
constexpr uint32_t kRetryGapMs = 30000;

enum WiFiState {
    WIFI_DISABLED,
    WIFI_CONNECTING,
    WIFI_CONNECTED,
    WIFI_FAILED,
};

WiFiState g_state = WIFI_DISABLED;
char g_ssid[33] = "";
char g_pass[65] = "";
char g_ip[16] = "";
char g_masked[40] = "";
char g_lastError[96] = "";
int g_lastStatus = -1;
uint32_t g_connectStartMs = 0;
uint32_t g_lastAttemptMs = 0;

void maskSsid() {
    if (g_ssid[0] == '\0') {
        g_masked[0] = '\0';
        return;
    }
    const size_t len = strlen(g_ssid);
    const size_t keep = len < 3 ? len : 3;
    snprintf(g_masked, sizeof(g_masked), "%.*s***", (int)keep, g_ssid);
}

const char* statusReason(wl_status_t status) {
    switch (status) {
        case WL_NO_SSID_AVAIL: return "ssid-not-found";
        case WL_CONNECT_FAILED: return "auth-or-connect-failed";
        case WL_CONNECTION_LOST: return "connection-lost";
        case WL_DISCONNECTED: return "disconnected";
        default: return "connect-timeout";
    }
}

void loadCredentials() {
    Preferences prefs;
    if (!prefs.begin(kNvsNamespace, true)) {
        snprintf(g_lastError, sizeof(g_lastError), "nvs-open-failed");
        Serial.println("[wifi] disabled: NVS open failed");
        return;
    }
    const String ssid = prefs.getString(kNvsSsidKey, "");
    const String pass = prefs.getString(kNvsPassKey, "");
    prefs.end();
    strlcpy(g_ssid, ssid.c_str(), sizeof(g_ssid));
    strlcpy(g_pass, pass.c_str(), sizeof(g_pass));
    maskSsid();
}

void beginConnect() {
    if (g_ssid[0] == '\0') {
        g_state = WIFI_DISABLED;
        Serial.println("[wifi] disabled: no credentials");
        return;
    }
    g_state = WIFI_CONNECTING;
    g_lastError[0] = '\0';
    g_connectStartMs = millis();
    g_lastAttemptMs = g_connectStartMs;
    Serial.printf("[wifi] connect start ssid=%s\n", wifiMaskedSSID());
    WiFi.mode(WIFI_STA);
    WiFi.disconnect(false, false);
    delay(50);
    WiFi.begin(g_ssid, g_pass);
}

void recordFailure(wl_status_t status) {
    g_lastStatus = (int)status;
    snprintf(g_lastError, sizeof(g_lastError), "%s status=%d",
             statusReason(status), (int)status);
    Serial.printf("[wifi] connect failed reason=%s\n", g_lastError);
    WiFi.disconnect(false, false);
    g_ip[0] = '\0';
    g_state = WIFI_FAILED;
}

}  // namespace

void wifiInit() {
    loadCredentials();
    if (g_ssid[0] == '\0') {
        g_state = WIFI_DISABLED;
        Serial.println("[wifi] disabled: no credentials in NVS");
        return;
    }
    Serial.printf("[wifi] enabled ssid=%s\n", wifiMaskedSSID());
    g_state = WIFI_FAILED;
}

void wifiAutoConnect() {
    if (g_state == WIFI_CONNECTED || g_state == WIFI_CONNECTING) return;
    beginConnect();
}

void wifiPoll() {
    const uint32_t now = millis();
    if (g_state == WIFI_DISABLED) return;

    if (g_state == WIFI_CONNECTING) {
        const wl_status_t status = WiFi.status();
        if (status == WL_CONNECTED) {
            strlcpy(g_ip, WiFi.localIP().toString().c_str(), sizeof(g_ip));
            g_state = WIFI_CONNECTED;
            g_lastError[0] = '\0';
            g_lastStatus = (int)status;
            Serial.printf("[wifi] connected ip=%s rssi=%d\n", g_ip, WiFi.RSSI());
            return;
        }
        if (now - g_connectStartMs > kConnectTimeoutMs) {
            recordFailure(status);
        }
        return;
    }

    if (g_state == WIFI_CONNECTED) {
        if (WiFi.status() != WL_CONNECTED) {
            strlcpy(g_lastError, "wifi-disconnected", sizeof(g_lastError));
            g_lastStatus = (int)WiFi.status();
            g_ip[0] = '\0';
            g_state = WIFI_FAILED;
            Serial.printf("[wifi] disconnected status=%d\n", g_lastStatus);
        }
        return;
    }

    if (g_state == WIFI_FAILED && now - g_lastAttemptMs > kRetryGapMs) {
        Serial.printf("[wifi] retry after %lu ms\n", (unsigned long)kRetryGapMs);
        beginConnect();
    }
}

bool wifiConnected() {
    return g_state == WIFI_CONNECTED && WiFi.status() == WL_CONNECTED;
}

const char* wifiSSID() {
    return g_ssid;
}

const char* wifiMaskedSSID() {
    return g_masked;
}

const char* wifiIPStr() {
    return wifiConnected() ? g_ip : "";
}

int wifiRSSI() {
    return wifiConnected() ? WiFi.RSSI() : -127;
}

const char* wifiStateName() {
    switch (g_state) {
        case WIFI_DISABLED: return "WIFI_DISABLED";
        case WIFI_CONNECTING: return "WIFI_CONNECTING";
        case WIFI_CONNECTED: return "WIFI_CONNECTED";
        case WIFI_FAILED: return "WIFI_FAILED";
        default: return "ERROR";
    }
}

const char* wifiLastError() {
    return g_lastError;
}

int wifiLastStatus() {
    return g_lastStatus;
}

void wifiSetCredentials(const char* ssid, const char* password) {
    if (!ssid) ssid = "";
    if (!password) password = "";
    Preferences prefs;
    if (!prefs.begin(kNvsNamespace, false)) {
        snprintf(g_lastError, sizeof(g_lastError), "nvs-write-failed");
        Serial.println("[wifi] credentials write failed: NVS open failed");
        return;
    }
    if (ssid[0] == '\0') {
        prefs.remove(kNvsSsidKey);
        prefs.remove(kNvsPassKey);
        prefs.end();
        g_ssid[0] = '\0';
        g_pass[0] = '\0';
        g_ip[0] = '\0';
        g_masked[0] = '\0';
        g_lastError[0] = '\0';
        g_state = WIFI_DISABLED;
        WiFi.disconnect(false, true);
        Serial.println("[wifi] credentials cleared");
        return;
    }
    prefs.putString(kNvsSsidKey, ssid);
    prefs.putString(kNvsPassKey, password);
    prefs.end();
    strlcpy(g_ssid, ssid, sizeof(g_ssid));
    strlcpy(g_pass, password, sizeof(g_pass));
    maskSsid();
    Serial.printf("[wifi] credentials saved ssid=%s\n", wifiMaskedSSID());
    beginConnect();
}

void wifiWakeNow() {
    wifiAutoConnect();
}
