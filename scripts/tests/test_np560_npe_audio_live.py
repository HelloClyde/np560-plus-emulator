import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from probe_np560_npe_audio_live import (
    audio_clock_progress, control_transitions, guest_dac_off_windows,
    hle_count_delta, map_advance, npe_game_control_state, npe_load_rom_state,
)


class NPEAudioLiveTests(unittest.TestCase):
    def test_load_rom_trace_summarizes_unique_resident_targets(self):
        state = npe_load_rom_state({"registers": (
            "NPE_LOAD_ROM=ACTIVE:0 ENTER:1 EXIT:1 READ:1/R0001 "
            "SLOT:0 FLAGS:0008,0000,0000 TRIGGER:0000>0000 "
            "CALLS:600 UNIQUE:3 TRACE:"
            "#1/call/1e:7f52>02:bbf6/n200;"
            "#2/call/02:bc48>02:6000/n200;"
            "#3/call/02:bc54>02:6200/n200\n"
        )})
        self.assertTrue(state["parsed"])
        self.assertEqual(state["read_result"], 1)
        self.assertEqual(state["slot_flags"], [8, 0, 0])
        self.assertEqual(state["rom_calls"], 600)
        self.assertEqual(state["unique_rom_targets"], 3)
        self.assertEqual(len(state["rom_targets"]), 3)
        self.assertIsNone(npe_load_rom_state({"registers": "PC=1D:8FA4"}))

    def test_npe_control_trace_exposes_live_words_and_guest_stores(self):
        state = npe_game_control_state({"registers": (
            "PC=1D:8FA4\n"
            "NPE_GAME_CONTROL=LIVE:m0001/g0001/t0000 "
            "OP1:0/0/F0/R0/N0/I0/X0 WRITES:21 TRACE:"
            "#20/1d:8fa4/l7934/p527934/0007>0001/b16;"
            "#21/1f:4396/l7934/p527934/0001>0001/b16\n"
        )})
        self.assertTrue(state["parsed"])
        self.assertEqual(state["live"],
                         {"mode": 1, "gate": 1, "trigger": 0})
        self.assertEqual(state["write_count"], 21)
        self.assertEqual(len(state["recent_writes"]), 2)
        self.assertIsNone(npe_game_control_state({"registers": "PC=1D:8FA4"}))

    def test_hle_call_delta_keeps_service_order(self):
        result = hle_count_delta(
            {"state": "experimental calls=1,2,3,4,5,6 decoded=4"},
            {"state": "experimental calls=2,4,7,8,10,12 decoded=8"},
        )
        self.assertEqual(result["order"],
                         ["ACD8", "B6DE", "B816", "B7AA", "B84E", "AD92"])
        self.assertEqual(result["delta"], [1, 2, 4, 4, 5, 6])
        self.assertIsNone(hle_count_delta({"state": "disabled"},
                                           {"state": "disabled"}))

    def test_http_key_acceptance_does_not_imply_guest_event(self):
        result = map_advance({"maps": 17}, {"maps": 17, "event": 134})
        self.assertFalse(result["guest_maps_advanced"])
        self.assertEqual(result["guest_maps_before"], 17)

    def test_guest_map_counter_advance_is_recorded(self):
        result = map_advance({"maps": 17}, {"maps": 18, "event": 134})
        self.assertTrue(result["guest_maps_advanced"])
        self.assertEqual(result["guest_maps_after"], 18)
        self.assertEqual(result["guest_last_event"], 134)

    def test_active_dac_media_rate_uses_elapsed_counter_not_capture_length(self):
        items = [
            {"monotonic_time": 10.0, "generation": 2, "next_frame": 9600,
             "enabled": True, "running": True},
            {"monotonic_time": 18.0, "generation": 2, "next_frame": 369600,
             "enabled": True, "running": True},
        ]
        result = audio_clock_progress(items, [])
        self.assertEqual(result["wall_seconds"], 8.0)
        self.assertEqual(result["dac_media_seconds"], 7.5)
        self.assertEqual(result["frame_clock_rate"], 0.9375)
        self.assertEqual(result["dac_media_rate"], 0.9375)

    def test_inactive_or_discontinuous_window_has_no_speed_claim(self):
        items = [
            {"monotonic_time": 10.0, "generation": 2, "next_frame": 0,
             "enabled": True, "running": True},
            {"monotonic_time": 11.0, "generation": 2, "next_frame": 48000,
             "enabled": False, "running": False},
        ]
        result = audio_clock_progress(items, [])
        self.assertIsNone(result["dac_media_rate"])
        self.assertEqual(result["frame_clock_rate"], 1.0)
        self.assertEqual(result["active_sample_count"], 1)
        items[1]["enabled"] = items[1]["running"] = True
        self.assertIsNone(audio_clock_progress(items, [[12, 13]])["frame_clock_rate"])
        items[1]["generation"] = 3
        self.assertIsNone(audio_clock_progress(items, [])["frame_clock_rate"])

    def test_guest_dac_edges_pair_into_off_window(self):
        def event(sequence, frame, old, new):
            return dict(sequence=sequence, virtual_ns=frame * 100,
                        frame=frame, pc=0x8478e if new & 0x8000 else 0x84718,
                        reg=0x72, old_value=old, value=new,
                        enabled=(new & 0x8001) == 1,
                        running=(new & 0x8001) == 1)

        packet = dict(control_event_next=6, control_events=[
            event(3, 100, 0x000b, 0x800b),
            event(4, 200, 0x800b, 0x800a),
            event(5, 3400, 0x800b, 0x000b),
        ])
        last, edges, missed = control_transitions(packet, 2)
        self.assertEqual(last, 5)
        self.assertFalse(missed)
        self.assertEqual([edge["sequence"] for edge in edges], [3, 5])
        self.assertEqual(guest_dac_off_windows(edges, [])[0]["frames"], 3300)

    def test_control_ring_overrun_is_not_a_continuous_window(self):
        off = dict(sequence=3, frame=100, pc=1, enabled=False)
        on = dict(sequence=70, frame=3400, pc=2, enabled=True)
        packet = dict(control_event_next=71, control_events=[
            dict(on, reg=0x72, old_value=0x800b,
                 value=0x000b, virtual_ns=0, running=True),
        ])
        last, edges, missed = control_transitions(packet, 3)
        self.assertEqual(last, 70)
        self.assertTrue(missed)
        self.assertEqual(guest_dac_off_windows(
            [off, on], [{"after_sequence": 3, "next_sequence": 71}]), [])
        last, edges, missed = control_transitions(
            {"control_event_next": 0, "control_events": []}, 70)
        self.assertEqual(last, -1)
        self.assertEqual(edges, [])
        self.assertTrue(missed)


if __name__ == "__main__":
    unittest.main()
