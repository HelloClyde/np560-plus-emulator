import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from probe_np560_mobivoice_sp_decoder import (
    candidate_bytes, decode_fresh_context, encoded_frames,
)


class MobiVoiceProbeInputTests(unittest.TestCase):
    def test_each_frame_uses_next_compressed_bytes(self):
        encoded = bytes(range(63))
        frames = list(encoded_frames(encoded, 21, 4))
        self.assertEqual([index for index, _ in frames], [0, 1, 2])
        self.assertEqual([frame[0] for _, frame in frames], [0, 21, 42])
        self.assertEqual([len(frame) for _, frame in frames], [21, 21, 21])

    def test_incomplete_trailing_frame_is_not_decoded(self):
        self.assertEqual(list(encoded_frames(bytes(range(22)), 21, 2)),
                         [(0, bytes(range(21)))])

    def test_swap16_preserves_odd_trailing_byte(self):
        self.assertEqual(candidate_bytes(b"\x12\x34\x56\x78\x9a", "swap16", 0),
                         b"\x34\x12\x78\x56\x9a")

    def test_swap16_continues_across_odd_frame_boundary(self):
        transformed = candidate_bytes(bytes(range(42)), "swap16", 0)
        self.assertEqual(transformed[20:22], bytes((21, 20)))

    def test_bit_offset_is_applied_after_byte_swap(self):
        self.assertEqual(candidate_bytes(b"\x12\x34\x56", "swap16", 1),
                         b"\x68\x24")

    def test_invalid_frame_bounds_rejected(self):
        with self.assertRaises(ValueError):
            list(encoded_frames(b"abc", 0, 1))
        with self.assertRaises(ValueError):
            list(encoded_frames(b"abc", 2, -1))

    def test_fresh_control_reinitializes_each_frame(self):
        created = []

        class FakeDecoder:
            def __init__(self):
                created.append(self)
                self.calls = 0

            def init(self, mode):
                self.assert_mode = mode
                return 1, 168

            def decode(self, frame, context):
                self.calls += 1
                return 160, bytes((frame[0], 0)) * 160

        self.assertEqual(decode_fresh_context(FakeDecoder, 5, b"\x34" * 21),
                         b"\x34\x00" * 160)
        self.assertEqual(decode_fresh_context(FakeDecoder, 5, b"\x56" * 21),
                         b"\x56\x00" * 160)
        self.assertEqual(len(created), 2)
        self.assertEqual([decoder.calls for decoder in created], [1, 1])
        self.assertEqual([decoder.assert_mode for decoder in created], [5, 5])

    def test_fresh_control_rejects_wrong_frame_spec(self):
        class WrongSpec:
            def init(self, mode):
                return 1, 160

        with self.assertRaisesRegex(ValueError, "frame specification"):
            decode_fresh_context(WrongSpec, 5, b"\x00" * 21)


if __name__ == "__main__":
    unittest.main()
