import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import burn_np560_stream as burn


class BurnDiagnosticsTests(unittest.TestCase):
    def test_state_capture_is_bounded_and_preserves_context(self):
        emulator = Mock()
        emulator.process.poll.return_value = None
        emulator.qmp.execute.return_value = "sample"
        with tempfile.TemporaryDirectory() as name, \
                patch.object(burn, "storage_guard_state", return_value="guard"):
            path = Path(name) / "state.json"
            burn.capture_diagnostics(emulator, path, completed_bytes=512)
            result = json.loads(path.read_text())
            self.assertEqual(result["completed_bytes"], 512)
            self.assertEqual(result["cpu-state"], "sample")
            self.assertEqual(result["storage_guard"], "guard")
            self.assertTrue(all(call.kwargs["timeout"] == 5.0
                                for call in emulator.qmp.execute.call_args_list))

    def test_failed_transport_still_leaves_failure_report(self):
        emulator = Mock()
        emulator.process.poll.return_value = None
        emulator.qmp.execute.side_effect = RuntimeError("disconnected")
        with tempfile.TemporaryDirectory() as name, \
                patch.object(burn, "storage_guard_state", side_effect=RuntimeError("gone")):
            path = Path(name) / "failure.json"
            burn.capture_diagnostics(emulator, path, error="original error")
            result = json.loads(path.read_text())
            self.assertEqual(result["error"], "original error")
            self.assertEqual(result["cpu-state-error"], "disconnected")

    def test_exited_process_is_not_queried(self):
        emulator = Mock()
        emulator.process.poll.return_value = -6
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "exit.json"
            burn.capture_diagnostics(emulator, path)
            self.assertEqual(json.loads(path.read_text())["qemu_returncode"], -6)
        emulator.qmp.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
