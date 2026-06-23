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
    int16_t vbusMillivolts = -1;
    int8_t charging = -1;
    int8_t usbPresent = -1;
    uint32_t lastReadMs = 0;
    const char* source = "unknown";
};

struct TouchState {
    enum class Event : uint8_t {
        None,
        Down,
        Move,
        Up,
    };

    bool ready = false;
    bool pressed = false;
    Event event = Event::None;
    uint8_t count = 0;
    int32_t rawX = -1;
    int32_t rawY = -1;
    int32_t screenX = -1;
    int32_t screenY = -1;
    int32_t x = 0;  // mapped logical 540x960 coordinate
    int32_t y = 0;  // mapped logical 540x960 coordinate
};

void begin();
void update();

int32_t displayWidth();
int32_t displayHeight();

PowerState readPower();
bool touchReady();
const char* touchMapName();
TouchState readTouch();

void clearDisplay();
void paintTestScreen(const char* firmwareVersion, const char* ipAddress);
void paintWaitingForDashboardScreen(const char* firmwareVersion, const char* ipAddress);
bool draw4bppFrame(const uint8_t* packed, int32_t width, int32_t height);

}  // namespace paper_s3
