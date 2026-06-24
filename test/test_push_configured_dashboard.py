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


if __name__ == "__main__":
    unittest.main()
