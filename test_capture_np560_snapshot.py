import base64
import importlib.util
from pathlib import Path
import sys
import unittest


MODULE_PATH = Path(__file__).with_name("capture_np560_snapshot.py")
SPEC = importlib.util.spec_from_file_location("capture_np560_snapshot", MODULE_PATH)
assert SPEC and SPEC.loader
snapshot = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = snapshot
SPEC.loader.exec_module(snapshot)

compact_diagnostics = snapshot.compact_diagnostics
decode_gray5 = snapshot.decode_gray5


class SnapshotTests(unittest.TestCase):
    def test_decode_gray5_masks_and_scales_levels(self) -> None:
        state = {
            "format": "gray5", "width": 2, "height": 1,
            "frame": base64.b64encode(bytes((0, 0x3f))).decode("ascii"),
        }
        self.assertEqual(list(decode_gray5(state).getdata()), [0, 255])

    def test_compact_diagnostics_discards_bulk_lines(self) -> None:
        text = "PC=29:c538\nR0 =1234\nFAR_COPY_BAD=none\n"
        self.assertEqual(
            compact_diagnostics(text),
            ["PC=29:c538", "FAR_COPY_BAD=none"],
        )


if __name__ == "__main__":
    unittest.main()
