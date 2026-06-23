import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


class FakeProc:
    def __init__(self, cmd):
        self.cmd = cmd
        self.terminated = False

    def poll(self):
        return None if not self.terminated else 0

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0


class OnboardPaperS3Test(unittest.TestCase):
    def test_runs_serial_provision_wifi_dashboard_sequence_without_password_in_commands(self):
        import onboard_papers3

        calls = []
        popens = []
        requests = []

        def fake_call(cmd, cwd=None):
            calls.append(cmd)
            return 0

        def fake_popen(cmd, **kwargs):
            proc = FakeProc(cmd)
            popens.append(proc)
            return proc

        def fake_request(method, daemon_url, path, payload=None, timeout=4.0):
            requests.append((method, path, payload))
            if path == "/pair-status":
                return 200, {"connected": True, "transport": "SerialTransport"}
            if path == "/heartbeat":
                return 200, {"wifi_ip": "192.168.137.253", "alive": True}
            if path == "/provision-wifi":
                return 200, {"ok": True}
            return 200, {"ok": True}

        args = onboard_papers3.build_arg_parser().parse_args([
            "--port", "COM3",
            "--wifi-ssid", "DeskNet",
            "--wifi-password", "secret-password",
            "--skip-build",
            "--skip-upload",
            "--wifi-timeout", "1",
            "--daemon-timeout", "1",
        ])

        result = onboard_papers3.run(
            args,
            call=fake_call,
            popen=fake_popen,
            request_json=fake_request,
            sleep=lambda seconds: None,
        )

        self.assertEqual(result, 0)
        self.assertEqual(len(popens), 2)
        self.assertIn("--transport", popens[0].cmd)
        self.assertIn("serial", popens[0].cmd)
        self.assertIn("--transport", popens[1].cmd)
        self.assertIn("wifi", popens[1].cmd)
        self.assertIn("--host", popens[1].cmd)
        self.assertIn("192.168.137.253", popens[1].cmd)
        self.assertIn("--http-host", popens[1].cmd)
        self.assertIn("0.0.0.0", popens[1].cmd)
        self.assertTrue(popens[0].terminated)
        self.assertIn("dashboard", calls[-1])
        self.assertIn(("POST", "/provision-wifi", {
            "ssid": "DeskNet",
            "password": "secret-password",
        }), requests)
        rendered_commands = " ".join(" ".join(cmd) for cmd in calls + [p.cmd for p in popens])
        self.assertNotIn("secret-password", rendered_commands)

    def test_known_host_skips_wifi_prompt_and_reprovision(self):
        import onboard_papers3

        calls = []
        popens = []
        requests = []

        def fake_call(cmd, cwd=None):
            calls.append(cmd)
            return 0

        def fake_popen(cmd, **kwargs):
            proc = FakeProc(cmd)
            popens.append(proc)
            return proc

        def fake_request(method, daemon_url, path, payload=None, timeout=4.0):
            requests.append((method, path, payload))
            if path == "/pair-status":
                return 200, {"connected": True, "transport": "WiFiTransport"}
            if path == "/heartbeat":
                return 200, {"alive": True, "wifi_ip": "192.168.137.253"}
            return 200, {"ok": True}

        args = onboard_papers3.build_arg_parser().parse_args([
            "--port", "COM3",
            "--host", "192.168.137.253",
            "--non-interactive",
            "--skip-build",
            "--skip-upload",
            "--daemon-timeout", "1",
        ])

        result = onboard_papers3.run(
            args,
            call=fake_call,
            popen=fake_popen,
            request_json=fake_request,
            sleep=lambda seconds: None,
        )

        self.assertEqual(result, 0)
        self.assertEqual(popens, [])
        self.assertNotIn("/provision-wifi", [path for _, path, _ in requests])
        self.assertIn("dashboard", calls[-1])

    def test_noninteractive_requires_wifi_password_when_wifi_is_enabled(self):
        import onboard_papers3

        args = onboard_papers3.build_arg_parser().parse_args([
            "--port", "COM3",
            "--wifi-ssid", "DeskNet",
            "--non-interactive",
        ])

        with self.assertRaises(SystemExit):
            onboard_papers3.resolve_wifi_credentials(args)


if __name__ == "__main__":
    unittest.main()
