#pragma once

#include <Arduino.h>
#include <ArduinoJson.h>

namespace paper_s3_frame {

constexpr int kFrameWidth = 540;
constexpr int kFrameHeight = 960;
constexpr size_t kFrameBytes4bpp = (kFrameWidth * kFrameHeight) / 2;

bool begin();
bool handleCommand(JsonDocument& doc);
const char* stateName();
bool isReceiving();
bool wantsRawBytes();
void appendRawBytes(const uint8_t* data, size_t len);
bool drawHttpFrame(const uint8_t* data, size_t len, uint32_t fid, uint32_t crc);
void setErrorState(const char* reason);

}  // namespace paper_s3_frame
