import unittest
from pathlib import Path

from tools.push_paper_s3_test_frame import (
    FRAME_BYTES,
    FRAME_H,
    FRAME_W,
    build_chunk_command,
    build_raw_begin_command,
    DEFAULT_MODE,
    iter_chunks,
    make_test_pixels,
    pack_luma_to_4bpp,
    parse_frame_chunk_ack,
    parse_status_line,
    should_print_device_line,
)


class PaperS3PushToolTest(unittest.TestCase):
    def test_paper_s3_hal_uses_quality_epd_mode_for_full_frame_refresh(self):
        source = Path("src/paper_s3/paper_s3_hw.cpp").read_text()

        self.assertIn("setEpdMode(epd_mode_t::epd_quality)", source)
        self.assertNotIn("setEpdMode(epd_mode_t::epd_fastest)", source)

    def test_pack_luma_to_4bpp_uses_high_nibble_first_and_m5epd_gray(self):
        pixels = bytes([255, 0, 128, 17])

        packed = pack_luma_to_4bpp(2, 2, pixels)

        self.assertEqual(packed, bytes([0x0F, 0x7E]))

    def test_make_test_pixels_has_full_logical_frame_size(self):
        pixels = make_test_pixels()

        self.assertEqual(len(pixels), FRAME_W * FRAME_H)
        self.assertEqual(len(pack_luma_to_4bpp(FRAME_W, FRAME_H, pixels)), FRAME_BYTES)

    def test_iter_chunks_preserves_sequence_and_payload(self):
        chunks = list(iter_chunks(b"abcdef", 4))

        self.assertEqual(chunks, [(0, b"abcd"), (1, b"ef")])

    def test_parse_status_line_returns_status_json_only(self):
        line = (
            '{"ack":"status","device":"M5Stack PaperS3",'
            '"frame_state":"ready","uptime_s":12}'
        )

        self.assertEqual(parse_status_line(line)["frame_state"], "ready")
        self.assertIsNone(parse_status_line("[frame] begin fid=1"))

    def test_default_chunk_json_line_stays_serial_friendly(self):
        seq, chunk = next(iter_chunks(bytes(range(256)) * 8))

        line = build_chunk_command(123, seq, chunk)

        self.assertLess(len(line), 1024)

    def test_parse_frame_chunk_ack_matches_fid_and_seq(self):
        line = '{"ack":"frame_chunk","fid":123,"seq":7,"bytes":4096}'

        self.assertTrue(parse_frame_chunk_ack(line, 123, 7))
        self.assertFalse(parse_frame_chunk_ack(line, 123, 8))
        self.assertFalse(parse_frame_chunk_ack('{"ack":"status"}', 123, 7))

    def test_should_suppress_noisy_per_chunk_lines(self):
        self.assertFalse(should_print_device_line("[rx] cmd=frame_chunk"))
        self.assertFalse(should_print_device_line(
            '{"ack":"frame_chunk","fid":123,"seq":7,"bytes":4096}'))
        self.assertTrue(should_print_device_line("[display] update start"))

    def test_default_mode_is_raw_and_raw_begin_is_short_json(self):
        line = build_raw_begin_command(123, FRAME_BYTES, 0xDEC1FC92)

        self.assertEqual(DEFAULT_MODE, "raw")
        self.assertLess(len(line), 160)
        self.assertIn(b'"cmd":"frame_raw_begin"', line)
        self.assertIn(b'"bytes":259200', line)


if __name__ == "__main__":
    unittest.main()
