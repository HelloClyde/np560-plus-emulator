import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).with_name("monitor_np560_game_draw.py")
SPEC = importlib.util.spec_from_file_location("monitor_np560_game_draw", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MonitorGameDrawTest(unittest.TestCase):
    def test_selects_draw_line_and_call_number(self) -> None:
        registers = (
            "PC=29:be8a\n"
            "NPE_GAME_LOOP=DRAW:6/4\n"
            "NPE_GAME_DRAW_TRACE=ACTIVE:0 CALL:6 EDGES:9 TRACE:#1\n"
        )
        line = MODULE.select_line(registers, "NPE_GAME_DRAW_TRACE=")
        match = MODULE.DRAW_RE.search(line)
        self.assertIsNotNone(match)
        assert match
        self.assertEqual(int(match.group(1)), 6)

    def test_missing_prefix_is_empty(self) -> None:
        self.assertEqual(MODULE.select_line("PC=00:0000", "NPE_GAME_LOOP="), "")


if __name__ == "__main__":
    unittest.main()
