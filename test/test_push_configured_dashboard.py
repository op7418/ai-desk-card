import os
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


class PushConfiguredDashboardTest(unittest.TestCase):
    def test_builds_dashboard_from_interests_without_demo_content(self):
        import push_configured_dashboard

        interests = """
version: 1
slots:
  top-left: weather
  top-right: ai-status
  middle: calendar
  bottom: todo
schedule:
  cadence: "30m"
data_sources:
  weather:
    city: "Shanghai"
  calendar:
    source: "macos"
  todo:
    source: "reminders"
  ai-status:
    source: "codex"
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "interests.yaml")
            with open(path, "w", encoding="utf-8") as f:
                f.write(interests)

            payloads = push_configured_dashboard.build_payloads(path)

        weather = payloads[0]
        self.assertEqual(weather["type"], "weather")
        self.assertEqual(weather["slot"], "top-left")
        self.assertEqual(weather["data"]["location"], "Shanghai")
        rendered = repr(payloads).lower()
        self.assertNotIn("mock", rendered)
        self.assertNotIn("demo", rendered)
        self.assertNotIn("paperS3 demo".lower(), rendered)

    def test_codex_usage_loader_updates_ai_status_payload(self):
        import push_configured_dashboard

        interests = """
version: 1
slots:
  top-right: ai-status
data_sources:
  ai-status:
    source: "codex"
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "interests.yaml")
            with open(path, "w", encoding="utf-8") as f:
                f.write(interests)

            payloads = push_configured_dashboard.build_payloads(
                path,
                codex_usage_loader=lambda: {
                    "model": "gpt-5.5",
                    "five_hour_remaining": "90% left",
                    "weekly_remaining": "80% left",
                    "reset_hint": "5h 16:00",
                },
            )

        self.assertEqual(payloads[0]["type"], "ai-status")
        self.assertEqual(payloads[0]["data"]["session_name"], "codex")
        self.assertEqual(payloads[0]["data"]["model"], "gpt-5.5")
        self.assertEqual(payloads[0]["data"]["usage"]["five_hour_remaining"], "90% left")

    def test_only_filters_widgets_for_partial_refresh(self):
        import push_configured_dashboard

        interests = """
version: 1
slots:
  top-left: weather
  top-right: ai-status
  middle: calendar
  bottom: todo
data_sources:
  weather:
    city: "Shanghai"
  ai-status:
    source: "codex"
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "interests.yaml")
            with open(path, "w", encoding="utf-8") as f:
                f.write(interests)

            payloads = push_configured_dashboard.build_payloads(
                path,
                only_widgets={"weather", "ai-status"},
                codex_usage_loader=lambda: {
                    "five_hour_remaining": "90% left",
                    "weekly_remaining": "80% left",
                },
            )

        self.assertEqual([payload["type"] for payload in payloads], ["weather", "ai-status"])

    def test_partial_refresh_skips_widgets_without_live_data(self):
        import push_configured_dashboard

        interests = """
version: 1
slots:
  top-left: weather
  top-right: ai-status
data_sources:
  weather:
    city: "Unknown"
  ai-status:
    source: "codex"
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "interests.yaml")
            with open(path, "w", encoding="utf-8") as f:
                f.write(interests)

            payloads = push_configured_dashboard.build_payloads(
                path,
                only_widgets={"weather", "ai-status"},
                require_live=True,
                codex_usage_loader=lambda: {},
            )

        self.assertEqual(payloads, [])


if __name__ == "__main__":
    unittest.main()
