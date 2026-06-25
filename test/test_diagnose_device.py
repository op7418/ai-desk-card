import os
import sys
import unittest
import urllib.request


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


class DiagnoseDeviceTest(unittest.TestCase):
    def test_paper_s3_advice_includes_commands_and_log_patterns(self):
        import diagnose_device
        import card_profiles

        profile = card_profiles.get_profile("paper-s3")
        advice = diagnose_device.build_advice(profile, root=ROOT, port="COM3")

        self.assertIn("paper-s3", " ".join(advice["build_command"]))
        self.assertIn(
            "daemon/card_daemon.py",
            "/".join(advice["daemon_command"]).replace("\\", "/"),
        )
        self.assertIn("--profile", advice["daemon_command"])
        self.assertIn("paper-s3", advice["demo_status_command"])
        self.assertIn("onboard_papers3.py", advice["onboard_command"].replace("\\", "/"))
        self.assertIn("[frame]", advice["daemon_log_patterns"])
        self.assertIn("[touch]", advice["device_log_patterns"])

    def test_paper_s3_wifi_advice_uses_explicit_host_when_provided(self):
        import diagnose_device
        import card_profiles

        profile = card_profiles.get_profile("paper-s3")
        advice = diagnose_device.build_advice(
            profile,
            root=ROOT,
            transport="wifi",
            host="192.0.2.44",
            wifi_port=9898,
            http_host="0.0.0.0",
        )

        self.assertIn("--transport", advice["daemon_command"])
        self.assertIn("wifi", advice["daemon_command"])
        self.assertIn("--host", advice["daemon_command"])
        self.assertIn("192.0.2.44", advice["daemon_command"])
        self.assertIn("--wifi-port", advice["daemon_command"])
        self.assertIn("9898", advice["daemon_command"])
        self.assertIn("--http-host", advice["daemon_command"])
        self.assertIn("0.0.0.0", advice["daemon_command"])
        self.assertIn("[wifi]", advice["daemon_log_patterns"])

    def test_paper_s3_power_section_reports_conservative_defaults(self):
        import diagnose_device
        import card_profiles

        profile = card_profiles.get_profile("paper-s3")
        section = diagnose_device.build_power_section(
            profile,
            frame_status={"power": {"mode": "always-on"}},
            device_status={
                "battery_pct": 73,
                "battery_mv": 4010,
                "on_usb": None,
                "charging": True,
                "power_source": "unknown",
                "wake_reason": "boot",
            },
        )

        self.assertEqual(section["power_mode"], "always-on")
        self.assertEqual(section["power_source"], "unknown")
        self.assertEqual(section["battery_pct"], 73)
        self.assertEqual(section["battery_mv"], 4010)
        self.assertEqual(section["charging"], True)
        self.assertFalse(section["deep_sleep_enabled"])
        self.assertEqual(section["deep_sleep_status"], "unsupported")
        self.assertEqual(section["ble_status"], "unsupported")
        self.assertEqual(section["last_wake_reason"], "boot")

    def test_device_status_uses_direct_opener(self):
        import diagnose_device

        captured = {}
        old_build_opener = urllib.request.build_opener

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"device":"M5Stack PaperS3"}'

        class FakeOpener:
            def open(self, url, timeout=0):
                captured["url"] = url
                captured["timeout"] = timeout
                return FakeResponse()

        def fake_build_opener(*handlers):
            captured["proxies"] = handlers[0].proxies
            return FakeOpener()

        urllib.request.build_opener = fake_build_opener
        try:
            code, status = diagnose_device._device_status("192.0.2.44", 9880)
        finally:
            urllib.request.build_opener = old_build_opener

        self.assertEqual(code, 200)
        self.assertEqual(status["device"], "M5Stack PaperS3")
        self.assertEqual(captured["url"], "http://192.0.2.44:9880/status")
        self.assertEqual(captured["timeout"], 4)
        self.assertEqual(captured["proxies"], {})


if __name__ == "__main__":
    unittest.main()
