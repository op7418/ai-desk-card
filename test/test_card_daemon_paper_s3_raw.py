import os
import sys
import json
import tempfile
import time
import types
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
        self.old_in_settings = card_daemon.IN_SETTINGS
        self.old_ui_state = card_daemon.UI_STATE
        self.old_ui_last_error = card_daemon.UI_LAST_ERROR
        self.old_frame_last_push = card_daemon._FRAME_LAST_PUSH
        self.old_widget_cache = dict(card_daemon.WIDGET_CACHE)
        self.old_frame_status = dict(card_daemon.FRAME_STATUS)
        card_daemon.DEVICE_TELEMETRY.clear()
        with card_daemon.WIDGET_LOCK:
            card_daemon.WIDGET_CACHE.clear()
        card_daemon._FRAME_ID = 0
        card_daemon._FRAME_LAST_PUSH = 0.0
        card_daemon.IN_SETTINGS = False
        card_daemon.UI_STATE = "BOOTING"
        card_daemon.UI_LAST_ERROR = ""
        card_daemon._reset_frame_status_for_test()
        with card_daemon._RX_LISTENERS_LOCK:
            card_daemon._RX_LISTENERS.clear()

    def tearDown(self):
        card_daemon.TRANSPORT = self.old_transport
        card_daemon.SERIAL_RAW_WRITE_SIZE = self.old_write_size
        card_daemon.SERIAL_RAW_WRITE_DELAY_S = self.old_write_delay
        card_daemon.SERIAL_RAW_BEGIN_TIMEOUT_S = self.old_begin_timeout
        card_daemon.SERIAL_RAW_END_TIMEOUT_S = self.old_end_timeout
        card_daemon.IN_SETTINGS = self.old_in_settings
        card_daemon.UI_STATE = self.old_ui_state
        card_daemon.UI_LAST_ERROR = self.old_ui_last_error
        card_daemon._FRAME_LAST_PUSH = self.old_frame_last_push
        with card_daemon.WIDGET_LOCK:
            card_daemon.WIDGET_CACHE.clear()
            card_daemon.WIDGET_CACHE.update(self.old_widget_cache)
        card_daemon.FRAME_STATUS.clear()
        card_daemon.FRAME_STATUS.update(self.old_frame_status)
        card_daemon.VIEW_HOT_ZONES = []
        card_daemon._FRAME_DIRTY.clear()
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

    def test_daemon_opens_serial_without_toggling_reset_lines(self):
        opened = []

        class FakeSerial:
            def __init__(self):
                self.port = None
                self.baudrate = None
                self.timeout = None
                self.write_timeout = None
                self.dtr = True
                self.rts = True

            def open(self):
                opened.append((self.dtr, self.rts))

        old_serial = sys.modules.get("serial")
        sys.modules["serial"] = types.SimpleNamespace(Serial=FakeSerial)
        try:
            ser = card_daemon._open_serial_no_reset("COM3", 115200)
        finally:
            if old_serial is None:
                sys.modules.pop("serial", None)
            else:
                sys.modules["serial"] = old_serial

        self.assertEqual(opened, [(False, False)])
        self.assertEqual(ser.port, "COM3")
        self.assertEqual(ser.baudrate, 115200)
        self.assertFalse(ser.dtr)
        self.assertFalse(ser.rts)

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

    def test_serial_touch_listener_dispatches_refresh_action(self):
        card_daemon.VIEW_HOT_ZONES = [
            {"action": "refresh", "rect": (0, 900, 160, 960)}
        ]
        card_daemon._FRAME_DIRTY.clear()

        card_daemon._touch_event_listener(
            '{"event":"touch","x":80,"y":930,"hold_ms":120}'
        )

        self.assertTrue(card_daemon._FRAME_DIRTY.is_set())

    def test_serial_touch_listener_dispatches_restart_action(self):
        fake = FakeRawSerialTransport()
        card_daemon.TRANSPORT = fake
        card_daemon.VIEW_HOT_ZONES = [
            {"action": "restart", "rect": (0, 100, 540, 160)}
        ]

        card_daemon._touch_event_listener(
            '{"event":"touch","x":100,"y":120,"hold_ms":120}'
        )

        commands = [
            json.loads(line.decode("utf-8").strip())
            for line in fake.json_lines
        ]
        self.assertIn({"cmd": "restart"}, commands)

    def test_serial_touch_listener_dispatches_sleep_without_blocking_reader(self):
        calls = []
        old_dispatch = card_daemon._internal_dispatch

        def slow_dispatch(action):
            time.sleep(0.2)
            calls.append(action)
            return {"action": action}

        card_daemon._internal_dispatch = slow_dispatch
        card_daemon.VIEW_HOT_ZONES = [
            {"action": "sleep", "rect": (0, 900, 160, 960)}
        ]
        try:
            start = time.time()
            card_daemon._touch_event_listener(
                '{"event":"touch","x":80,"y":930,"hold_ms":120}'
            )
            elapsed = time.time() - start

            self.assertLess(elapsed, 0.1)
            deadline = time.time() + 1.0
            while not calls and time.time() < deadline:
                time.sleep(0.01)
            self.assertEqual(calls, ["sleep"])
        finally:
            card_daemon._internal_dispatch = old_dispatch

    def test_status_and_home_actions_drive_settings_view(self):
        card_daemon.IN_SETTINGS = False
        card_daemon._FRAME_DIRTY.clear()

        status_result = card_daemon._internal_dispatch("status")

        self.assertEqual(status_result["action"], "status")
        self.assertTrue(status_result["accepted"])
        self.assertTrue(card_daemon.IN_SETTINGS)
        self.assertTrue(card_daemon._FRAME_DIRTY.is_set())

        card_daemon._FRAME_DIRTY.clear()
        home_result = card_daemon._internal_dispatch("home")

        self.assertEqual(home_result["action"], "home")
        self.assertTrue(home_result["accepted"])
        self.assertFalse(card_daemon.IN_SETTINGS)
        self.assertTrue(card_daemon._FRAME_DIRTY.is_set())

    def test_retry_action_without_error_does_not_schedule_refresh(self):
        card_daemon._FRAME_DIRTY.clear()

        result = card_daemon._internal_dispatch("retry")

        self.assertEqual(result["action"], "retry")
        self.assertTrue(result["accepted"])
        self.assertEqual(result["reason"], "no-error")
        self.assertEqual(result["frame_request"], "none")
        self.assertFalse(card_daemon._FRAME_DIRTY.is_set())

    def test_retry_action_with_error_schedules_refresh(self):
        card_daemon.UI_LAST_ERROR = "paper-s3 raw serial frame push failed"
        card_daemon._FRAME_DIRTY.clear()

        result = card_daemon._internal_dispatch("retry")

        self.assertEqual(result["action"], "retry")
        self.assertTrue(result["accepted"])
        self.assertEqual(result["frame_request"], "scheduled")
        self.assertTrue(card_daemon._FRAME_DIRTY.is_set())
        self.assertEqual(card_daemon.UI_LAST_ERROR, "")

    def test_refresh_action_returns_to_widget_view_before_render(self):
        card_daemon.IN_SETTINGS = True
        card_daemon._FRAME_DIRTY.clear()

        result = card_daemon._internal_dispatch("refresh")

        self.assertEqual(result["action"], "refresh")
        self.assertTrue(result["accepted"])
        self.assertFalse(card_daemon.IN_SETTINGS)
        self.assertTrue(card_daemon._FRAME_DIRTY.is_set())

    def test_touch_action_ignored_while_frame_push_busy(self):
        card_daemon._FRAME_DIRTY.clear()

        acquired = card_daemon._FRAME_LOCK.acquire(timeout=0.1)
        self.assertTrue(acquired)
        try:
            result = card_daemon._dispatch_touch_action("refresh")
        finally:
            card_daemon._FRAME_LOCK.release()

        self.assertEqual(result["action"], "refresh")
        self.assertFalse(result["accepted"])
        self.assertEqual(result["reason"], "busy")
        self.assertFalse(card_daemon._FRAME_DIRTY.is_set())

    def test_settings_state_exposes_paper_s3_status_fields(self):
        card_daemon.DEVICE_TELEMETRY.update({
            "device": "M5Stack PaperS3",
            "firmware": "0.10.7-paper-s3-frame",
            "wifi_ip": "192.168.4.23",
            "frame_state": "displayed",
        })
        card_daemon._FRAME_LAST_PUSH = time.time() - 12

        state = card_daemon._settings_state()

        self.assertEqual(state["model"], "M5Stack PaperS3")
        self.assertEqual(state["firmware_profile"], "paper-s3")
        self.assertEqual(state["ip"], "192.168.4.23")
        self.assertEqual(state["last_frame_age_s"], 12)
        self.assertIn(state["ui_state"], {
            "BOOTING", "READY", "RECEIVING_FRAME", "DISPLAYING_FRAME",
            "ERROR", "STATUS",
        })

    def test_render_and_push_records_real_widget_frame_status(self):
        fake = FakeRawSerialTransport()
        card_daemon.TRANSPORT = fake
        card_daemon.DEVICE_TELEMETRY.update({
            "device": "M5Stack PaperS3",
            "firmware": "0.10.7-paper-s3-frame",
            "frame_state": "ready",
        })
        card_daemon.SERIAL_RAW_WRITE_SIZE = card_daemon.FRAME_BYTES
        card_daemon.SERIAL_RAW_WRITE_DELAY_S = 0.0
        card_daemon.SERIAL_RAW_BEGIN_TIMEOUT_S = 0.2
        card_daemon.SERIAL_RAW_END_TIMEOUT_S = 0.2
        with card_daemon.WIDGET_LOCK:
            card_daemon.WIDGET_CACHE["full"] = {
                "type": "scratch",
                "data": {"title": "Desk Note", "text": "Real widget frame"},
                "theme": "",
                "ttl": 0,
                "stale_after": 0,
                "written_at": time.time(),
            }

        card_daemon.render_and_push()

        status = card_daemon._frame_status_snapshot()
        self.assertEqual(status["selected_profile"], "paper-s3")
        self.assertEqual(status["selected_view"], "widgets")
        self.assertEqual(status["selected_widgets"], ["scratch"])
        self.assertEqual(status["output"], {
            "width": 540,
            "height": 960,
            "format": "4bpp",
        })
        self.assertEqual(status["transfer"]["method"], "raw-serial")
        self.assertEqual(status["transfer"]["bytes"], card_daemon.FRAME_BYTES)
        self.assertEqual(status["result"], "ok")


if __name__ == "__main__":
    unittest.main()
