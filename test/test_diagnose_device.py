import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


class DiagnoseDeviceTest(unittest.TestCase):
    def test_paper_s3_advice_includes_commands_and_log_patterns(self):
        import diagnose_device
        import card_profiles

        profile = card_profiles.get_profile("paper-s3")
        advice = diagnose_device.build_advice(profile, root=ROOT, port="COM3")

        self.assertIn("paper-s3", " ".join(advice["build_command"]))
        self.assertIn(
            "daemon/card_daemon.py",
            "/".join(advice["daemon_command"]).replace("\\", "/"),
        )
        self.assertIn("--profile", advice["daemon_command"])
        self.assertIn("paper-s3", advice["demo_status_command"])
        self.assertIn("[frame]", advice["daemon_log_patterns"])
        self.assertIn("[touch]", advice["device_log_patterns"])


if __name__ == "__main__":
    unittest.main()
