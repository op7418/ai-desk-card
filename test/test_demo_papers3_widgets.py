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


if __name__ == "__main__":
    unittest.main()
