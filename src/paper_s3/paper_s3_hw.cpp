#include "paper_s3_hw.h"

#include <M5GFX.h>
#include <M5Unified.h>

namespace paper_s3 {
namespace {

constexpr uint16_t kWhite = 0xFFFF;
constexpr uint16_t kBlack = 0x0000;
constexpr uint16_t kDarkGray = 0x4208;
constexpr uint16_t kMidGray = 0x8410;
constexpr uint16_t kLightGray = 0xD69A;

M5Canvas g_canvas(&M5.Display);
bool g_canvasReady = false;

enum class FrameMap {
    kDirect,
    kRotateClockwise,
    kUnsupported,
};

enum class TouchMap {
    kDirect,
    kRotateClockwiseFrame,
    kScaled,
};

uint16_t gray4ToRgb565(uint8_t nibble) {
    const uint8_t level = 255 - (nibble & 0x0F) * 17;
    return ((level & 0xF8) << 8) | ((level & 0xFC) << 3) | (level >> 3);
}

FrameMap selectFrameMap(int32_t logicalW, int32_t logicalH) {
    const int32_t panelW = g_canvas.width();
    const int32_t panelH = g_canvas.height();
    if (panelW == logicalW && panelH == logicalH) return FrameMap::kDirect;
    if (panelW == logicalH && panelH == logicalW) return FrameMap::kRotateClockwise;
    return FrameMap::kUnsupported;
}

const char* frameMapName(FrameMap map) {
    switch (map) {
        case FrameMap::kDirect: return "direct";
        case FrameMap::kRotateClockwise: return "rotate-cw";
        default: return "unsupported";
    }
}

int32_t clampCoord(int32_t value, int32_t minValue, int32_t maxValue) {
    if (value < minValue) return minValue;
    if (value > maxValue) return maxValue;
    return value;
}

TouchMap selectTouchMap() {
    const int32_t panelW = g_canvas.width();
    const int32_t panelH = g_canvas.height();
    if (panelW == kLogicalFrameWidth && panelH == kLogicalFrameHeight) {
        return TouchMap::kDirect;
    }
    if (panelW == kLogicalFrameHeight && panelH == kLogicalFrameWidth) {
        return TouchMap::kRotateClockwiseFrame;
    }
    return TouchMap::kScaled;
}

void mapScreenToLogical(int32_t screenX, int32_t screenY,
                        int32_t* logicalX, int32_t* logicalY) {
    if (!logicalX || !logicalY) return;

    const TouchMap map = selectTouchMap();
    if (map == TouchMap::kDirect) {
        *logicalX = clampCoord(screenX, 0, kLogicalFrameWidth - 1);
        *logicalY = clampCoord(screenY, 0, kLogicalFrameHeight - 1);
        return;
    }

    if (map == TouchMap::kRotateClockwiseFrame) {
        *logicalX = clampCoord(kLogicalFrameWidth - 1 - screenY,
                               0, kLogicalFrameWidth - 1);
        *logicalY = clampCoord(screenX, 0, kLogicalFrameHeight - 1);
        return;
    }

    const int32_t panelW = g_canvas.width() > 0 ? g_canvas.width() : 1;
    const int32_t panelH = g_canvas.height() > 0 ? g_canvas.height() : 1;
    *logicalX = clampCoord((screenX * kLogicalFrameWidth) / panelW,
                           0, kLogicalFrameWidth - 1);
    *logicalY = clampCoord((screenY * kLogicalFrameHeight) / panelH,
                           0, kLogicalFrameHeight - 1);
}

void mapLogicalToScreen(int32_t logicalX, int32_t logicalY,
                        int32_t* screenX, int32_t* screenY) {
    if (!screenX || !screenY) return;

    const TouchMap map = selectTouchMap();
    if (map == TouchMap::kDirect) {
        *screenX = clampCoord(logicalX, 0, g_canvas.width() - 1);
        *screenY = clampCoord(logicalY, 0, g_canvas.height() - 1);
        return;
    }

    if (map == TouchMap::kRotateClockwiseFrame) {
        *screenX = clampCoord(logicalY, 0, g_canvas.width() - 1);
        *screenY = clampCoord(kLogicalFrameWidth - 1 - logicalX,
                              0, g_canvas.height() - 1);
        return;
    }

    *screenX = clampCoord((logicalX * g_canvas.width()) / kLogicalFrameWidth,
                          0, g_canvas.width() - 1);
    *screenY = clampCoord((logicalY * g_canvas.height()) / kLogicalFrameHeight,
                          0, g_canvas.height() - 1);
}

const char* touchMapNameFor(TouchMap map) {
    switch (map) {
        case TouchMap::kDirect: return "direct";
        case TouchMap::kRotateClockwiseFrame: return "rotate-cw-inverse";
        default: return "scaled";
    }
}

void drawLabelValue(const char* label, const char* value, int32_t x, int32_t y) {
    g_canvas.setTextDatum(top_left);
    g_canvas.setFont(&fonts::FreeSans9pt7b);
    g_canvas.setTextColor(kDarkGray);
    g_canvas.drawString(label, x, y);

    g_canvas.setFont(&fonts::FreeSansBold12pt7b);
    g_canvas.setTextColor(kBlack);
    g_canvas.drawString(value, x, y + 24);
}

void drawLogicalTarget(const char* label,
                       int32_t targetX, int32_t targetY,
                       int32_t labelX, int32_t labelY,
                       textdatum_t datum) {
    int32_t screenTargetX = 0;
    int32_t screenTargetY = 0;
    mapLogicalToScreen(targetX, targetY, &screenTargetX, &screenTargetY);

    g_canvas.drawCircle(screenTargetX, screenTargetY, 14, kBlack);
    g_canvas.drawLine(screenTargetX - 20, screenTargetY,
                      screenTargetX + 20, screenTargetY, kBlack);
    g_canvas.drawLine(screenTargetX, screenTargetY - 20,
                      screenTargetX, screenTargetY + 20, kBlack);

    int32_t screenLabelX = 0;
    int32_t screenLabelY = 0;
    mapLogicalToScreen(labelX, labelY, &screenLabelX, &screenLabelY);
    g_canvas.setTextDatum(datum);
    g_canvas.setFont(&fonts::FreeSansBold12pt7b);
    g_canvas.setTextColor(kBlack);
    g_canvas.drawString(label, screenLabelX, screenLabelY);
}

}  // namespace

void begin() {
    auto cfg = M5.config();
    cfg.clear_display = true;
    cfg.fallback_board = m5::board_t::board_M5PaperS3;
    M5.begin(cfg);

    M5.Display.setRotation(1);
    M5.Display.setEpdMode(epd_mode_t::epd_quality);

    g_canvas.createSprite(M5.Display.width(), M5.Display.height());
    g_canvasReady = true;
}

void update() {
    M5.update();
}

int32_t displayWidth() {
    return M5.Display.width();
}

int32_t displayHeight() {
    return M5.Display.height();
}

PowerState readPower() {
    PowerState state;
    state.charging = M5.Power.isCharging();
    state.batteryPercent = M5.Power.getBatteryLevel();
    state.batteryMillivolts = M5.Power.getBatteryVoltage();
    // PaperS3 exposes charge status, not a separate VBUS-present reading.
    state.usbPresent = state.charging;
    return state;
}

bool touchReady() {
    return M5.Touch.isEnabled();
}

const char* touchMapName() {
    return touchMapNameFor(selectTouchMap());
}

TouchState readTouch() {
    TouchState state;
    state.ready = touchReady();
    state.count = M5.Touch.getCount();

    const auto detail = M5.Touch.getDetail();
    const auto raw = M5.Touch.getTouchPointRaw(0);
    state.pressed = detail.isPressed();
    if (detail.wasPressed()) {
        state.event = TouchState::Event::Down;
    } else if (detail.wasReleased()) {
        state.event = TouchState::Event::Up;
    } else if (state.pressed) {
        state.event = TouchState::Event::Move;
    }

    state.rawX = raw.x;
    state.rawY = raw.y;
    state.screenX = detail.x;
    state.screenY = detail.y;
    mapScreenToLogical(state.screenX, state.screenY, &state.x, &state.y);
    return state;
}

void clearDisplay() {
    if (!g_canvasReady) return;
    g_canvas.fillSprite(kWhite);
    g_canvas.pushSprite(0, 0);
}

void paintTestScreen(const char* firmwareVersion, const char* ipAddress) {
    if (!g_canvasReady) return;

    const int32_t w = g_canvas.width();
    const int32_t h = g_canvas.height();
    const PowerState power = readPower();

    g_canvas.fillSprite(kWhite);
    g_canvas.fillRect(0, 0, w, 86, kBlack);
    g_canvas.setTextColor(kWhite);
    g_canvas.setTextDatum(middle_left);
    g_canvas.setFont(&fonts::FreeSansBold18pt7b);
    g_canvas.drawString("AI Desk Card", 32, 36);

    g_canvas.setFont(&fonts::FreeSans9pt7b);
    g_canvas.setTextDatum(top_right);
    g_canvas.drawString("PaperS3 bring-up", w - 32, 24);
    g_canvas.drawString("BLE off / sleep off", w - 32, 50);

    g_canvas.setTextDatum(top_left);
    g_canvas.setTextColor(kBlack);
    g_canvas.setFont(&fonts::FreeSansBold18pt7b);
    g_canvas.drawString(kDeviceName, 32, 126);

    char panelLine[48];
    snprintf(panelLine, sizeof(panelLine), "%ld x %ld",
             (long)displayWidth(), (long)displayHeight());

    char batteryLine[64];
    snprintf(batteryLine, sizeof(batteryLine), "%ld%% / %d mV",
             (long)power.batteryPercent, (int)power.batteryMillivolts);

    char usbLine[64];
    snprintf(usbLine, sizeof(usbLine), "USB inferred %s, charging %s",
             power.usbPresent ? "present" : "absent",
             power.charging ? "yes" : "no");

    const int32_t top = 202;
    const int32_t colW = (w - 96) / 2;
    drawLabelValue("Firmware", firmwareVersion, 40, top);
    drawLabelValue("IP address", ipAddress, 40 + colW + 32, top);
    drawLabelValue("Panel", panelLine, 40, top + 96);
    drawLabelValue("Power", batteryLine, 40 + colW + 32, top + 96);

    g_canvas.drawLine(40, h - 112, w - 40, h - 112, kMidGray);
    g_canvas.setFont(&fonts::FreeSans9pt7b);
    g_canvas.setTextColor(kDarkGray);
    g_canvas.setTextDatum(top_left);
    g_canvas.drawString(usbLine, 40, h - 88);
    g_canvas.drawString("Waiting for daemon integration in a later phase.", 40, h - 58);

    g_canvas.fillRect(40, h - 22, w - 80, 4, kLightGray);
    g_canvas.pushSprite(0, 0);
}

void paintTouchCalibrationScreen(const char* firmwareVersion) {
    if (!g_canvasReady) return;

    const int32_t w = g_canvas.width();
    const int32_t h = g_canvas.height();

    g_canvas.fillSprite(kWhite);
    g_canvas.drawRect(0, 0, w, h, kBlack);

    g_canvas.setTextDatum(top_center);
    g_canvas.setFont(&fonts::FreeSansBold18pt7b);
    g_canvas.setTextColor(kBlack);
    g_canvas.drawString("PaperS3 Touch Test", w / 2, 24);

    g_canvas.setFont(&fonts::FreeSans9pt7b);
    char line[96];
    snprintf(line, sizeof(line), "fw %s  map %s  logical 540x960",
             firmwareVersion, touchMapName());
    g_canvas.drawString(line, w / 2, 66);

    int32_t x0 = 0;
    int32_t y0 = 0;
    int32_t x1 = 0;
    int32_t y1 = 0;
    mapLogicalToScreen(0, 0, &x0, &y0);
    mapLogicalToScreen(kLogicalFrameWidth - 1, 0, &x1, &y1);
    g_canvas.drawLine(x0, y0, x1, y1, kMidGray);
    mapLogicalToScreen(kLogicalFrameWidth - 1, kLogicalFrameHeight - 1, &x0, &y0);
    g_canvas.drawLine(x1, y1, x0, y0, kMidGray);
    mapLogicalToScreen(0, kLogicalFrameHeight - 1, &x1, &y1);
    g_canvas.drawLine(x0, y0, x1, y1, kMidGray);
    mapLogicalToScreen(0, 0, &x0, &y0);
    g_canvas.drawLine(x1, y1, x0, y0, kMidGray);

    drawLogicalTarget("TOP LEFT", 0, 0, 24, 28, top_left);
    drawLogicalTarget("TOP RIGHT", kLogicalFrameWidth - 1, 0,
                      kLogicalFrameWidth - 25, 28, top_right);
    drawLogicalTarget("CENTER", kLogicalFrameWidth / 2, kLogicalFrameHeight / 2,
                      kLogicalFrameWidth / 2, kLogicalFrameHeight / 2 + 32,
                      top_center);
    drawLogicalTarget("BOTTOM LEFT", 0, kLogicalFrameHeight - 1,
                      24, kLogicalFrameHeight - 28, bottom_left);
    drawLogicalTarget("BOTTOM RIGHT", kLogicalFrameWidth - 1,
                      kLogicalFrameHeight - 1,
                      kLogicalFrameWidth - 25, kLogicalFrameHeight - 28,
                      bottom_right);

    g_canvas.pushSprite(0, 0);
}

bool draw4bppFrame(const uint8_t* packed, int32_t width, int32_t height) {
    if (!g_canvasReady || !packed) {
        Serial.println("[display] error: canvas not ready or frame buffer null");
        return false;
    }
    if (width <= 0 || height <= 0) {
        Serial.printf("[display] error: invalid logical frame %ldx%ld\n",
                      (long)width, (long)height);
        return false;
    }

    const FrameMap map = selectFrameMap(width, height);
    if (map == FrameMap::kUnsupported) {
        Serial.printf("[display] error: cannot map logical=%ldx%ld to panel=%ldx%ld\n",
                      (long)width, (long)height,
                      (long)g_canvas.width(), (long)g_canvas.height());
        return false;
    }

    const uint32_t startMs = millis();
    Serial.printf("[display] update start logical=%ldx%ld panel=%ldx%ld map=%s epd=quality\n",
                  (long)width, (long)height,
                  (long)g_canvas.width(), (long)g_canvas.height(),
                  frameMapName(map));

    const size_t rowBytes = (size_t)(width + 1) / 2;
    for (int32_t y = 0; y < height; ++y) {
        const size_t row = (size_t)y * rowBytes;
        for (int32_t x = 0; x < width; x += 2) {
            const uint8_t b = packed[row + (size_t)x / 2];
            const uint16_t c0 = gray4ToRgb565(b >> 4);
            const uint16_t c1 = gray4ToRgb565(b & 0x0F);

            if (map == FrameMap::kDirect) {
                g_canvas.drawPixel(x, y, c0);
                if (x + 1 < width) g_canvas.drawPixel(x + 1, y, c1);
            } else {
                g_canvas.drawPixel(y, width - 1 - x, c0);
                if (x + 1 < width) g_canvas.drawPixel(y, width - 2 - x, c1);
            }
        }
    }

    g_canvas.pushSprite(0, 0);
    Serial.printf("[display] update end ms=%lu\n",
                  (unsigned long)(millis() - startMs));
    return true;
}

}  // namespace paper_s3
