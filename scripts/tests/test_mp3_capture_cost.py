"""Recording cost observations must preserve overlapping PCM and generations."""
from pathlib import Path
import base64
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import probe_np560_mp3_player_heap as player


class CaptureCostTests(unittest.TestCase):
    def test_preserves_same_packet_request_timing(self):
        with patch.object(player.threading.Thread, 'start'):
            capture = player.DeviceAudioCapture(None)
        timing = dict(late_ticks=7, last_deadline_ns=100, last_lateness_ns=3,
                      max_lateness_ns=12)
        packet = dict(generation=1, first_frame=0, next_frame=1,
                      sample_rate=48000, channels=2, pcm='AAAAAA==',
                      request_delivery={}, request_timing=timing)
        capture.checkpoint(packet)
        self.assertEqual(capture.delivery[0]['request_timing'], timing)
        self.assertEqual(capture.delivery[0]['next_frame'], 1)
        self.assertEqual(bytes(capture.parts[0]['data']), bytes(4))

    def test_endpoint_extends_real_tail_and_does_not_fill_missing_interval(self):
        with patch.object(player.threading.Thread, 'start'):
            capture = player.DeviceAudioCapture(None)
        def packet(first, last):
            return dict(generation=2, first_frame=first, next_frame=last,
                        sample_rate=48000, channels=2,
                        pcm=base64.b64encode(bytes(range(first*4, last*4))).decode())
        capture.checkpoint(packet(0, 5))
        capture.checkpoint(packet(3, 8))
        self.assertEqual(bytes(capture.parts[0]['data']), bytes(range(32)))
        capture.checkpoint(packet(0, 5))  # periodic reader may already be ahead
        self.assertEqual(capture.checkpoint_packets, 2)
        capture.checkpoint(packet(10, 12))
        self.assertEqual(len(capture.parts), 2)
        self.assertEqual(bytes(capture.parts[1]['data']), bytes(range(40, 48)))
        self.assertEqual(capture.cost['unique_pcm_bytes'], 40)

    def test_metrics_do_not_duplicate_or_fill_pcm(self):
        raw = bytes(range(32))
        def packet(generation, first, last, pcm):
            return dict(generation=generation, first_frame=first, next_frame=last,
                        sample_rate=48000, channels=2,
                        pcm=base64.b64encode(pcm).decode('ascii'))
        packets = [packet(2, 0, 5, raw[:20]), packet(2, 3, 8, raw[12:]),
                   packet(3, 0, 3, raw[:12])]
        with patch.object(player.threading.Thread, 'start'):
            capture = player.DeviceAudioCapture(None)
        capture.stop.wait = lambda seconds: False
        def audio():
            result = packets.pop(0)
            if not packets:
                capture.stop.set()
            return result
        capture.run(SimpleNamespace(audio=audio))
        self.assertIsNone(capture.error)
        self.assertEqual([bytes(part['data']) for part in capture.parts], [raw, raw[:12]])
        self.assertEqual(capture.cost['packets'], 3)
        self.assertEqual(capture.cost['unique_pcm_bytes'], 44)
        self.assertEqual(capture.cost['pcm_base64_chars'], 28 + 28 + 16)
        for field in ('query_wall_seconds', 'query_thread_cpu_seconds',
                      'processing_wall_seconds', 'processing_thread_cpu_seconds',
                      'total_wall_seconds', 'total_thread_cpu_seconds'):
            self.assertGreaterEqual(capture.cost[field], 0)


if __name__ == '__main__':
    unittest.main()
