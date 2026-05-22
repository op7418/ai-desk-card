// HTTP server for Paper Color. Three endpoints:
//
//   POST /frame              raw RGB565 LE pixels (w*h*2 bytes)
//                            X-Frame-W / X-Frame-H headers for size
//   POST /provision-wifi     JSON {"ssid":"...","password":"..."}
//   GET  /status             JSON fw / battery / wifi / panel
//
// Body is read into a PSRAM buffer; canvas blit happens after full body
// received. After successful blit, canvas.pushSprite() triggers the
// (~15 s) Spectra 6 refresh — server returns 200 before refresh starts,
// so the daemon doesn't time out.

#pragma once
#include <Arduino.h>

void httpServerStart();
void httpServerStop();
void httpServerPoll();
bool httpServerRunning();
uint16_t httpServerPort();

// Daemon discovery: peer IP of the last HTTP client (used for backchannel
// status_report POST). Empty until first inbound request.
const char* httpDaemonIp();
bool httpPostJsonToDaemon(const char* path, const char* json);
