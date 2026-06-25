import os
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


class ConfigureProfileTest(unittest.TestCase):
    def test_writes_business_card_profile_yaml(self):
        import configure_profile

        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "profile.yaml")
            args = configure_profile.build_arg_parser().parse_args([
                "--output", out,
                "--name", "Lucy",
                "--tagline", "AI desk card builder",
                "--bio", "Builds calm tools|Keeps e-ink useful",
                "--city", "Shanghai",
                "--link", "example.com/lucy",
                "--qr-label", "Scan to connect",
                "--footer", "ai-desk-card",
                "--non-interactive",
            ])

            result = configure_profile.run(args)

            self.assertEqual(result, 0)
            with open(out, encoding="utf-8") as f:
                written = f.read()
            self.assertIn('name: "Lucy"', written)
            self.assertIn('tagline: "AI desk card builder"', written)
            self.assertIn('- "Builds calm tools"', written)
            self.assertIn('icon: "City"', written)
            self.assertIn('text: "Shanghai"', written)
            self.assertIn('icon: "Web"', written)
            self.assertIn('text: "example.com/lucy"', written)
            self.assertIn('qr_label: "Scan to connect"', written)

    def test_noninteractive_requires_name(self):
        import configure_profile

        args = configure_profile.build_arg_parser().parse_args([
            "--non-interactive",
        ])

        with self.assertRaises(SystemExit):
            configure_profile.run(args)


if __name__ == "__main__":
    unittest.main()
