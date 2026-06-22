import unittest


class DeviceProfilesTest(unittest.TestCase):
    def test_paper_s3_profile_has_required_stage8_fields(self):
        import card_profiles

        profile = card_profiles.get_profile("paper-s3")

        self.assertEqual(profile["device_name"], "M5Stack PaperS3")
        self.assertEqual(profile["platformio_env"], "paper-s3")
        self.assertEqual(profile["logical_width"], 540)
        self.assertEqual(profile["logical_height"], 960)
        self.assertEqual(profile["display_format"], "4bpp grayscale")
        self.assertEqual(profile["preferred_transport"], "Wi-Fi")
        self.assertEqual(profile["frame_bytes"], 259200)
        self.assertEqual(profile["supported_features"], {
            "frame_rendering": True,
            "touch": True,
            "ui_actions": True,
            "widgets": True,
            "ble": False,
            "deep_sleep": False,
            "battery_policy": True,
        })
        self.assertEqual(profile["power"]["default_mode"], "always-on")
        self.assertIn("idle-low-power", profile["power"]["supported_modes"])
        self.assertIn("sleep-card", profile["power"]["supported_modes"])
        self.assertEqual(profile["power"]["idle_timeout_minutes"], 0)
        self.assertFalse(profile["power"]["deep_sleep"]["enabled"])
        self.assertEqual(profile["power"]["deep_sleep"]["status"], "unsupported")
        self.assertEqual(profile["power"]["ble"]["status"], "unsupported")

    def test_profile_aliases_keep_original_card_environment(self):
        import card_profiles

        self.assertEqual(card_profiles.normalize_profile_name("card"), "m5paper-v1.1")
        self.assertEqual(card_profiles.get_profile("M5Paper V1.1")["platformio_env"], "card")
        self.assertEqual(card_profiles.normalize_profile_name("M5Stack PaperS3"), "paper-s3")

    def test_detect_profile_from_daemon_status_is_conservative(self):
        import card_profiles

        self.assertEqual(card_profiles.detect_profile_from_status({
            "firmware": "0.10.7-paper-s3-frame",
            "device": "M5Stack PaperS3",
        }), "paper-s3")
        self.assertEqual(card_profiles.detect_profile_from_status({
            "selected_profile": "m5paper-v1.1",
        }), "m5paper-v1.1")
        self.assertIsNone(card_profiles.detect_profile_from_status({
            "firmware": "0.10.1",
            "device": "unknown",
        }))


if __name__ == "__main__":
    unittest.main()
