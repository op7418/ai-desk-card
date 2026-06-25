import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "daemon"))

import card_render_settings


class CardRenderSettingsTest(unittest.TestCase):
    def test_m5paper_settings_renders_action_buttons(self):
        img = card_render_settings.render_settings_page({
            "firmware_profile": "m5paper-v1.1",
            "daemon_ok": True,
            "transport": "USB",
        })

        self.assertEqual(img.size, (540, 960))
        actions = [zone["action"] for zone in card_render_settings.get_hot_zones()]
        self.assertIn("sleep", actions)
        self.assertIn("refresh", actions)

    def test_paper_s3_settings_renders_power_status_and_actions(self):
        img = card_render_settings.render_settings_page({
            "firmware_profile": "paper-s3",
            "daemon_ok": True,
            "transport": "Wi-Fi",
            "power_mode": "always-on",
            "power_source": "usb",
            "battery_pct": 73,
            "battery_mv": 4010,
            "vbus_mv": 5000,
            "on_usb": True,
            "charging": True,
            "last_wake_reason": "boot",
        })

        self.assertEqual(img.size, (540, 960))
        actions = [zone["action"] for zone in card_render_settings.get_hot_zones()]
        self.assertIn("refresh", actions)
        self.assertIn("status", actions)
        self.assertIn("home", actions)


if __name__ == "__main__":
    unittest.main()
