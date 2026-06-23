import os
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


class ConfigureInterestsTest(unittest.TestCase):
    def test_default_yaml_matches_m5paper_v11_readme_layout(self):
        import configure_interests

        args = configure_interests.build_arg_parser().parse_args([])
        text = configure_interests.build_yaml(args)

        self.assertIn("top-left: weather", text)
        self.assertIn("top-right: calendar", text)
        self.assertIn("middle: todo", text)
        self.assertIn("bottom: inbox", text)
        self.assertIn('cadence: "30m"', text)
        self.assertIn('timezone: "Asia/Shanghai"', text)

    def test_papers3_profile_yaml_matches_dashboard_layout(self):
        import configure_interests

        args = configure_interests.build_arg_parser().parse_args(["--profile", "paper-s3"])
        text = configure_interests.build_yaml(args)

        self.assertIn("top-left: weather", text)
        self.assertIn("top-right: ai-status", text)
        self.assertIn("middle: calendar", text)
        self.assertIn("bottom: todo", text)

    def test_writes_interests_yaml_to_requested_path(self):
        import configure_interests

        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "interests.yaml")
            args = configure_interests.build_arg_parser().parse_args([
                "--output", out,
                "--profile", "paper-s3",
                "--city", "Shanghai",
                "--cadence", "15m",
            ])

            result = configure_interests.run(args)

            self.assertEqual(result, 0)
            with open(out, encoding="utf-8") as f:
                written = f.read()
            self.assertIn('cadence: "15m"', written)
            self.assertIn('city: "Shanghai"', written)

    def test_custom_slot_mapping_is_validated(self):
        import configure_interests

        args = configure_interests.build_arg_parser().parse_args([
            "--slots", "top-left=weather,top-right=calendar,middle=todo,bottom=inbox",
        ])
        slots = configure_interests.parse_slots(args.slots, args.profile)

        self.assertEqual(slots["top-right"], "calendar")
        self.assertEqual(slots["bottom"], "inbox")

        with self.assertRaises(SystemExit):
            configure_interests.parse_slots("left=weather", args.profile)


if __name__ == "__main__":
    unittest.main()
