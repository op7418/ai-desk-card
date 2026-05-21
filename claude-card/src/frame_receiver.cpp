#include "frame_receiver.h"
#include "mbedtls/base64.h"

namespace {

// PSRAM-allocated. 259 KB.
uint8_t* g_frame_buf = nullptr;
uint32_t g_frame_offset = 0;

uint32_t g_frame_id_active   = 0;   // current frame we're assembling
uint32_t g_chunks_expected   = 0;
uint32_t g_chunks_received   = 0;
uint32_t g_crc_expected      = 0;
bool     g_frame_in_progress = false;

// v0.7 region updates: when true, the current frame is a partial region.
// Coordinates + size describe where this region lives on the panel.
bool     g_is_region    = false;
uint16_t g_region_x     = 0;
uint16_t g_region_y     = 0;
uint16_t g_region_w     = FRAME_W;
uint16_t g_region_h     = FRAME_H;

// What we did last. Useful for the boot log.
const char* g_last_state = "idle";

// Very small CRC32 (no table) — only for end-of-frame sanity. ~4 ms per
// 260 KB frame, negligible. Could swap for the ESP32 hardware CRC unit if
// we ever care about that overhead.
uint32_t crc32_calc(const uint8_t* data, size_t len) {
    uint32_t crc = 0xFFFFFFFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int k = 0; k < 8; k++) {
            crc = (crc >> 1) ^ (0xEDB88320u & -(int32_t)(crc & 1));
        }
    }
    return ~crc;
}

}  // namespace

bool frameReceiverInit() {
    g_frame_buf = (uint8_t*)ps_malloc(FRAME_BYTES_4BPP);
    if (!g_frame_buf) {
        Serial.println("[frame] PSRAM alloc FAILED");
        g_last_state = "alloc-failed";
        return false;
    }
    memset(g_frame_buf, 0, FRAME_BYTES_4BPP);   // start clean white (0 = white)
    g_last_state = "ready";
    Serial.printf("[frame] PSRAM buffer ready: %u bytes at %p\n",
                  (unsigned)FRAME_BYTES_4BPP, g_frame_buf);
    return true;
}

const char* frameReceiverStateName() { return g_last_state; }

