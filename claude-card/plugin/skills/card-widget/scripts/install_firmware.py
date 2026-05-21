#!/usr/bin/env python3
"""claude-card firmware OTA installer.

Modes:
  --detect   Print current firmware version on the connected card (parses
             [boot] m5-paper-buddy vXX or [boot] claude-card vXX lines).
  --flash    Flash a card firmware binary. By default uses the local build
             at ../../../.pio/build/card/firmware.bin (relative to this
             script). With --url, downloads from a release URL after sha256
             verification.

Trust model (per PLAN.md):
  - Auto-download requires explicit --url
  - sha256 ALWAYS verified before flash
  - Interactive confirmation required (skip with --yes)

Usage:
    install_firmware.py --detect
    install_firmware.py --flash --yes           # local build
    install_firmware.py --flash --url ... --sha256 ... --yes  # cloud
"""
from __future__ import annotations
import argparse, hashlib, os, subprocess, sys, time, urllib.request

LOCAL_BIN = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "..", "..", "..", ".pio", "build", "card", "firmware.bin")


def detect_port() -> str | None:
    import glob
    ports = sorted(glob.glob("/dev/cu.usbserial-*") + glob.glob("/dev/ttyUSB*"))
    return ports[0] if ports else None


def detect_version(port: str | None = None) -> str:
    """Open serial, capture 5 s, parse [boot] vX.X lines."""
    port = port or detect_port()
    if not port: return "unknown (no /dev/cu.usbserial-* found)"
    try:
        sys.path.insert(0, "/opt/homebrew/Cellar/platformio/6.1.19_1/libexec/lib/python3.14/site-packages")
        import serial
    except ImportError:
        return "unknown (install pyserial)"
    try:
        s = serial.Serial(port, 115200, timeout=0.3)
        s.setDTR(False); s.setRTS(True); time.sleep(0.1)
        s.setDTR(False); s.setRTS(False); time.sleep(0.05)
        s.reset_input_buffer()
        end = time.time() + 5
        buf = bytearray()
        while time.time() < end:
            n = s.in_waiting
            if n: buf.extend(s.read(n))
            time.sleep(0.05)
        txt = buf.decode("utf-8", errors="replace")
        for line in txt.splitlines():
            if "[boot]" in line and ("claude-card" in line or "m5-paper-buddy" in line):
                return line.strip()
        return "unknown (no [boot] line within 5 s)"
    except Exception as e:
        return f"unknown (serial: {e!r})"


def download(url: str, expected_sha: str) -> str:
    out = "/tmp/claude_card_firmware.bin"
    print(f"[ota] downloading {url}", file=sys.stderr)
    urllib.request.urlretrieve(url, out)
    with open(out, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    if sha != expected_sha:
        sys.exit(f"sha256 mismatch: got {sha}, expected {expected_sha}")
    print(f"[ota] sha256 ok: {sha}", file=sys.stderr)
    return out


def flash(bin_path: str, port: str | None = None):
    port = port or detect_port()
    if not port: sys.exit("no device port detected")
    print(f"[ota] flashing {bin_path} → {port}", file=sys.stderr)
    subprocess.check_call([
        "esptool.py", "--chip", "esp32", "--port", port, "--baud", "921600",
        "--before", "default_reset", "--after", "hard_reset",
        "write_flash", "-z", "--flash_mode", "dio", "--flash_freq", "80m",
        "--flash_size", "16MB", "0x10000", bin_path,
    ])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--detect", action="store_true")
    ap.add_argument("--flash",  action="store_true")
    ap.add_argument("--url",    help="firmware bin URL (otherwise uses local build)")
    ap.add_argument("--sha256", help="expected sha256 of the downloaded bin")
    ap.add_argument("--port")
    ap.add_argument("--yes",    action="store_true", help="skip interactive confirm")
    args = ap.parse_args()

    if args.detect or (not args.flash):
        print(detect_version(args.port))
        if not args.flash: return 0

    if args.flash:
        if args.url:
            if not args.sha256: sys.exit("--url requires --sha256")
            bin_path = download(args.url, args.sha256)
        else:
            bin_path = os.path.abspath(LOCAL_BIN)
            if not os.path.exists(bin_path):
                sys.exit(f"local bin missing: {bin_path}. run `pio run -e card` first.")
        if not args.yes:
            print(f"\nabout to flash: {bin_path}\nport: {args.port or detect_port()}\n")
            ans = input("proceed? [y/N] ")
            if ans.strip().lower() != "y": sys.exit("aborted")
        flash(bin_path, args.port)
        print("[ota] done. device booting…", file=sys.stderr)
    return 0


if __name__ == "__main__": sys.exit(main())
