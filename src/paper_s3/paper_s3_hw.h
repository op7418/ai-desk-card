#pragma once

#include <Arduino.h>

namespace paper_s3 {

constexpr const char* kDeviceName = "M5Stack PaperS3";
constexpr const char* kIpPlaceholder = "0.0.0.0";
constexpr int32_t kLogicalFrameWidth = 540;
constexpr int32_t kLogicalFrameHeight = 960;

struct PowerState {
    int32_t batteryPercent = -1;
    int16_t batteryMillivolts = -1;
    bool charging = false;
    bool usbPresent = false;
};

struct TouchState {
    bool pressed = false;
    int32_t x = 0;
    int32_t y = 0;
};

void begin();
void update();

int32_t displayWidth();
int32_t displayHeight();

PowerState readPower();
TouchState readTouch();

void clearDisplay();
void paintTestScreen(const char* firmwareVersion, const char* ipAddress);
bool draw4bppFrame(const uint8_t* packed, int32_t width, int32_t height);

}  // namespace paper_s3
