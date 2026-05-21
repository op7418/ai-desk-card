// Server-side-render frame receiver. Replaces the on-device TTF renderer.
//
// Wire protocol (added in v0.6):
//
//   {"cmd":"frame_begin","fid":N,"w":540,"h":960,"bpp":4,"chunks":K,"crc":X}
//   {"cmd":"frame_chunk","fid":N,"seq":0,"data":"<base64 of 4bpp pixels>"}
//   ... K chunks total ...
//   {"cmd":"frame_end","fid":N}
//
// After frame_end, we WritePartGram4bpp + UpdateFull(GC16). The 4bpp buffer
// is 540*960/2 = 259,200 bytes; lives in PSRAM (ps_malloc) so we don't
// blow heap.
//
// All UI rendering happens in daemon (PIL). This module is pure plumbing.

#pragma once

#include <Arduino.h>
#include <ArduinoJson.h>
#include <M5EPD.h>

constexpr int FRAME_W   = 540;
constexpr int FRAME_H   = 960;
constexpr size_t FRAME_BYTES_4BPP = (FRAME_W * FRAME_H) / 2;   // 259,200

// Returns true if doc was a frame command (begin/chunk/end) and was consumed.
bool frameHandleCommand(JsonDocument& doc);

// Allocate the PSRAM frame buffer. Call once at boot AFTER M5.begin (PSRAM
// must be ready). Returns false if allocation failed.
bool frameReceiverInit();

// Diagnostics — current state for boot log.
const char* frameReceiverStateName();
