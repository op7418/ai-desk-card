// Frame buffer for Paper Color. Receives RGB565 pixel buffers from
// the HTTP /frame endpoint and draws them through M5Canvas. M5GFX
// quantizes RGB565 → Spectra 6 palette automatically when the panel
// is in epd_fastest mode (~15 s for a full refresh).

#include <Arduino.h>
#include <M5Unified.h>

// Defined in main.cpp.
extern M5Canvas canvas;

bool frameAcceptRGB565(int x, int y, int w, int h,
                       const uint8_t* data, size_t len) {
    if (!data || len != (size_t)w * h * 2) {
        Serial.printf("[frame] reject: len=%u expected=%u (w=%d h=%d)\n",
                      (unsigned)len, (unsigned)((size_t)w * h * 2), w, h);
        return false;
    }

    // pushImage interprets data as the canvas color depth; for our
    // M5Canvas (created from M5.Display) the natural depth is rgb565.
    canvas.pushImage(x, y, w, h, (uint16_t*)data);

    Serial.printf("[frame] received %d x %d at (%d,%d), %u bytes — pushing\n",
                  w, h, x, y, (unsigned)len);
    uint32_t t0 = millis();
    canvas.pushSprite(0, 0);
    Serial.printf("[frame] panel push %lu ms\n",
                  (unsigned long)(millis() - t0));
    return true;
}
