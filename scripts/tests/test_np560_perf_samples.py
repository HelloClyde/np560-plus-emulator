"""Check stopped perf record decoding, loss accounting and corrupt input rejection."""
import struct
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from probe_np560_perf_samples import decode_records


class Records(unittest.TestCase):
    def test_sample_and_loss(self):
        data = struct.pack('<IHHQII', 9, 2, 24, 0x123456789, 100, 101)
        data += struct.pack('<IHHQQ', 2, 0, 24, 8, 11)
        data += struct.pack('<IHH', 3, 0, 8)
        result = decode_records(data)
        self.assertEqual(result['samples'], [dict(ip=0x123456789, pid=100, tid=101, misc=2)])
        self.assertEqual(result['lost'], 11)
        self.assertEqual(result['other_records'], {3: 1})

    def test_invalid(self):
        for data in (b'x', struct.pack('<IHH', 9, 0, 0),
                     struct.pack('<IHH', 9, 0, 24),
                     struct.pack('<IHH', 9, 0, 8),
                     struct.pack('<IHH', 2, 0, 8)):
            with self.subTest(data=data), self.assertRaises(ValueError):
                decode_records(data)

    def test_empty(self):
        self.assertEqual(decode_records(b''), dict(samples=[], lost=0, other_records={}))


if __name__ == '__main__':
    unittest.main()
