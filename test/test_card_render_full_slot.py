import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "daemon"))

import card_render


class CardRenderFullSlotTest(unittest.TestCase):
    def test_full_slot_does_not_draw_grid_divider_over_content(self):
        img = card_render.render_image([
            {
                "slot": "full",
                "type": "scratch",
                "data": {"text": "Daemon raw frame test"},
            }
        ], status={})

        self.assertEqual(img.getpixel((270, 20)), 255)

    def test_scratch_title_is_rendered_as_text_card_heading(self):
        untitled = card_render.render_image([
            {
                "slot": "full",
                "type": "scratch",
                "data": {"text": "Line one\nLine two"},
            }
        ], status={})
        titled = card_render.render_image([
            {
                "slot": "full",
                "type": "scratch",
                "data": {"title": "Desk Note", "text": "Line one\nLine two"},
            }
        ], status={})

        self.assertNotEqual(
            untitled.crop((16, 16, 260, 72)).tobytes(),
            titled.crop((16, 16, 260, 72)).tobytes(),
        )


if __name__ == "__main__":
    unittest.main()
