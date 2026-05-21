// Server-side-render frame receiver. Replaces the on-device TTF renderer.
//
// Wire protocol (v0.6 full + v0.7 region):
//
//   Full frame:
//     {"cmd":"frame_begin","fid":N,"w":540,"h":960,"bpp":4,"chunks":K,"crc":X}
//     {"cmd":"frame_chunk","fid":N,"seq":0,"data":"<base64 of 4bpp pixels>"}
//     ... K chunks total ...
//     {"cmd":"frame_end","fid":N}
//
//   Partial region update (v0.7+):
//     {"cmd":"frame_region_begin","fid":N,"x":X,"y":Y,"w":W,"h":H,
//      "bpp":4,"chunks":K,"crc":X}
//     {"cmd":"frame_chunk",...}    ← same chunk protocol; pixels are W*H/2 bytes total
//     {"cmd":"frame_end","fid":N}
//
// After frame_end we WritePartGram4bpp + UpdateFull (full) or
// UpdateArea (region). The same 259 KB PSRAM buffer holds full or region
// payloads; region geometry is stored separately.
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
