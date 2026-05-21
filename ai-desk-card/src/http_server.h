// HTTP server for v0.8 Wi-Fi transport. Three endpoints:
//
//   POST /frame          full frame (259200 bytes raw 4bpp)
//                        headers: X-Frame-Fid, X-Frame-CRC
//   POST /frame?x=&y=&w=&h=
//                        region update (w*h/2 bytes raw 4bpp)
//                        headers same as above
//   POST /cmd            JSON body, same dispatch as serial/BLE
//                        e.g. {"cmd":"restart"}
//   GET  /status         JSON: battery_pct, battery_mv, firmware, mac,
//                        uptime_s, wifi:{ssid,ip,rssi}
//
// The /frame handler writes pixels directly into frameBuffer() then calls
// frameDisplay(). Shares the PSRAM buffer with serial/BLE via the
// frameAcquireBuffer()/frameReleaseBuffer() lock.

#pragma once
#include <Arduino.h>

void httpServerStart();           // call after Wi-Fi connected
void httpServerStop();            // call when Wi-Fi goes down (battery mode)
void httpServerPoll();             // call in loop(); no-op if not started
bool httpServerRunning();
uint16_t httpServerPort();        // 9880 by default
