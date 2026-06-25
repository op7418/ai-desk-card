#pragma once

#include <Arduino.h>

void httpServerStart();
void httpServerStop();
void httpServerPoll();
bool httpServerRunning();
uint16_t httpServerPort();
const char* httpDaemonIp();
bool httpPostJsonToDaemon(const char* path, const char* json);
