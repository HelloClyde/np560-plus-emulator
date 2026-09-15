
# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))

import unittest

from scripts.monitor_np560_modal_dispatch import find_diagnostic, summarize


SAMPLE = (
    "NPE_CONTROL_TRACE=COUNT:4 FROZEN:1 PENDING:0 ACTIVE:0 "
    "CALLER:2f:c23a RESULT:0001 OUTPUTS:1 TYPE:0001 CODE:0086 "
    "DECODER:1@2d:be5e/R0086 TRACE:"
    "#1/1e:fd7a>2f:c23a/wc620/sp0c48/fp0c62,"
    "#2/2f:c304>2c:d350/wbd2c/sp0c50/fp0c62,"
    "#3/2c:d52e>2f:c308/wc620/sp0c4a/fp0c62,"
    "#4/2f:c340>2d:be5e/wc620/sp0c58/fp0c62"
)


class ModalDispatchMonitorTests(unittest.TestCase):
    def test_find_and_summarize_completed_dispatch(self) -> None:
        self.assertEqual(find_diagnostic("A=1\n" + SAMPLE + "\nB=2"), SAMPLE)
        summary = summarize(SAMPLE)
        self.assertIn(
            "count=4 frozen=1 pending=0 active=0 retained=4", summary
        )
        self.assertIn(
            "modal event 0x86 return=1e:fd7a>2f:c23a result=0001 "
            "outputs=1 type=0001 code=0086", summary
        )
        self.assertIn("event decoder return=1@2d:be5e result=0086", summary)
        self.assertIn("last transfer=#4 2f:c340>2d:be5e", summary)

    def test_waiting_state(self) -> None:
        summary = summarize(
            "NPE_CONTROL_TRACE=COUNT:0 FROZEN:0 PENDING:0 ACTIVE:0 "
            "CALLER:00:0000 RESULT:0000 OUTPUTS:0 TYPE:0000 CODE:0000 "
            "DECODER:0@00:0000/R0000 TRACE:none"
        )
        self.assertIn("modal event 0x86 return=pending", summary)
        self.assertIn("waiting for modal event 0x86", summary)


if __name__ == "__main__":
    unittest.main()
