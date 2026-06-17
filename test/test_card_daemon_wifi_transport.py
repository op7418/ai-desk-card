import os
import sys
import types
import unittest
import urllib.error
import urllib.request


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "daemon"))

import card_daemon


class _FakeResponse:
    def __init__(self, status=200, body=b'{"ok":true}'):
        self.status = status
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._body


class CardDaemonWiFiTransportTest(unittest.TestCase):
    def test_wifi_transport_posts_frame_with_integrity_headers(self):
        captured = {}
        old_urlopen = urllib.request.urlopen

        def fake_urlopen(req, timeout=0):
            captured["url"] = req.full_url
            captured["timeout"] = timeout
            captured["data"] = req.data
            captured["headers"] = dict(req.header_items())
            return _FakeResponse()

        urllib.request.urlopen = fake_urlopen
        try:
            transport = card_daemon.WiFiTransport("192.0.2.42", 9880)
            ok = transport.push_frame_http(
                b"\x5a" * card_daemon.FRAME_BYTES,
                None,
                fid=7,
                crc=0x1234ABCD,
            )
        finally:
            urllib.request.urlopen = old_urlopen

        self.assertTrue(ok)
        self.assertEqual(captured["url"], "http://192.0.2.42:9880/frame")
        self.assertEqual(captured["timeout"], 15)
        self.assertEqual(len(captured["data"]), card_daemon.FRAME_BYTES)
        self.assertEqual(captured["headers"]["X-frame-fid"], "7")
        self.assertEqual(captured["headers"]["X-frame-width"], "540")
        self.assertEqual(captured["headers"]["X-frame-height"], "960")
        self.assertEqual(captured["headers"]["X-frame-bpp"], "4")
        self.assertEqual(captured["headers"]["X-frame-bytes"], str(card_daemon.FRAME_BYTES))
        self.assertEqual(captured["headers"]["X-frame-crc"], "1234abcd")
        self.assertEqual(transport.last_error, "")

    def test_wifi_transport_records_host_unreachable_error(self):
        old_urlopen = urllib.request.urlopen

        def fake_urlopen(req, timeout=0):
            raise urllib.error.URLError(ConnectionRefusedError("refused"))

        urllib.request.urlopen = fake_urlopen
        try:
            transport = card_daemon.WiFiTransport("192.0.2.77", 9880)
            ok = transport.push_frame_http(b"\x00" * card_daemon.FRAME_BYTES, None)
        finally:
            urllib.request.urlopen = old_urlopen

        self.assertFalse(ok)
        self.assertFalse(transport.connected())
        self.assertIn("192.0.2.77:9880", transport.last_error)
        self.assertIn("refused", transport.last_error.lower())

    def test_pick_transport_uses_direct_wifi_host_without_mdns(self):
        made = []
        old_wifi = card_daemon.WiFiTransport

        class FakeWiFiTransport:
            def __init__(self, ip, port):
                made.append((ip, port))
                self.ip = ip
                self.port = port

        card_daemon.WiFiTransport = FakeWiFiTransport
        try:
            transport = card_daemon.pick_transport(
                "wifi",
                port=None,
                host="192.0.2.91",
                wifi_port=9899,
            )
        finally:
            card_daemon.WiFiTransport = old_wifi

        self.assertEqual(made, [("192.0.2.91", 9899)])
        self.assertEqual(transport.ip, "192.0.2.91")
        self.assertEqual(transport.port, 9899)

    def test_wifi_provision_command_allows_empty_ssid_to_clear_credentials(self):
        cmd, err = card_daemon._wifi_provision_command({"ssid": "", "password": "ignored"})

        self.assertIsNone(err)
        self.assertEqual(cmd, {"cmd": "wifi_set", "ssid": "", "password": ""})

    def test_arg_parser_supports_explicit_http_host_for_wifi_callbacks(self):
        args = card_daemon.build_arg_parser().parse_args([
            "--transport", "wifi",
            "--host", "192.0.2.44",
            "--http-host", "0.0.0.0",
        ])

        self.assertEqual(args.http_host, "0.0.0.0")
        self.assertEqual(args.http_port, 9877)


if __name__ == "__main__":
    unittest.main()