bool frameHandleCommand(JsonDocument& doc) {
    const char* cmd = doc["cmd"];
    if (!cmd) return false;

    if (strcmp(cmd, "frame_begin") == 0) {
        if (!g_frame_buf) {
            Serial.println("[frame] begin without buf");
            return true;
        }
        g_frame_id_active = doc["fid"] | 0;
        g_chunks_expected = doc["chunks"] | 0;
        g_chunks_received = 0;
        g_crc_expected    = doc["crc"] | 0;
        g_frame_offset    = 0;
        g_frame_in_progress = true;
        g_is_region       = false;
        g_region_x = 0; g_region_y = 0;
        g_region_w = FRAME_W; g_region_h = FRAME_H;
        g_last_state = "receiving";
        Serial.printf("[frame] begin fid=%u chunks=%u crc=%08x\n",
                      (unsigned)g_frame_id_active,
                      (unsigned)g_chunks_expected,
                      (unsigned)g_crc_expected);
        return true;
    }

    if (strcmp(cmd, "frame_region_begin") == 0) {
        // v0.7: partial update — same buffer, but only the region's worth
        // of pixels arrive in chunks, and the e-ink update at the end
        // covers just (x, y, w, h).
        if (!g_frame_buf) {
            Serial.println("[frame] region_begin without buf");
            return true;
        }
        g_frame_id_active = doc["fid"] | 0;
        g_chunks_expected = doc["chunks"] | 0;
        g_chunks_received = 0;
        g_crc_expected    = doc["crc"] | 0;
        g_frame_offset    = 0;
        g_region_x        = doc["x"] | 0;
        g_region_y        = doc["y"] | 0;
        g_region_w        = doc["w"] | FRAME_W;
        g_region_h        = doc["h"] | FRAME_H;
        g_frame_in_progress = true;
        g_is_region       = true;
        g_last_state = "receiving-region";
        Serial.printf("[frame] region begin fid=%u (%u,%u %ux%u) chunks=%u crc=%08x\n",
                      (unsigned)g_frame_id_active,
                      (unsigned)g_region_x, (unsigned)g_region_y,
                      (unsigned)g_region_w, (unsigned)g_region_h,
                      (unsigned)g_chunks_expected,
                      (unsigned)g_crc_expected);
        return true;
    }

    if (strcmp(cmd, "frame_chunk") == 0) {
        if (!g_frame_in_progress || !g_frame_buf) return true;
        uint32_t fid = doc["fid"] | 0;
        if (fid != g_frame_id_active) {
            Serial.printf("[frame] chunk fid mismatch %u vs %u, drop\n",
                          (unsigned)fid, (unsigned)g_frame_id_active);
            return true;
        }
        const char* b64 = doc["data"] | "";
        size_t b64_len = strlen(b64);
        if (b64_len == 0) return true;

        // Decoded size = ~3/4 of base64 input. Don't pre-check against
        // encoded length (that was the v0.6 bug — last chunk's b64_len of
        // 1536 looked like "overrun" but decoded to 1152 which fit exactly).
        // mbedtls fills `decoded` with actual byte count; we trust that
        // and only sanity-check against buffer end.
        size_t decoded = 0;
        int rc = mbedtls_base64_decode(
            g_frame_buf + g_frame_offset,
            FRAME_BYTES_4BPP - g_frame_offset,
            &decoded,
            (const unsigned char*)b64,
            b64_len);
        if (rc != 0) {
            Serial.printf("[frame] base64 decode err %d (off=%u b64_len=%u)\n",
                          rc, (unsigned)g_frame_offset, (unsigned)b64_len);
            g_frame_in_progress = false;
            g_last_state = "decode-err";
            return true;
        }
        g_frame_offset += decoded;
        g_chunks_received++;
        return true;
    }

    if (strcmp(cmd, "frame_end") == 0) {
        if (!g_frame_in_progress || !g_frame_buf) return true;
        uint32_t fid = doc["fid"] | 0;
        if (fid != g_frame_id_active) {
            Serial.printf("[frame] end fid mismatch\n");
            g_frame_in_progress = false;
            return true;
        }
        // CRC check (optional — if daemon set crc=0, skip).
        if (g_crc_expected != 0) {
            uint32_t got = crc32_calc(g_frame_buf, g_frame_offset);
            if (got != g_crc_expected) {
                Serial.printf("[frame] CRC mismatch: got %08x expected %08x  "
                              "(received %u of %u chunks, %u bytes)\n",
                              (unsigned)got, (unsigned)g_crc_expected,
                              (unsigned)g_chunks_received,
                              (unsigned)g_chunks_expected,
                              (unsigned)g_frame_offset);
                g_frame_in_progress = false;
                g_last_state = "crc-fail";
                return true;
            }
        }
        size_t expected_bytes = g_is_region
            ? (size_t)g_region_w * g_region_h / 2
            : FRAME_BYTES_4BPP;
        if (g_frame_offset != expected_bytes) {
            Serial.printf("[frame] size mismatch: got %u, expected %u (%s)\n",
                          (unsigned)g_frame_offset, (unsigned)expected_bytes,
                          g_is_region ? "region" : "full");
            // continue anyway — better partial than nothing
        }

        if (g_is_region) {
            Serial.printf("[frame] end fid=%u OK region (%u,%u %ux%u) "
                          "%u bytes %u chunks — pushing\n",
                          (unsigned)fid,
                          (unsigned)g_region_x, (unsigned)g_region_y,
                          (unsigned)g_region_w, (unsigned)g_region_h,
                          (unsigned)g_frame_offset,
                          (unsigned)g_chunks_received);
            M5.EPD.WritePartGram4bpp(g_region_x, g_region_y,
                                     g_region_w, g_region_h, g_frame_buf);
            M5.EPD.UpdateArea(g_region_x, g_region_y, g_region_w, g_region_h,
                              UPDATE_MODE_GC16);
        } else {
            Serial.printf("[frame] end fid=%u OK (%u bytes %u chunks) — pushing\n",
                          (unsigned)fid, (unsigned)g_frame_offset,
                          (unsigned)g_chunks_received);
            M5.EPD.WritePartGram4bpp(0, 0, FRAME_W, FRAME_H, g_frame_buf);
            M5.EPD.UpdateFull(UPDATE_MODE_GC16);
        }
        g_frame_in_progress = false;
        g_last_state = "displayed";
        return true;
    }

    return false;
}
