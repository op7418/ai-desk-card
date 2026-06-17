#include "paper_s3_frame_receiver.h"

#include "paper_s3_hw.h"

#include <mbedtls/base64.h>

namespace paper_s3_frame {
namespace {

uint8_t* g_frameBuf = nullptr;
uint32_t g_frameId = 0;
uint32_t g_chunksExpected = 0;
uint32_t g_chunksReceived = 0;
uint32_t g_crcExpected = 0;
uint32_t g_frameOffset = 0;
bool g_frameInProgress = false;
bool g_rawMode = false;
const char* g_state = "idle";

uint32_t crc32Calc(const uint8_t* data, size_t len) {
    uint32_t crc = 0xFFFFFFFF;
    for (size_t i = 0; i < len; ++i) {
        crc ^= data[i];
        for (int k = 0; k < 8; ++k) {
            crc = (crc >> 1) ^ (0xEDB88320u & -(int32_t)(crc & 1));
        }
    }
    return ~crc;
}

void abortFrame(const char* reason) {
    Serial.printf("[frame] error: %s\n", reason);
    g_frameInProgress = false;
    g_rawMode = false;
    g_state = reason;
}

bool validateBegin(JsonDocument& doc) {
    const int w = doc["w"] | 0;
    const int h = doc["h"] | 0;
    const int bpp = doc["bpp"] | 0;
    if (w != kFrameWidth || h != kFrameHeight || bpp != 4) {
        Serial.printf("[frame] error: unsupported frame w=%d h=%d bpp=%d expected=%dx%d bpp=4\n",
                      w, h, bpp, kFrameWidth, kFrameHeight);
        g_state = "unsupported-format";
        return false;
    }
    return true;
}

uint32_t readU32(JsonVariantConst value) {
    return value.is<uint32_t>() ? value.as<uint32_t>() : 0;
}

void finishFrame() {
    if (g_crcExpected != 0) {
        const uint32_t got = crc32Calc(g_frameBuf, g_frameOffset);
        if (got != g_crcExpected) {
            Serial.printf("[frame] error: crc mismatch got=%08x expected=%08x\n",
                          (unsigned)got, (unsigned)g_crcExpected);
            abortFrame("crc-mismatch");
            return;
        }
    }

    Serial.printf("[frame] end fid=%u bytes=%u\n",
                  (unsigned)g_frameId, (unsigned)g_frameOffset);
    Serial.printf("[frame] decoded width=%d height=%d format=4bpp\n",
                  kFrameWidth, kFrameHeight);
    Serial.printf("{\"ack\":\"frame_raw_end\",\"fid\":%u,\"bytes\":%u}\n",
                  (unsigned)g_frameId, (unsigned)g_frameOffset);

    const bool ok = paper_s3::draw4bppFrame(g_frameBuf, kFrameWidth, kFrameHeight);
    g_frameInProgress = false;
    g_rawMode = false;
    g_state = ok ? "displayed" : "display-error";
}

}  // namespace

bool begin() {
    g_frameBuf = (uint8_t*)ps_malloc(kFrameBytes4bpp);
    if (!g_frameBuf) {
        Serial.printf("[frame] error: PSRAM alloc failed bytes=%u\n",
                      (unsigned)kFrameBytes4bpp);
        g_state = "alloc-failed";
        return false;
    }
    memset(g_frameBuf, 0, kFrameBytes4bpp);
    g_state = "ready";
    Serial.printf("[frame] PSRAM buffer ready bytes=%u at=%p\n",
                  (unsigned)kFrameBytes4bpp, g_frameBuf);
    Serial.println("[transport] serial frame stream active");
    return true;
}

const char* stateName() {
    return g_state;
}

bool isReceiving() {
    return g_frameInProgress;
}

bool wantsRawBytes() {
    return g_frameInProgress && g_rawMode;
}

void appendRawBytes(const uint8_t* data, size_t len) {
    if (!wantsRawBytes() || !g_frameBuf || !data || len == 0) return;
    if ((size_t)g_frameOffset + len > kFrameBytes4bpp) {
        abortFrame("raw-overrun");
        return;
    }
    memcpy(g_frameBuf + g_frameOffset, data, len);
    g_frameOffset += (uint32_t)len;
    if (g_frameOffset == len || (g_frameOffset % 32768) < len ||
        g_frameOffset == kFrameBytes4bpp) {
        Serial.printf("[frame] raw bytes %u/%u\n",
                      (unsigned)g_frameOffset,
                      (unsigned)kFrameBytes4bpp);
    }
    if (g_frameOffset == kFrameBytes4bpp) {
        finishFrame();
    }
}

bool drawHttpFrame(const uint8_t* data, size_t len, uint32_t fid, uint32_t crc) {
    if (!data) {
        abortFrame("http-null-frame");
        return false;
    }
    if (len != kFrameBytes4bpp) {
        Serial.printf("[frame] error: http size mismatch got=%u expected=%u\n",
                      (unsigned)len, (unsigned)kFrameBytes4bpp);
        g_state = "http-size-mismatch";
        return false;
    }

    g_frameInProgress = true;
    g_rawMode = false;
    g_state = "receiving-http";
    Serial.printf("[frame] http start fid=%u w=%d h=%d bpp=4 bytes=%u crc=%08x\n",
                  (unsigned)fid, kFrameWidth, kFrameHeight,
                  (unsigned)len, (unsigned)crc);
    if (crc != 0) {
        const uint32_t got = crc32Calc(data, len);
        if (got != crc) {
            Serial.printf("[frame] error: http crc mismatch got=%08x expected=%08x\n",
                          (unsigned)got, (unsigned)crc);
            abortFrame("http-crc-mismatch");
            return false;
        }
    }

    const bool ok = paper_s3::draw4bppFrame(data, kFrameWidth, kFrameHeight);
    g_frameInProgress = false;
    g_state = ok ? "displayed" : "display-error";
    Serial.printf("[frame] http complete fid=%u bytes=%u result=%s\n",
                  (unsigned)fid, (unsigned)len, ok ? "ok" : "display-error");
    return ok;
}

void setErrorState(const char* reason) {
    abortFrame(reason ? reason : "error");
}

bool handleCommand(JsonDocument& doc) {
    const char* cmd = doc["cmd"];
    if (!cmd) return false;

    if (strcmp(cmd, "frame_region_begin") == 0) {
        Serial.println("[frame] error: region update unsupported on paper-s3 phase 2");
        g_state = "region-unsupported";
        return true;
    }

    if (strcmp(cmd, "frame_raw_begin") == 0) {
        if (!g_frameBuf) {
            Serial.println("[frame] error: raw begin without frame buffer");
            g_state = "no-buffer";
            return true;
        }
        if (!validateBegin(doc)) return true;
        const uint32_t byteCount = readU32(doc["bytes"]);
        if (byteCount != kFrameBytes4bpp) {
            Serial.printf("[frame] error: raw size mismatch got=%u expected=%u\n",
                          (unsigned)byteCount,
                          (unsigned)kFrameBytes4bpp);
            g_state = "raw-size-mismatch";
            return true;
        }

        g_frameId = readU32(doc["fid"]);
        g_crcExpected = readU32(doc["crc"]);
        g_chunksExpected = 0;
        g_chunksReceived = 0;
        g_frameOffset = 0;
        g_frameInProgress = true;
        g_rawMode = true;
        g_state = "receiving-raw";

        Serial.printf("[frame] raw begin fid=%u w=%d h=%d bpp=4 bytes=%u crc=%08x\n",
                      (unsigned)g_frameId, kFrameWidth, kFrameHeight,
                      (unsigned)kFrameBytes4bpp,
                      (unsigned)g_crcExpected);
        Serial.printf("{\"ack\":\"frame_raw_begin\",\"fid\":%u,\"bytes\":0}\n",
                      (unsigned)g_frameId);
        return true;
    }

    if (strcmp(cmd, "frame_begin") == 0) {
        if (!g_frameBuf) {
            Serial.println("[frame] error: begin without frame buffer");
            g_state = "no-buffer";
            return true;
        }
        if (!validateBegin(doc)) return true;

        g_frameId = readU32(doc["fid"]);
        g_chunksExpected = readU32(doc["chunks"]);
        g_crcExpected = readU32(doc["crc"]);
        g_chunksReceived = 0;
        g_frameOffset = 0;
        g_frameInProgress = true;
        g_rawMode = false;
        g_state = "receiving";

        Serial.printf("[frame] begin fid=%u w=%d h=%d bpp=4 chunks=%u crc=%08x\n",
                      (unsigned)g_frameId, kFrameWidth, kFrameHeight,
                      (unsigned)g_chunksExpected, (unsigned)g_crcExpected);
        return true;
    }

    if (strcmp(cmd, "frame_chunk") == 0) {
        if (!g_frameInProgress || !g_frameBuf) {
            Serial.println("[frame] error: chunk without active frame");
            return true;
        }
        const uint32_t fid = readU32(doc["fid"]);
        if (fid != g_frameId) {
            Serial.printf("[frame] error: chunk fid mismatch got=%u active=%u\n",
                          (unsigned)fid, (unsigned)g_frameId);
            return true;
        }
        const uint32_t seq = readU32(doc["seq"]);
        if (seq != g_chunksReceived) {
            Serial.printf("[frame] error: chunk seq mismatch got=%u expected=%u\n",
                          (unsigned)seq, (unsigned)g_chunksReceived);
            abortFrame("seq-mismatch");
            return true;
        }

        const char* b64 = doc["data"] | "";
        const size_t b64Len = strlen(b64);
        if (b64Len == 0) {
            Serial.println("[frame] error: empty chunk data");
            return true;
        }

        size_t decoded = 0;
        const int rc = mbedtls_base64_decode(
            g_frameBuf + g_frameOffset,
            kFrameBytes4bpp - g_frameOffset,
            &decoded,
            (const unsigned char*)b64,
            b64Len);
        if (rc != 0) {
            Serial.printf("[frame] error: base64 decode rc=%d off=%u b64_len=%u\n",
                          rc, (unsigned)g_frameOffset, (unsigned)b64Len);
            abortFrame("decode-error");
            return true;
        }

        g_frameOffset += decoded;
        g_chunksReceived++;
        if (g_chunksReceived == 1 || (g_chunksReceived % 16) == 0 ||
            g_chunksReceived == g_chunksExpected) {
            Serial.printf("[frame] chunk %u/%u bytes=%u\n",
                          (unsigned)g_chunksReceived,
                          (unsigned)g_chunksExpected,
                          (unsigned)g_frameOffset);
        }
        Serial.printf("{\"ack\":\"frame_chunk\",\"fid\":%u,\"seq\":%u,\"bytes\":%u}\n",
                      (unsigned)g_frameId,
                      (unsigned)seq,
                      (unsigned)g_frameOffset);
        return true;
    }

    if (strcmp(cmd, "frame_end") == 0) {
        if (!g_frameInProgress || !g_frameBuf) {
            Serial.println("[frame] error: end without active frame");
            return true;
        }
        const uint32_t fid = readU32(doc["fid"]);
        if (fid != g_frameId) {
            Serial.printf("[frame] error: end fid mismatch got=%u active=%u\n",
                          (unsigned)fid, (unsigned)g_frameId);
            abortFrame("fid-mismatch");
            return true;
        }
        if (g_chunksReceived != g_chunksExpected) {
            Serial.printf("[frame] error: chunk count mismatch got=%u expected=%u\n",
                          (unsigned)g_chunksReceived,
                          (unsigned)g_chunksExpected);
            abortFrame("chunk-count-mismatch");
            return true;
        }
        if (g_frameOffset != kFrameBytes4bpp) {
            Serial.printf("[frame] error: size mismatch got=%u expected=%u\n",
                          (unsigned)g_frameOffset,
                          (unsigned)kFrameBytes4bpp);
            abortFrame("size-mismatch");
            return true;
        }
        Serial.printf("[frame] chunks complete fid=%u chunks=%u\n",
                      (unsigned)fid, (unsigned)g_chunksReceived);
        finishFrame();
        return true;
    }

    return false;
}

}  // namespace paper_s3_frame
