import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "daemon"))

import card_render


class CardRenderWidgetsTest(unittest.TestCase):
    def test_weather_location_is_below_header(self):
        img = card_render.render_image([
            {
                "slot": "top-left",
                "type": "weather",
                "data": {
                    "location": "Shanghai Xuhui",
                    "current": {"temp_c": 28, "condition": "rain"},
                    "forecast": [{"day": "today", "high": 29, "low": 24, "condition": "rain"}],
                },
            }
        ], status={})

        self.assertNotEqual(img.crop((20, 76, 250, 112)).tobytes(), _blank(230, 36))

    def test_ai_usage_suppresses_task_when_usage_exists(self):
        img = card_render.render_image([
            {
                "slot": "top-right",
                "type": "ai-status",
                "data": {
                    "session_name": "codex",
                    "model": "gpt-5.5",
                    "task": "this should not render",
                    "usage": {
                        "five_hour_remaining": "91% left",
                        "weekly_remaining": "42% left",
                        "reset_hint": "5h 16:00",
                    },
                },
            }
        ], status={})

        self.assertNotEqual(img.crop((290, 76, 520, 210)).tobytes(), _blank(230, 134))


def _blank(width, height):
    return bytes([255]) * width * height


if __name__ == "__main__":
    unittest.main()
