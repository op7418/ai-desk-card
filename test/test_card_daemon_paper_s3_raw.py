import os
import sys
import json
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "daemon"))

import card_daemon


class FakeRawSerialTransport(card_daemon.SerialTransport):
    def __init__(self):
        self.json_lines = []
        self.raw_payload = bytearray()
        self.active_fid = None
        self.expected_bytes = None

    def write(self, data: bytes):
        if data.startswith(b"{") and data.rstrip().endswith(b"}"):
            self.json_lines.append(data)
            obj = json.loads(data.decode("utf-8").strip())
            if obj.get("cmd") == "frame_raw_begin":
                self.active_fid = obj["fid"]
                self.expected_bytes = obj["bytes"]
                self._emit({"ack": "frame_raw_begin", "fid": self.active_fid, "bytes": 0})
            return

        self.raw_payload.extend(data)
        if self.expected_bytes is not None and len(self.raw_payload) >= self.expected_bytes:
            self._emit({
                "ack": "frame_raw_end",
                "fid": self.active_fid,
                "bytes": len(self.raw_payload),
            })

    def connected(self):
        return True

    def _emit(self, obj: dict):
        line = json.dumps(obj, separators=(",", ":"))
        with card_daemon._RX_LISTENERS_LOCK:
            listeners = list(card_daemon._RX_LISTENERS)
        for fn in listeners:
            fn(line)


class CardDaemonPaperS3RawTest(unittest.TestCase):
    def setUp(self):
        self.old_transport = card_daemon.TRANSPORT
        self.old_write_size = card_daemon.SERIAL_RAW_WRITE_SIZE
        self.old_write_delay = card_daemon.SERIAL_RAW_WRITE_DELAY_S
        self.old_begin_timeout = card_daemon.SERIAL_RAW_BEGIN_TIMEOUT_S
        self.old_end_timeout = card_daemon.SERIAL_RAW_END_TIMEOUT_S
        card_daemon.DEVICE_TELEMETRY.clear()
        card_daemon._FRAME_ID = 0
        with card_daemon._RX_LISTENERS_LOCK:
            card_daemon._RX_LISTENERS.clear()

    def tearDown(self):
        card_daemon.TRANSPORT = self.old_transport
        card_daemon.SERIAL_RAW_WRITE_SIZE = self.old_write_size
        card_daemon.SERIAL_RAW_WRITE_DELAY_S = self.old_write_delay
        card_daemon.SERIAL_RAW_BEGIN_TIMEOUT_S = self.old_begin_timeout
        card_daemon.SERIAL_RAW_END_TIMEOUT_S = self.old_end_timeout
        with card_daemon._RX_LISTENERS_LOCK:
            card_daemon._RX_LISTENERS.clear()

    def test_telemetry_records_paper_s3_frame_capability_fields(self):
        card_daemon._telemetry_listener(
            '{"ack":"status","device":"M5Stack PaperS3",'
            '"fw":"0.10.7-paper-s3-frame","frame_state":"ready"}'
        )

        self.assertEqual(card_daemon.DEVICE_TELEMETRY["device"], "M5Stack PaperS3")
        self.assertEqual(card_daemon.DEVICE_TELEMETRY["firmware"], "0.10.7-paper-s3-frame")
        self.assertEqual(card_daemon.DEVICE_TELEMETRY["frame_state"], "ready")
        self.assertTrue(card_daemon._paper_s3_raw_frame_supported())

    def test_raw_frame_support_does_not_match_m5paper_v11(self):
        card_daemon.DEVICE_TELEMETRY["firmware"] = "0.10.1"

        self.assertFalse(card_daemon._paper_s3_raw_frame_supported())

    def test_frame_raw_begin_command_shape(self):
        cmd = card_daemon._frame_raw_begin_command(123, 259200, 0xDEC1FC92)

        self.assertEqual(cmd["cmd"], "frame_raw_begin")
        self.assertEqual(cmd["fid"], 123)
        self.assertEqual(cmd["w"], 540)
        self.assertEqual(cmd["h"], 960)
        self.assertEqual(cmd["bpp"], 4)
        self.assertEqual(cmd["bytes"], 259200)
        self.assertEqual(cmd["crc"], 0xDEC1FC92)

    def test_daemon_cache_paths_use_existing_temp_directory(self):
        widget_path = card_daemon._daemon_cache_path("widget_cache.json")

        self.assertEqual(os.path.dirname(widget_path), tempfile.gettempdir())
        self.assertTrue(os.path.isdir(os.path.dirname(widget_path)))

    def test_push_frame_bytes_uses_raw_serial_for_paper_s3_full_frame(self):
        fake = FakeRawSerialTransport()
        card_daemon.TRANSPORT = fake
        card_daemon.DEVICE_TELEMETRY["firmware"] = "0.10.7-paper-s3-frame"
        card_daemon.SERIAL_RAW_WRITE_SIZE = 65536
        card_daemon.SERIAL_RAW_WRITE_DELAY_S = 0.0
        card_daemon.SERIAL_RAW_BEGIN_TIMEOUT_S = 0.2
        card_daemon.SERIAL_RAW_END_TIMEOUT_S = 0.2
        packed = b"\x5a" * card_daemon.FRAME_BYTES

        card_daemon.push_frame_bytes(packed)

        commands = [
            json.loads(line.decode("utf-8").strip())
            for line in fake.json_lines
        ]
        self.assertEqual(commands[0]["cmd"], "frame_raw_begin")
        self.assertEqual(commands[0]["bytes"], card_daemon.FRAME_BYTES)
        self.assertEqual(fake.raw_payload, packed)
        self.assertNotIn("frame_chunk", [cmd.get("cmd") for cmd in commands])


if __name__ == "__main__":
    unittest.main()
