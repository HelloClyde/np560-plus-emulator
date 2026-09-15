#!/usr/bin/env python3
"""Tests for the NP560 provisioning monitor."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parent))
from monitor_np560_provision import (  # noqa: E402
    decimal_field,
    outcome,
    should_stop,
    snapshot,
)


def registers(*, stage: int = 0, writes: int = 0,
              frame_writes: int = 0, invalid: str = "none") -> str:
    return f"""PC=29:c126 PSW=----
PROVISION=CALLS:1 FROM:22:9a8a SP:0fd8 STAGE:{stage} OPEN:0000:0000 RESULT:0000:0000
FILE_WRITE=CALLS:{writes} FROM:59:0412 SP:0e00 FILE:005126ac BUFFER:000d00 LENGTH:00000100 RESULT:0000:0100
FILE_COMMIT=CALLS:1 RETURNS:1 RESULT:0000:0000
CAPACITY_SCAN=CALLS:1 STAGE:10 FROM:29:0536 TO:20:f928 SP:0f88 FP:0fa0 R:0002:0000:0000:0000 RETURNS:0
REGISTRY_INIT=CALLS:1 STAGE:6 FROM:2b:2f92 TO:5f:c1a6 SP:0fb0 FP:0fca R:002f:2154 RESULT:1/1 ENTRIES:1/0 RETURNS:0
FILE_ENTRY_BUILD=CALLS:1 STAGE:4 FROM:5c:c00a TO:33:07b0 SP:0f90 FP:0fa8 RECORD:002f:2132 CHILD:2 CALLRET:2/1 RETURNS:0
APPLICATION_INIT_FRAME=ACTIVE:1 CALLS:1 WRITES:{frame_writes} FIRST:00:0000
INVALID_CONTROL={invalid}
UNSUPPORTED=none COUNT=0
"""


class ProvisionMonitorTests(unittest.TestCase):
    def test_snapshot_and_decimal_fields(self) -> None:
        current = snapshot(registers(stage=4, writes=17))
        self.assertEqual(decimal_field(current["provision"], "STAGE"), 4)
        self.assertEqual(decimal_field(current["file_write"], "CALLS"), 17)
        self.assertEqual(outcome(current), "provisioning")

    def test_complete_requires_all_chunks(self) -> None:
        self.assertEqual(outcome(snapshot(registers(stage=7, writes=256))),
                         "complete")
        self.assertEqual(outcome(snapshot(registers(stage=7, writes=255))),
                         "incomplete-write-count")

    def test_incidents_take_priority(self) -> None:
        current = snapshot(registers(
            stage=4, writes=12, invalid="29:c3be/c620>ff:ffff SP=0fd8 FP=ffff IRQ=0"
        ))
        self.assertEqual(outcome(current), "invalid-control")
        self.assertTrue(should_stop("terminal", outcome(current)))
        self.assertTrue(should_stop("incident", outcome(current)))

    def test_frame_overwrite_is_terminal(self) -> None:
        result = outcome(snapshot(registers(frame_writes=1)))
        self.assertEqual(result, "frame-overwrite")
        self.assertTrue(should_stop("complete", result))


if __name__ == "__main__":
    unittest.main()
