#pragma once

#include <Arduino.h>

namespace paper_s3 {

constexpr const char* kDeviceName = "M5Stack PaperS3";
constexpr const char* kIpPlaceholder = "0.0.0.0";

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

void paintTestScreen(const char* firmwareVersion, const char* ipAddress);

}  // namespace paper_s3
