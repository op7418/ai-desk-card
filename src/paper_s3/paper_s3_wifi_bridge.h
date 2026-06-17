#pragma once

#include <Arduino.h>

void wifiInit();
void wifiAutoConnect();
void wifiPoll();
bool wifiConnected();
const char* wifiSSID();
const char* wifiMaskedSSID();
const char* wifiIPStr();
int wifiRSSI();
const char* wifiStateName();
const char* wifiLastError();
int wifiLastStatus();
void wifiSetCredentials(const char* ssid, const char* password);
void wifiWakeNow();
