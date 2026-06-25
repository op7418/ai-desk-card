import os
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class PaperS3WiFiFirmwareSourcesTest(unittest.TestCase):
    def _read(self, rel):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            return f.read()

    def test_paper_s3_has_profile_local_wifi_and_http_sources(self):
        for rel in (
            "src/paper_s3/paper_s3_wifi_bridge.h",
            "src/paper_s3/paper_s3_wifi_bridge.cpp",
            "src/paper_s3/paper_s3_http_server.h",
            "src/paper_s3/paper_s3_http_server.cpp",
        ):
            self.assertTrue(os.path.exists(os.path.join(ROOT, rel)), rel)

    def test_paper_s3_main_wires_wifi_http_mdns_and_no_longer_says_disabled(self):
        main_cpp = self._read("src/paper_s3/main.cpp")

        self.assertIn("paper_s3_wifi_bridge.h", main_cpp)
        self.assertIn("paper_s3_http_server.h", main_cpp)
        self.assertIn("ESPmDNS.h", main_cpp)
        self.assertIn("startMDNSIfNeeded", main_cpp)
        self.assertNotIn("wifi disabled in phase 1", main_cpp)

    def test_paper_s3_http_server_does_not_depend_on_m5epd(self):
        http_cpp = self._read("src/paper_s3/paper_s3_http_server.cpp")

        self.assertNotIn("M5EPD", http_cpp)
        self.assertIn("POST /frame", http_cpp)
        self.assertIn("X-Frame-Crc", http_cpp)
        self.assertIn("httpPostJsonToDaemon", http_cpp)

    def test_paper_s3_status_report_uses_json_serializer_for_wifi_fields(self):
        main_cpp = self._read("src/paper_s3/main.cpp")

        self.assertIn("serializeJson(doc, line)", main_cpp)
        self.assertIn("serializeJson(ack, Serial)", main_cpp)
        self.assertNotIn("\\\"wifi_ssid\\\":\\\"%s\\\"", main_cpp)
        self.assertNotIn("\\\"ack\\\":\\\"wifi_set\\\",\\\"ok\\\":true,\\\"ssid\\\":\\\"%s\\\"", main_cpp)

    def test_paper_s3_firmware_exposes_stage8_power_fields(self):
        main_cpp = self._read("src/paper_s3/main.cpp")
        hw_cpp = self._read("src/paper_s3/paper_s3_hw.cpp")
        http_cpp = self._read("src/paper_s3/paper_s3_http_server.cpp")

        self.assertIn("getVBUSVoltage", hw_cpp)
        for field in (
            "vbus_mv",
            "power_source",
            "power_mode",
            "deep_sleep_enabled",
            "wake_reason",
            "last_power_read_ms",
        ):
            self.assertIn(field, main_cpp)
            self.assertIn(field, http_cpp)

    def test_paper_s3_startup_screen_waits_for_dashboard_not_touch_test(self):
        main_cpp = self._read("src/paper_s3/main.cpp")
        hw_cpp = self._read("src/paper_s3/paper_s3_hw.cpp")
        hw_h = self._read("src/paper_s3/paper_s3_hw.h")

        self.assertIn("paintWaitingForDashboardScreen", hw_h)
        self.assertIn("paintWaitingForDashboardScreen(CARD_VERSION, wifiIPStr())", main_cpp)
        self.assertNotIn("paintTouchCalibrationScreen(CARD_VERSION)", main_cpp)
        self.assertIn("Waiting for dashboard", hw_cpp)
        self.assertNotIn("PaperS3 Touch Test", hw_cpp)


if __name__ == "__main__":
    unittest.main()
