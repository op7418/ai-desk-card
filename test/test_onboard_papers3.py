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
            "--city", "Shanghai",
            "--card-name", "Lucy",
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
        rendered_calls = [" ".join(cmd).replace("\\", "/") for cmd in calls]
        self.assertIn("configure_interests.py", rendered_calls[0])
        self.assertIn("configure_profile.py", rendered_calls[1])
        self.assertIn("push_configured_dashboard.py", rendered_calls[2])
        self.assertNotIn("demo_papers3_widgets.py", " ".join(rendered_calls))
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
            "--city", "Shanghai",
            "--card-name", "Lucy",
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
        rendered_calls = [" ".join(cmd).replace("\\", "/") for cmd in calls]
        self.assertIn("configure_interests.py", rendered_calls[0])
        self.assertIn("configure_profile.py", rendered_calls[1])
        self.assertIn("push_configured_dashboard.py", rendered_calls[2])
        self.assertNotIn("demo_papers3_widgets.py", " ".join(rendered_calls))

    def test_onboard_writes_papers3_interests_after_dashboard_by_default(self):
        import onboard_papers3

        calls = []
        requests = []

        def fake_call(cmd, cwd=None):
            calls.append(cmd)
            return 0

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
            "--city", "Shanghai",
            "--card-name", "Lucy",
            "--skip-build",
            "--skip-upload",
            "--daemon-timeout", "1",
        ])

        result = onboard_papers3.run(
            args,
            call=fake_call,
            popen=lambda cmd, **kwargs: FakeProc(cmd),
            request_json=fake_request,
            sleep=lambda seconds: None,
        )

        self.assertEqual(result, 0)
        self.assertIn("configure_interests.py", "/".join(calls[0]).replace("\\", "/"))
        self.assertIn("--profile", calls[0])
        self.assertIn("paper-s3", calls[0])
        self.assertIn("--city", calls[0])
        self.assertIn("Shanghai", calls[0])
        self.assertIn("--cadence", calls[0])
        self.assertIn("30m", calls[0])
        self.assertIn("configure_profile.py", "/".join(calls[1]).replace("\\", "/"))
        self.assertIn("--name", calls[1])
        self.assertIn("Lucy", calls[1])
        self.assertIn("push_configured_dashboard.py", "/".join(calls[2]).replace("\\", "/"))

    def test_onboard_can_skip_interests_for_existing_setups(self):
        import onboard_papers3

        calls = []

        def fake_call(cmd, cwd=None):
            calls.append(cmd)
            return 0

        def fake_request(method, daemon_url, path, payload=None, timeout=4.0):
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
            "--skip-interests",
            "--skip-card-profile",
        ])

        result = onboard_papers3.run(
            args,
            call=fake_call,
            popen=lambda cmd, **kwargs: FakeProc(cmd),
            request_json=fake_request,
            sleep=lambda seconds: None,
        )

        self.assertEqual(result, 0)
        self.assertEqual(len(calls), 1)
        self.assertIn("push_configured_dashboard.py", "/".join(calls[0]).replace("\\", "/"))

    def test_noninteractive_requires_flow04_inputs(self):
        import onboard_papers3

        args = onboard_papers3.build_arg_parser().parse_args([
            "--port", "COM3",
            "--host", "192.168.137.253",
            "--non-interactive",
            "--skip-build",
            "--skip-upload",
        ])

        with self.assertRaises(SystemExit):
            onboard_papers3.resolve_flow04_inputs(args)

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
