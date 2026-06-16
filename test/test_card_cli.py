import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


class CardCliTest(unittest.TestCase):
    def test_build_upload_monitor_commands_use_profile_platformio_env(self):
        import card_cli
        import card_profiles

        profile = card_profiles.get_profile("paper-s3")

        self.assertEqual(
            card_cli.platformio_command(profile, "build", root=ROOT),
            [card_cli.platformio_executable(ROOT), "run", "-e", "paper-s3"],
        )
        self.assertEqual(
            card_cli.platformio_command(profile, "upload", root=ROOT, port="COM3")[-4:],
            ["paper-s3", "-t", "upload", "--upload-port=COM3"],
        )
        self.assertEqual(
            card_cli.platformio_command(profile, "monitor", root=ROOT, port="COM3")[-6:],
            ["monitor", "--environment", "paper-s3", "--port", "COM3", "--baud=115200"],
        )

    def test_daemon_command_uses_profile_transport_and_port(self):
        import card_cli
        import card_profiles

        profile = card_profiles.get_profile("paper-s3")
        command = card_cli.daemon_command(profile, root=ROOT, transport="serial", port="COM3")

        self.assertEqual(command[-6:], [
            "--profile", "paper-s3",
            "--transport", "serial",
            "--port", "COM3",
        ])


if __name__ == "__main__":
    unittest.main()
