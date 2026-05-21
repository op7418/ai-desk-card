// Wi-Fi transport for v0.8. Companion to ble_bridge — both stacks live
// side-by-side on the same ESP32. BLE handles pair + small commands +
// (architecture C) "wake Wi-Fi" signal. Wi-Fi handles bulk frame transfer
// via HTTP (see http_server.{h,cpp}).
//
// Architecture A (always on USB power): wifiInit() at boot auto-connects
//   and stays online. wifiPoll() reconnects on drops.
// Architecture C (battery): same NVS creds, but radio stays off until
//   wifiWakeNow() is called via cmd:wifi_wake_now. wifiPowerDown() puts
//   the radio back to sleep when daemon signals it's done.
//
// Credentials live in Preferences (NVS, namespace "wifi"). Set once via
// the cmd:wifi_set BLE command — no captive portal yet.

#pragma once
#include <Arduino.h>
#include <IPAddress.h>

void wifiInit();           // load NVS credentials; no auto-connect
void wifiAutoConnect();    // if creds loaded, start connecting now
void wifiPoll();           // call in loop(); ~free when nothing to do
bool wifiConnected();
const char* wifiSSID();    // configured SSID ("" if never provisioned)
const char* wifiIPStr();   // dotted-quad of current IP, or ""
int wifiRSSI();            // -127 if disconnected

// Provision: store {ssid, password} to NVS and trigger reconnect.
// password may be "" for open networks. ssid="" forgets the creds.
void wifiSetCredentials(const char* ssid, const char* password);

// Architecture C: bring Wi-Fi up on demand. Idempotent.
void wifiWakeNow();
// Architecture C: take the radio back down to save power.
void wifiPowerDown();
