import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import demo_papers3_widgets as demo


class DemoPaperS3WidgetsTest(unittest.TestCase):
    def test_text_demo_uses_full_scratch_card_with_title(self):
        selection = demo.build_demo_selection("text", now_iso="2026-06-15T12:34:00")

        self.assertEqual(selection["action"], "widgets")
        self.assertEqual(selection["payloads"], [{
            "slot": "full",
            "type": "scratch",
            "data": {
                "title": "PaperS3 Text",
                "source": "demo",
                "age": "12:34",
                "text": "PaperS3 real widget demo\nMultiline text wraps through the existing scratch renderer.",
            },
        }])

    def test_weather_calendar_todo_dashboard_uses_existing_widget_types(self):
        selection = demo.build_demo_selection("dashboard", now_iso="2026-06-15T12:34:00")

        payloads = selection["payloads"]
        self.assertEqual(selection["action"], "widgets")
        self.assertEqual([p["type"] for p in payloads], [
            "weather", "ai-status", "calendar", "todo",
        ])
        self.assertEqual([p["slot"] for p in payloads], [
            "top-left", "top-right", "middle", "bottom",
        ])

    def test_status_demo_uses_existing_settings_page(self):
        selection = demo.build_demo_selection("status", now_iso="2026-06-15T12:34:00")

        self.assertEqual(selection, {"action": "status", "payloads": []})

    def test_frame_status_is_complete_after_new_render_finishes(self):
        before = {"render_id": 4, "in_progress": False, "result": "ok"}
        current = {"render_id": 5, "in_progress": False, "result": "ok"}

        self.assertTrue(demo.frame_status_is_complete(before, current))
        self.assertFalse(demo.frame_status_is_complete(
            before, {"render_id": 5, "in_progress": True, "result": "rendering"}
        ))
        self.assertFalse(demo.frame_status_is_complete(
            before, {"render_id": 4, "in_progress": False, "result": "ok"}
        ))

    def test_auto_profile_does_not_treat_daemon_default_as_detection(self):
        pair = {"selected_profile": "m5paper-v1.1", "profile_source": "default"}

        self.assertIsNone(demo._resolve_profile("auto", pair, {}))
        self.assertEqual(demo._resolve_profile("paper-s3", pair, {})["name"], "paper-s3")

    def test_ensure_widget_view_exits_status_page_and_returns_new_baseline(self):
        calls = []
        old_request_json = demo._request_json
        old_wait_for_frame = demo._wait_for_frame

        def fake_request_json(method, daemon_url, path, payload=None, timeout=4.0):
            calls.append((method, path, payload))
            if method == "POST" and path == "/back":
                return 200, {"ok": True, "in_settings": False}
            raise AssertionError((method, path, payload))

        def fake_wait_for_frame(daemon_url, before, timeout_s, poll_s):
            self.assertEqual(before["selected_view"], "status")
            return {
                "render_id": before["render_id"] + 1,
                "selected_view": "widgets",
                "result": "ok",
            }

        demo._request_json = fake_request_json
        demo._wait_for_frame = fake_wait_for_frame
        try:
            baseline = demo._ensure_widget_view(
                "http://daemon",
                {"render_id": 7, "selected_view": "status"},
                timeout_s=90,
                poll_s=0.5,
            )
        finally:
            demo._request_json = old_request_json
            demo._wait_for_frame = old_wait_for_frame

        self.assertEqual(calls, [("POST", "/back", {})])
        self.assertEqual(baseline["selected_view"], "widgets")

    def test_ensure_widget_view_keeps_widget_baseline_without_request(self):
        baseline = {"render_id": 3, "selected_view": "widgets"}

        self.assertIs(demo._ensure_widget_view(
            "http://daemon", baseline, timeout_s=90, poll_s=0.5
        ), baseline)


if __name__ == "__main__":
    unittest.main()
