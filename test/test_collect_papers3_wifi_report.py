import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import collect_papers3_wifi_report as report


class CollectPaperS3WiFiReportTest(unittest.TestCase):
    def test_report_masks_private_fields_and_includes_core_sections(self):
        text = report.build_report({
            "git": "abc123",
            "profile": "paper-s3",
            "transport": "wifi",
            "host": "192.0.2.9",
            "wifi_status": {
                "ssid": "HomeSecret",
                "ip": "192.0.2.9",
                "last_error": "auth failed",
                "password": "should-not-appear",
            },
            "daemon": {"pair_status": {"connected": True}},
            "frame": {
                "result": "failed",
                "error": "timeout",
                "power": {
                    "mode": "always-on",
                    "power_source": "usb",
                    "battery_pct": 73,
                    "deep_sleep_status": "unsupported",
                    "ble_status": "unsupported",
                    "last_wake_reason": "boot",
                },
            },
        })

        self.assertIn("# PaperS3 Wi-Fi Diagnostic Report", text)
        self.assertIn("git commit: abc123", text)
        self.assertIn("selected profile: paper-s3", text)
        self.assertIn("selected transport: wifi", text)
        self.assertIn("PaperS3 host: 192.0.2.9", text)
        self.assertIn("ssid: Hom***", text)
        self.assertNotIn("HomeSecret", text)
        self.assertNotIn("should-not-appear", text)
        self.assertIn("last frame result: failed", text)
        self.assertIn("## Power", text)
        self.assertIn("mode: always-on", text)
        self.assertIn("source: usb", text)
        self.assertIn("battery_pct: 73", text)
        self.assertIn("deep_sleep: unsupported", text)
        self.assertIn("BLE: unsupported", text)
        self.assertIn("wake_reason: boot", text)


if __name__ == "__main__":
    unittest.main()
