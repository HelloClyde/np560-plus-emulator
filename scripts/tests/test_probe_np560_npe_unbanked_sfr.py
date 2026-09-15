#!/usr/bin/env python3
"""Unit tests for the NPE unbanked-SFR differential probe."""

from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import unittest

try:
    from probe_np560_npe_unbanked_sfr import (
        parse_banked_inventory,
        direct_inventory_delta,
        inventory_delta,
        parse_direct_inventory,
        parse_sfr_inventory,
        parse_stream_position_inventory,
        parse_stream_io_trace,
        parse_high_stream_io_trace,
        parse_transition_leaf_trace,
        parse_stream_resolve_trace,
        stream_position_delta,
    )
except ModuleNotFoundError:
    from .probe_np560_npe_unbanked_sfr import (
        parse_banked_inventory,
        direct_inventory_delta,
        inventory_delta,
        parse_direct_inventory,
        parse_sfr_inventory,
        parse_stream_position_inventory,
        parse_stream_io_trace,
        parse_high_stream_io_trace,
        parse_transition_leaf_trace,
        parse_stream_resolve_trace,
        stream_position_delta,
    )


class SfrInventoryTests(unittest.TestCase):
    def test_parse_and_delta(self) -> None:
        before = parse_sfr_inventory(
            "UNBANKED_SFR_WRITE=TOTAL:5 UNKNOWN:1 "
            "BUCKETS:F0=0,F1=4,F2=0,F3=0,F4=0,F5=0,F6=0,F7=0,"
            "F8=1,F9=0,Fa=0,Fb=0,Fc=0,Fd=0,Fe=0,Ff=0 "
            "TRACE:#0/g4/20:0010/af800=1234/b16/spfffe/fp0000/"
            "ds000,001/i0\n"
        )
        after = parse_sfr_inventory(
            "UNBANKED_SFR_WRITE=TOTAL:8 UNKNOWN:2 "
            "BUCKETS:F0=0,F1=6,F2=0,F3=0,F4=0,F5=0,F6=0,F7=0,"
            "F8=2,F9=0,Fa=0,Fb=0,Fc=0,Fd=0,Fe=0,Ff=0 "
            "TRACE:#0/g4/20:0010/af800=1234/b16/spfffe/fp0000/"
            "ds000,001/i0;#1/g7/21:0020/af802=5678/b16/spfff0/"
            "fp0010/ds000,001/i0\n"
        )
        delta = inventory_delta({"sfr": before}, {"sfr": after})
        self.assertEqual(delta["total"], 3)
        self.assertEqual(delta["unknown"], 1)
        self.assertEqual(delta["buckets"]["F1"], 2)
        self.assertEqual(delta["buckets"]["F8"], 1)
        self.assertEqual(len(delta["new_unknown_trace"]), 1)
        self.assertIn("af802=5678", delta["new_unknown_trace"][0])

        banked = parse_banked_inventory(
            after["line"].replace(
                "UNBANKED_SFR_WRITE", "BANKED_FXXX_WRITE"
            )
        )
        self.assertEqual(banked["total"], 8)
        self.assertEqual(banked["unknown"], 2)

    def test_rejects_incomplete_buckets(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            parse_sfr_inventory(
                "UNBANKED_SFR_WRITE=TOTAL:0 UNKNOWN:0 "
                "BUCKETS:F0=0 TRACE:none\n"
            )

    def test_parse_direct_inventory_and_delta(self) -> None:
        before = parse_direct_inventory(
            "DIRECT_SFR_WRITE=TOTAL:3 COUNTS:27=1,39=1,41=1 "
            "TRACE:#0/g0/20:0010/r27=0000>c080/b16/spfffe/fp0000/"
            "ds000,001/i0;#1/g1/20:0014/r39=0000>8000/b16/"
            "spfffe/fp0000/ds000,001/i0;#2/g2/20:0018/"
            "r41=0000>0000/b16/spfffe/fp0000/ds000,001/i0\n"
        )
        after = parse_direct_inventory(
            "DIRECT_SFR_WRITE=TOTAL:5 COUNTS:27=2,39=1,41=1,72=1 "
            "TRACE:#0/g0/20:0010/r27=0000>c080/b16/spfffe/fp0000/"
            "ds000,001/i0;#1/g1/20:0014/r39=0000>8000/b16/"
            "spfffe/fp0000/ds000,001/i0;#2/g2/20:0018/"
            "r41=0000>0000/b16/spfffe/fp0000/ds000,001/i0;"
            "#3/g3/21:0020/r72=0000>1234/b16/spfff0/fp0010/"
            "ds000,001/i1;#4/g4/21:0024/r27=c080>c081/b16/"
            "spfff0/fp0010/ds000,001/i1\n"
        )
        delta = direct_inventory_delta(
            {"direct_sfr": before}, {"direct_sfr": after}
        )
        self.assertEqual(delta["total"], 2)
        self.assertEqual(delta["counts"], {"27": 1, "72": 1})
        self.assertTrue(delta["trace_complete"])
        self.assertEqual(len(delta["new_trace"]), 2)
        self.assertIn("r72=0000>1234", delta["new_trace"][0])

    def test_parse_stream_position_inventory_and_delta(self) -> None:
        before = parse_stream_position_inventory(
            "NPE_STREAM_POSITION=CALLS:832 RETURNS:832 CHANGED:820 "
            "REVERSE:2 RANGE:00000000-00003f20 REQUESTED:15000 "
            "ADVANCED:14900 PAGES:4 TRACE:000=5,001=8,002=3,003=1\n"
        )
        after = parse_stream_position_inventory(
            "NPE_STREAM_POSITION=CALLS:836 RETURNS:836 CHANGED:824 "
            "REVERSE:2 RANGE:00000000-00009000 REQUESTED:15100 "
            "ADVANCED:15000 PAGES:6 TRACE:000=5,001=9,002=3,003=1,"
            "008=2,009=1\n"
        )
        delta = stream_position_delta(
            {"stream_position": before}, {"stream_position": after}
        )
        self.assertEqual(delta["calls"], 4)
        self.assertEqual(delta["requested_bytes"], 100)
        self.assertEqual(
            delta["page_calls"], {"001": 1, "008": 2, "009": 1}
        )
        self.assertEqual(delta["range_end"], 0x9000)

    def test_rejects_incomplete_stream_page_inventory(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "does not match"):
            parse_stream_position_inventory(
                "NPE_STREAM_POSITION=CALLS:1 RETURNS:1 CHANGED:1 "
                "REVERSE:0 RANGE:00001000-00001002 REQUESTED:2 "
                "ADVANCED:2 PAGES:2 TRACE:001=1\n"
            )

    def test_parse_stream_io_trace(self) -> None:
        registers = (
            "NPE_GAME_TABLE=LIVE:0/00000000 STREAM:2/2/A0/M2:2/T0 "
            "TRACE:#1/0c:d0dc/s0050fe74/d00526ca2/n0002/"
            "p0012a133>0012a135/m1c:ccd4/r0002:fe74/e0000/w2,"
            "#2/22:c7fc/s0050fe74/d005273bd/n0001/"
            "p00090af8>00090af9/m1c:ccd4/r0001:fe74/e0000/w0\n"
        )
        entries = parse_stream_io_trace(registers)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["caller"], "0C:D0DC")
        self.assertEqual(entries[0]["position_before"], 0x12A133)
        self.assertEqual(entries[1]["destination"], 0x5273BD)
        self.assertEqual(entries[1]["length"], 1)

    def test_parse_stream_resolve_trace(self) -> None:
        registers = (
            "NPE_STREAM_RESOLVE=CALLS:2 RETURNS:2 ACTIVE:0 TRACE:"
            "#1/29:5d84/s50fe74/o00003afa/w0000/"
            "p00002e12>00003afa/r0000:fe74/e0000,"
            "#2/2e:7316/s50fe74/o00000010/w0001/"
            "p00003afa>00003b0a/r0000:fe74/e0000\n"
        )
        parsed = parse_stream_resolve_trace(registers)
        self.assertEqual(parsed["calls"], 2)
        self.assertFalse(parsed["active"])
        self.assertEqual(parsed["trace"][0]["caller"], "29:5D84")
        self.assertEqual(parsed["trace"][0]["position_after"], 0x3AFA)
        self.assertEqual(parsed["trace"][1]["whence"], 1)

    def test_parse_high_stream_io_trace(self) -> None:
        registers = (
            "NPE_HIGH_STREAM_IO=CALLS:4 RETURNS:4 ACTIVE:0 TRACE:"
            "#1/24:ad92/d000de6/n0004/"
            "p0013291a>0013291e/r0004:fe74/e0000,"
            "#2/24:adb8/d000deb/n0001/"
            "p0013291e>0013291f/r0001:fe74/e0000,"
            "#3/24:ae42/d000de2/n0004/"
            "p00132b0e>00132b12/r0004:fe74/e0000,"
            "#4/24:ae68/d000dec/n0004/"
            "p00132b12>00132b16/r0004:fe74/e0000\n"
        )
        parsed = parse_high_stream_io_trace(registers)
        self.assertEqual(parsed["calls"], 4)
        self.assertEqual(parsed["returns"], 4)
        self.assertFalse(parsed["active"])
        self.assertEqual(parsed["trace"][0]["caller"], "24:AD92")
        self.assertEqual(parsed["trace"][0]["position_before"], 0x13291A)
        self.assertEqual(parsed["trace"][1]["length"], 1)
        self.assertEqual(parsed["trace"][3]["destination"], 0xDEC)
        self.assertEqual(parsed["trace"][3]["position_after"], 0x132B16)

    def test_parse_transition_leaf_trace(self) -> None:
        registers = (
            "NPE_TRANSITION_LEAF=CALLS:2 RETURNS:1 LOW:1 HIGH:1 TRACE:"
            "#1/32:b9b8/sp0d00/s0000/f0003/"
            "a0050,fe74,001b,fad8,0000,0000/bL/r0000,"
            "#2/31:a480/sp0ce0/s0001/f0007/"
            "a0050,fe74,001f,325a,0000,0000/bH/rfffd\n"
        )
        parsed = parse_transition_leaf_trace(registers)
        self.assertEqual(parsed["calls"], 2)
        self.assertEqual(parsed["returns"], 1)
        self.assertEqual(parsed["low"], 1)
        self.assertEqual(parsed["high"], 1)
        self.assertEqual(parsed["trace"][0]["caller"], "32:B9B8")
        self.assertEqual(parsed["trace"][0]["format"], 3)
        self.assertEqual(parsed["trace"][0]["args"][2], 0x1B)
        self.assertEqual(parsed["trace"][1]["branch"], "H")
        self.assertEqual(parsed["trace"][1]["result"], 0xFFFD)


if __name__ == "__main__":
    unittest.main()
