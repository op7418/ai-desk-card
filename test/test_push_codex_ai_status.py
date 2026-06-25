import json
import os
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import push_codex_ai_status as push_codex


STATUS_TEXT = """
╭─────────────────────────────────────────────────────────────────────────────────╮
│  >_ OpenAI Codex (v0.140.0)                                                     │
│                                                                                 │
│  Model:                gpt-5.5 (reasoning medium, summaries auto)               │
│  Account:              lucyundeadshao@gmail.com (Business)                      │
│                                                                                 │
│  5h limit:             [███████████████████░] 94% left (resets 18:43)           │
│  Weekly limit:         [███████████░░░░░░░░░] 53% left (resets 13:01 on 22 Jun) │
╰─────────────────────────────────────────────────────────────────────────────────╯
"""


class PushCodexAiStatusTest(unittest.TestCase):
    def test_parse_codex_status_text(self):
        usage = push_codex.parse_status_text(STATUS_TEXT)

        self.assertEqual(usage["model"], "gpt-5.5")
        self.assertEqual(usage["five_hour_remaining"], "94% left")
        self.assertEqual(usage["weekly_remaining"], "53% left")
        self.assertEqual(usage["reset_hint"], "5h 18:43 / wk 22 Jun 13:01")

    def test_rate_limits_snapshot_to_usage(self):
        usage = push_codex.rate_limits_to_usage({
            "primary": {
                "usedPercent": 28,
                "windowDurationMins": 300,
                "resetsAt": 1781606595,
            },
            "secondary": {
                "usedPercent": 50,
                "windowDurationMins": 10080,
                "resetsAt": 1782104484,
            },
        }, model="gpt-5.5")

        self.assertEqual(usage["model"], "gpt-5.5")
        self.assertEqual(usage["five_hour_remaining"], "72% left")
        self.assertEqual(usage["weekly_remaining"], "50% left")
        self.assertIn("5h", usage["reset_hint"])
        self.assertIn("wk", usage["reset_hint"])

    def test_env_values_override_state_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "usage.json")
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump({
                    "model": "file-model",
                    "usage": {
                        "five_hour_remaining": "1h",
                        "weekly_remaining": "20%",
                    },
                }, f)

            usage = push_codex.load_usage(
                state_file,
                env={
                    "CODEX_MODEL": "env-model",
                    "CODEX_5H_REMAINING": "3h 20m",
                    "CODEX_WEEKLY_REMAINING": "72%",
                },
            )

        self.assertEqual(usage["model"], "env-model")
        self.assertEqual(usage["five_hour_remaining"], "3h 20m")
        self.assertEqual(usage["weekly_remaining"], "72%")

    def test_build_payload_uses_ai_status_usage_shape(self):
        payload = push_codex.build_payload(
            slot="top-right",
            session_name="Codex",
            task="working on ai-desk-card",
            usage={
                "model": "GPT-5 Codex",
                "five_hour_remaining": "2h 10m",
                "weekly_remaining": "64%",
            },
        )

        self.assertEqual(payload["type"], "ai-status")
        self.assertEqual(payload["slot"], "top-right")
        self.assertEqual(payload["data"]["model"], "GPT-5 Codex")
        self.assertEqual(payload["data"]["usage"], {
            "five_hour_remaining": "2h 10m",
            "weekly_remaining": "64%",
        })
        self.assertNotIn("context", payload["data"])

    def test_missing_quota_is_not_ready(self):
        self.assertFalse(push_codex.has_quota({"model": "GPT-5 Codex"}))
        self.assertTrue(push_codex.has_quota({"five_hour_remaining": "2h"}))
        self.assertTrue(push_codex.has_quota({"weekly_remaining": "64%"}))


if __name__ == "__main__":
    unittest.main()
