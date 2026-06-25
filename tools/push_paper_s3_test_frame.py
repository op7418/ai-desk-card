#!/usr/bin/env python3
"""Send a 540x960 packed 4bpp grayscale test frame to PaperS3 over USB CDC."""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import threading
import time


FRAME_W = 540
FRAME_H = 960
FRAME_BYTES = FRAME_W * FRAME_H // 2
DEFAULT_CHUNK_SIZE = 256
DEFAULT_READY_TIMEOUT = 20.0
DEFAULT_INTER_CHUNK_DELAY = 0.05
DEFAULT_ACK_TIMEOUT = 5.0
DEFAULT_MODE = "raw"
DEFAULT_RAW_WRITE_SIZE = 512
DEFAULT_RAW_WRITE_DELAY = 0.005


FONT_5X7 = {
    " ": ["00000", "00000", "00000", "00000", "00000", "00000", "00000"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01111", "10000", "10000", "10111", "10001", "10001", "01110"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
}


def _fill_rect(pixels: bytearray, width: int, height: int,
               x: int, y: int, w: int, h: int, value: int) -> None:
    x0 = max(0, x)
    y0 = max(0, y)
    x1 = min(width, x + w)
    y1 = min(height, y + h)
    if x0 >= x1 or y0 >= y1:
        return
    for yy in range(y0, y1):
        row = yy * width
        pixels[row + x0:row + x1] = bytes([value]) * (x1 - x0)


def _draw_text(pixels: bytearray, width: int, height: int,
               x: int, y: int, text: str, scale: int, value: int) -> None:
    cursor = x
    for ch in text.upper():
        glyph = FONT_5X7.get(ch, FONT_5X7[" "])
        for gy, row in enumerate(glyph):
            for gx, bit in enumerate(row):
                if bit == "1":
                    _fill_rect(
                        pixels, width, height,
                        cursor + gx * scale, y + gy * scale,
                        scale, scale, value)
        cursor += 6 * scale


def _label_box(pixels: bytearray, width: int, height: int,
               text: str, x: int, y: int, scale: int = 5,
               anchor: str = "left") -> None:
    text_w = max(1, len(text)) * 6 * scale - scale
    text_h = 7 * scale
    pad = 10
    box_w = text_w + pad * 2
    box_h = text_h + pad * 2
    if anchor == "right":
        x -= box_w
    elif anchor == "center":
        x -= box_w // 2
        y -= box_h // 2

    _fill_rect(pixels, width, height, x, y, box_w, box_h, 255)
    _fill_rect(pixels, width, height, x, y, box_w, 3, 0)
    _fill_rect(pixels, width, height, x, y + box_h - 3, box_w, 3, 0)
    _fill_rect(pixels, width, height, x, y, 3, box_h, 0)
    _fill_rect(pixels, width, height, x + box_w - 3, y, 3, box_h, 0)
    _draw_text(pixels, width, height, x + pad, y + pad, text, scale, 0)


def make_test_pixels(width: int = FRAME_W, height: int = FRAME_H) -> bytes:
    pixels = bytearray(width * height)
    for y in range(height):
        grad = int(255 * y / max(1, height - 1))
        for x in range(width):
            checker = ((x // 54) ^ (y // 64)) & 1
            level = grad if checker else 255 - grad
            pixels[y * width + x] = level

    _fill_rect(pixels, width, height, 0, 0, width, 6, 0)
    _fill_rect(pixels, width, height, 0, height - 6, width, 6, 0)
    _fill_rect(pixels, width, height, 0, 0, 6, height, 0)
    _fill_rect(pixels, width, height, width - 6, 0, 6, height, 0)
    _fill_rect(pixels, width, height, width // 2 - 2, 0, 4, height, 80)
    _fill_rect(pixels, width, height, 0, height // 2 - 2, width, 4, 80)

    _label_box(pixels, width, height, "TOP LEFT", 18, 18)
    _label_box(pixels, width, height, "TOP RIGHT", width - 18, 18, anchor="right")
    _label_box(pixels, width, height, "BOTTOM LEFT", 18, height - 78)
    _label_box(pixels, width, height, "BOTTOM RIGHT", width - 18, height - 78, anchor="right")
    _label_box(pixels, width, height, "CENTER", width // 2, height // 2, anchor="center")
    return bytes(pixels)


def pack_luma_to_4bpp(width: int, height: int, pixels: bytes) -> bytes:
    if len(pixels) != width * height:
        raise ValueError(f"pixel buffer is {len(pixels)} bytes, expected {width * height}")

    packed_width = width if width % 2 == 0 else width + 1
    out = bytearray(packed_width * height // 2)
    out_i = 0
    for y in range(height):
        row = y * width
        for x in range(0, packed_width, 2):
            a = pixels[row + x] if x < width else 255
            b = pixels[row + x + 1] if x + 1 < width else 255
            na = (255 - a) >> 4
            nb = (255 - b) >> 4
            out[out_i] = (na << 4) | nb
            out_i += 1
    return bytes(out)


def iter_chunks(data: bytes, chunk_size: int = DEFAULT_CHUNK_SIZE):
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    for seq, start in enumerate(range(0, len(data), chunk_size)):
        yield seq, data[start:start + chunk_size]


def build_chunk_command(fid: int, seq: int, chunk: bytes) -> bytes:
    obj = {
        "cmd": "frame_chunk",
        "fid": fid,
        "seq": seq,
        "data": base64.b64encode(chunk).decode("ascii"),
    }
    return json.dumps(obj, separators=(",", ":")).encode("ascii") + b"\n"


def build_raw_begin_command(fid: int, byte_count: int, crc: int) -> bytes:
    obj = {
        "cmd": "frame_raw_begin",
        "fid": fid,
        "w": FRAME_W,
        "h": FRAME_H,
        "bpp": 4,
        "bytes": byte_count,
        "crc": crc,
    }
    return json.dumps(obj, separators=(",", ":")).encode("ascii") + b"\n"


def parse_status_line(line: str) -> dict | None:
    try:
        obj = json.loads(line.strip())
    except json.JSONDecodeError:
        return None
    if isinstance(obj, dict) and obj.get("ack") == "status":
        return obj
    return None


def parse_frame_chunk_ack(line: str, fid: int, seq: int) -> bool:
    try:
        obj = json.loads(line.strip())
    except json.JSONDecodeError:
        return False
    return (
        isinstance(obj, dict)
        and obj.get("ack") == "frame_chunk"
        and int(obj.get("fid", -1)) == fid
        and int(obj.get("seq", -1)) == seq
    )


def should_print_device_line(line: str, verbose_chunks: bool = False) -> bool:
    if verbose_chunks:
        return True
    if line == "[rx] cmd=frame_chunk":
        return False
    try:
        obj = json.loads(line.strip())
    except json.JSONDecodeError:
        return True
    return not (isinstance(obj, dict) and obj.get("ack") == "frame_chunk")


class AckTracker:
    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._seen: set[tuple[int, int]] = set()
        self._raw_begin: set[int] = set()
        self._raw_end: set[int] = set()

    def note_line(self, line: str) -> None:
        try:
            obj = json.loads(line.strip())
        except json.JSONDecodeError:
            return
        if not isinstance(obj, dict):
            return
        if obj.get("ack") == "frame_raw_begin":
            try:
                fid = int(obj["fid"])
            except (KeyError, TypeError, ValueError):
                return
            with self._condition:
                self._raw_begin.add(fid)
                self._condition.notify_all()
            return
        if obj.get("ack") == "frame_raw_end":
            try:
                fid = int(obj["fid"])
            except (KeyError, TypeError, ValueError):
                return
            with self._condition:
                self._raw_end.add(fid)
                self._condition.notify_all()
            return
        if obj.get("ack") != "frame_chunk":
            return
        try:
            key = (int(obj["fid"]), int(obj["seq"]))
        except (KeyError, TypeError, ValueError):
            return
        with self._condition:
            self._seen.add(key)
            self._condition.notify_all()

    def wait_for(self, fid: int, seq: int, timeout_s: float) -> bool:
        deadline = time.time() + timeout_s
        key = (fid, seq)
        with self._condition:
            while key not in self._seen:
                remaining = deadline - time.time()
                if remaining <= 0:
                    return False
                self._condition.wait(timeout=remaining)
            return True

    def wait_raw_begin(self, fid: int, timeout_s: float) -> bool:
        return self._wait_for_set(self._raw_begin, fid, timeout_s)

    def wait_raw_end(self, fid: int, timeout_s: float) -> bool:
        return self._wait_for_set(self._raw_end, fid, timeout_s)

    def _wait_for_set(self, values: set[int], fid: int, timeout_s: float) -> bool:
        deadline = time.time() + timeout_s
        with self._condition:
            while fid not in values:
                remaining = deadline - time.time()
                if remaining <= 0:
                    return False
                self._condition.wait(timeout=remaining)
            return True


def _open_serial_no_reset(port: str, baud: int):
    import serial

    ser = serial.Serial()
    ser.port = port
    ser.baudrate = baud
    ser.timeout = 0.2
    ser.write_timeout = 5
    ser.dtr = False
    ser.rts = False
    ser.open()
    ser.dtr = False
    ser.rts = False
    return ser


def _write_json_line(ser, obj: dict) -> None:
    line = json.dumps(obj, separators=(",", ":")).encode("ascii") + b"\n"
    ser.write(line)


def _read_device_lines(ser, stop_event: threading.Event,
                       ready_event: threading.Event,
                       ack_tracker: AckTracker,
                       verbose_chunks: bool) -> None:
    buf = bytearray()
    while not stop_event.is_set():
        chunk = ser.read(256)
        if not chunk:
            continue
        for b in chunk:
            if b in (10, 13):
                if buf:
                    line = buf.decode("utf-8", errors="replace")
                    if parse_status_line(line) is not None:
                        ready_event.set()
                    ack_tracker.note_line(line)
                    if should_print_device_line(line, verbose_chunks):
                        print(line)
                    buf.clear()
            else:
                buf.append(b)
    if buf:
        print(buf.decode("utf-8", errors="replace"))


def _wait_for_ready(ser, ready_event: threading.Event, timeout_s: float) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        _write_json_line(ser, {"cmd": "ping"})
        ser.flush()
        if ready_event.wait(timeout=1.0):
            return
    raise TimeoutError(
        f"no status ack from device within {timeout_s:.1f}s; "
        "check the port and make sure monitor is closed")


def send_test_frame(port: str, baud: int = 115200,
                    mode: str = DEFAULT_MODE,
                    chunk_size: int = DEFAULT_CHUNK_SIZE,
                    listen_after: float = 30.0,
                    ready_timeout: float = DEFAULT_READY_TIMEOUT,
                    inter_chunk_delay: float = DEFAULT_INTER_CHUNK_DELAY,
                    ack_timeout: float = DEFAULT_ACK_TIMEOUT,
                    verbose_chunks: bool = False,
                    raw_write_size: int = DEFAULT_RAW_WRITE_SIZE,
                    raw_write_delay: float = DEFAULT_RAW_WRITE_DELAY) -> None:
    pixels = make_test_pixels()
    packed = pack_luma_to_4bpp(FRAME_W, FRAME_H, pixels)
    chunks = list(iter_chunks(packed, chunk_size))
    crc = binascii.crc32(packed) & 0xFFFFFFFF
    fid = int(time.time()) & 0xFFFFFFFF

    print(f"[host] opening {port} @ {baud}")
    ser = _open_serial_no_reset(port, baud)
    stop_event = threading.Event()
    ready_event = threading.Event()
    ack_tracker = AckTracker()
    reader = threading.Thread(
        target=_read_device_lines,
        args=(ser, stop_event, ready_event, ack_tracker, verbose_chunks),
        daemon=True)
    reader.start()

    try:
        print(f"[host] waiting for device status ack up to {ready_timeout:.1f}s")
        _wait_for_ready(ser, ready_event, ready_timeout)

        if mode == "raw":
            print(
                f"[host] frame_raw_begin fid={fid} {FRAME_W}x{FRAME_H} "
                f"4bpp bytes={len(packed)} crc={crc:08x}")
            ser.write(build_raw_begin_command(fid, len(packed), crc))
            ser.flush()
            if not ack_tracker.wait_raw_begin(fid, ack_timeout):
                raise TimeoutError(
                    f"no frame_raw_begin ack within {ack_timeout:.1f}s")
            for start in range(0, len(packed), raw_write_size):
                ser.write(packed[start:start + raw_write_size])
                if raw_write_delay > 0:
                    time.sleep(raw_write_delay)
                sent = min(start + raw_write_size, len(packed))
                if sent == raw_write_size or sent % 32768 == 0 or sent == len(packed):
                    print(f"[host] raw bytes {sent}/{len(packed)}")
            ser.flush()
            if not ack_tracker.wait_raw_end(fid, max(ack_timeout, 30.0)):
                raise TimeoutError(
                    f"no frame_raw_end ack within {max(ack_timeout, 30.0):.1f}s")
        elif mode == "chunk":
            print(
                f"[host] frame_begin fid={fid} {FRAME_W}x{FRAME_H} "
                f"4bpp bytes={len(packed)} chunks={len(chunks)} crc={crc:08x}")
            _write_json_line(ser, {
                "cmd": "frame_begin",
                "fid": fid,
                "w": FRAME_W,
                "h": FRAME_H,
                "bpp": 4,
                "chunks": len(chunks),
                "crc": crc,
            })
            for seq, chunk in chunks:
                ser.write(build_chunk_command(fid, seq, chunk))
                if inter_chunk_delay > 0:
                    time.sleep(inter_chunk_delay)
                if not ack_tracker.wait_for(fid, seq, ack_timeout):
                    raise TimeoutError(
                        f"no frame_chunk ack for seq={seq} within {ack_timeout:.1f}s")
                if seq == 0 or (seq + 1) % 32 == 0 or seq + 1 == len(chunks):
                    sent = min((seq + 1) * chunk_size, len(packed))
                    print(f"[host] chunk {seq + 1}/{len(chunks)} bytes={sent}")
            _write_json_line(ser, {"cmd": "frame_end", "fid": fid})
            ser.flush()
        else:
            raise ValueError(f"unknown mode {mode!r}")

        print(f"[host] frame_end sent; listening {listen_after:.1f}s for device logs")
        time.sleep(listen_after)
    finally:
        stop_event.set()
        reader.join(timeout=1.0)
        ser.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="COM3")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--mode", choices=("raw", "chunk"), default=DEFAULT_MODE)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--listen-after", type=float, default=10.0)
    parser.add_argument("--ready-timeout", type=float, default=DEFAULT_READY_TIMEOUT)
    parser.add_argument("--inter-chunk-delay", type=float, default=DEFAULT_INTER_CHUNK_DELAY)
    parser.add_argument("--ack-timeout", type=float, default=DEFAULT_ACK_TIMEOUT)
    parser.add_argument("--verbose-chunks", action="store_true")
    parser.add_argument("--raw-write-size", type=int, default=DEFAULT_RAW_WRITE_SIZE)
    parser.add_argument("--raw-write-delay", type=float, default=DEFAULT_RAW_WRITE_DELAY)
    args = parser.parse_args()
    send_test_frame(
        args.port,
        args.baud,
        args.mode,
        args.chunk_size,
        args.listen_after,
        args.ready_timeout,
        args.inter_chunk_delay,
        args.ack_timeout,
        args.verbose_chunks,
        args.raw_write_size,
        args.raw_write_delay)


if __name__ == "__main__":
    main()
