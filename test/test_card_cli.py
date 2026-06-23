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

    def test_daemon_command_can_select_wifi_host_and_port(self):
        import card_cli
        import card_profiles

        profile = card_profiles.get_profile("paper-s3")
        command = card_cli.daemon_command(
            profile,
            root=ROOT,
            transport="wifi",
            host="192.0.2.55",
            wifi_port=9899,
        )

        self.assertEqual(command[-8:], [
            "--profile", "paper-s3",
            "--transport", "wifi",
            "--host", "192.0.2.55",
            "--wifi-port", "9899",
        ])

    def test_daemon_command_can_bind_http_host_for_wifi_callbacks(self):
        import card_cli
        import card_profiles

        profile = card_profiles.get_profile("paper-s3")
        command = card_cli.daemon_command(
            profile,
            root=ROOT,
            transport="wifi",
            host="192.0.2.55",
            http_host="0.0.0.0",
        )

        self.assertIn("--http-host", command)
        self.assertIn("0.0.0.0", command)

    def test_demo_command_defaults_to_dashboard_for_first_push(self):
        import card_cli

        captured = []
        old_run_or_print = card_cli._run_or_print

        def fake_run_or_print(cmd, dry_run):
            captured.append((cmd, dry_run))
            return 0

        card_cli._run_or_print = fake_run_or_print
        try:
            result = card_cli.main(["demo", "--profile", "paper-s3", "--dry-run"])
        finally:
            card_cli._run_or_print = old_run_or_print

        self.assertEqual(result, 0)
        self.assertEqual(captured[0][0][-1], "dashboard")
        self.assertTrue(captured[0][1])

    def test_onboard_command_delegates_to_paper_s3_wrapper(self):
        import card_cli

        captured = []
        old_run_or_print = card_cli._run_or_print

        def fake_run_or_print(cmd, dry_run):
            captured.append((cmd, dry_run))
            return 0

        card_cli._run_or_print = fake_run_or_print
        try:
            result = card_cli.main([
                "onboard",
                "--profile", "paper-s3",
                "--port", "COM3",
                "--host", "192.168.137.253",
                "--dry-run",
            ])
        finally:
            card_cli._run_or_print = old_run_or_print

        self.assertEqual(result, 0)
        command = captured[0][0]
        self.assertIn("onboard_papers3.py", "/".join(command).replace("\\", "/"))
        self.assertIn("--profile", command)
        self.assertIn("paper-s3", command)
        self.assertIn("--port", command)
        self.assertIn("COM3", command)
        self.assertIn("--host", command)
        self.assertIn("192.168.137.253", command)
        self.assertTrue(captured[0][1])


if __name__ == "__main__":
    unittest.main()
