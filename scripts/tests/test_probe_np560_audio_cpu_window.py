"""Accounting invariants for the read-only live audio CPU probe."""

import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from probe_np560_audio_cpu_window import delta


def point(when, ticks, frame, *, start_ticks=10, generation=2):
    return {
        "time": when,
        "processes": {name: {
            "start_ticks": start_ticks,
            "user_ticks": count,
            "system_ticks": 0,
        } for name, count in ticks.items()},
        "audio": {"stream_id": "device", "generation": generation,
                  "next_frame": frame},
    }


class AudioCPUWindowTests(unittest.TestCase):
    def test_distinguishes_device_speed_from_process_cpu(self):
        first = point(10, {"qemu": 10, "codec": 20, "bridge": 30}, 1000)
        last = point(12, {"qemu": 190, "codec": 30, "bridge": 34}, 97000)
        result = delta(first, last, ticks_per_second=100)
        self.assertEqual(result["device_speed_ratio"], 1.0)
        self.assertEqual(result["cpu_wall_ratio"], {
            "qemu": 0.9, "codec": 0.05, "bridge": 0.02})

    def test_rejects_replaced_process_and_audio_stream(self):
        first = point(10, {"qemu": 10}, 1000)
        with self.assertRaisesRegex(ValueError, "replaced"):
            delta(first, point(11, {"qemu": 100}, 49000, start_ticks=11), 100)
        with self.assertRaisesRegex(ValueError, "stream changed"):
            delta(first, point(11, {"qemu": 100}, 49000, generation=3), 100)


if __name__ == "__main__":
    unittest.main()
