import os
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class SkillWorkflowDocsTest(unittest.TestCase):
    def test_papers3_onboard_does_not_silently_skip_flow04(self):
        with open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8") as f:
            skill = f.read()
        with open(os.path.join(ROOT, "flows", "04_interests.md"), encoding="utf-8") as f:
            flow04 = f.read()
        with open(os.path.join(ROOT, "plugin", "commands", "card-onboard.md"), encoding="utf-8") as f:
            command = f.read()

        self.assertIn("PaperS3 onboard completion rule", skill)
        self.assertIn("rewrite flow 04 inputs or preserve", skill)
        self.assertIn("Do not infer that choice from a healthy daemon", skill)
        self.assertIn("PaperS3 first-time/onboard requests are also an explicit trigger", flow04)
        self.assertIn("Do not silently skip flow 04", flow04)
        self.assertIn("rewrite-or-preserve question", command)


if __name__ == "__main__":
    unittest.main()
