// Simpler Wi-Fi bridge for Paper Color. No architecture-C wake/sleep —
// this device is mostly stationary on USB power for v1. Just connect
// from NVS-stored creds, auto-reconnect, expose state.

#pragma once
#include <Arduino.h>

void wifiInit();           // load NVS creds + start auto-connect if any
void wifiPoll();           // call in loop(); reconnects on drops
bool wifiConnected();
const char* wifiSSID();
const char* wifiIPStr();
int  wifiRSSI();

// Provision: stores {ssid, password} to NVS and reconnects.
void wifiSetCredentials(const char* ssid, const char* password);
