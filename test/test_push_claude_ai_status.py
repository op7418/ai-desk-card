import json
import os
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import push_claude_ai_status as push_claude


STATUSLINE = {
    "model": {
        "id": "claude-sonnet-4-5",
        "display_name": "Sonnet 4.5",
    },
    "session_name": "PaperS3 work",
    "rate_limits": {
        "five_hour": {
            "used_percentage": 28,
            "resets_at": 1781606595,
        },
        "seven_day": {
            "used_percentage": 52,
            "resets_at": 1782104484,
        },
    },
}


class PushClaudeAiStatusTest(unittest.TestCase):
    def test_statusline_json_to_usage(self):
        usage = push_claude.statusline_to_usage(STATUSLINE)

        self.assertEqual(usage["model"], "Sonnet 4.5")
        self.assertEqual(usage["session_name"], "PaperS3 work")
        self.assertEqual(usage["five_hour_remaining"], "72% left")
        self.assertEqual(usage["weekly_remaining"], "48% left")
        self.assertIn("5h", usage["reset_hint"])
        self.assertIn("wk", usage["reset_hint"])

    def test_missing_rate_limits_is_not_ready(self):
        usage = push_claude.statusline_to_usage({
            "model": {"display_name": "Opus"},
        })

        self.assertEqual(usage["model"], "Opus")
        self.assertFalse(push_claude.has_quota(usage))

    def test_build_payload_uses_ai_status_usage_shape(self):
        payload = push_claude.build_payload(
            slot="top-right",
            task="Claude usage remaining",
            usage={
                "model": "Sonnet 4.5",
                "session_name": "Claude Code",
                "five_hour_remaining": "72% left",
                "weekly_remaining": "48% left",
            },
        )

        self.assertEqual(payload["type"], "ai-status")
        self.assertEqual(payload["slot"], "top-right")
        self.assertEqual(payload["data"]["session_name"], "Claude Code")
        self.assertEqual(payload["data"]["model"], "Sonnet 4.5")
        self.assertEqual(payload["data"]["usage"], {
            "five_hour_remaining": "72% left",
            "weekly_remaining": "48% left",
        })
        self.assertNotIn("context", payload["data"])

    def test_cache_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "usage.json")
            push_claude.write_usage_cache(STATUSLINE, state_file)

            usage = push_claude.load_usage(state_file)

        self.assertEqual(usage["model"], "Sonnet 4.5")
        self.assertEqual(usage["five_hour_remaining"], "72% left")
        self.assertEqual(usage["weekly_remaining"], "48% left")

    def test_statusline_output_is_short(self):
        text = push_claude.format_statusline({
            "model": "Sonnet 4.5",
            "five_hour_remaining": "72% left",
            "weekly_remaining": "48% left",
        })

        self.assertEqual(text, "Sonnet 4.5 | 5h 72% left | wk 48% left")

    def test_empty_statusline_text_reports_clear_error(self):
        with self.assertRaisesRegex(ValueError, "empty Claude statusline JSON"):
            push_claude.parse_statusline_json("")


if __name__ == "__main__":
    unittest.main()
