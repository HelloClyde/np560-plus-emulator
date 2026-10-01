#!/usr/bin/env python3
"""Check lifecycle evidence and failure cleanup without touching a live guest."""

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from web import np560_web as web


class WebLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_aborted_stream_read_does_not_send_a_second_response(self):
        for failure in (BrokenPipeError, ConnectionResetError):
            for phase in ("headers", "body"):
                handler = Mock()
                target = handler.end_headers if phase == "headers" else handler.wfile.write
                target.side_effect = failure("browser canceled read")
                web.RequestHandler._json(handler, {"pcm": ""})
                handler.send_response.assert_called_once()
                handler.end_headers.assert_called_once()
                handler._error.assert_not_called()

    def test_response_errors_other_than_disconnect_still_surface(self):
        handler = Mock()
        handler.wfile.write.side_effect = OSError("unexpected write failure")
        with self.assertRaisesRegex(OSError, "unexpected write failure"):
            web.RequestHandler._json(handler, {})

    def test_journal_runs_do_not_overwrite_and_preserve_terminal_status(self):
        first = web.RunJournal(self.root, port=8808)
        first.record("qemu_exited", qemu_returncode=7, unexpected_qemu_exit=True)
        second = web.RunJournal(self.root, port=8808)
        self.assertNotEqual(first.directory, second.directory)
        status = json.loads((first.directory / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["qemu_returncode"], 7)
        events = [json.loads(line) for line in
                  (first.directory / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([item["event"] for item in events],
                         ["bridge_starting", "qemu_exited"])

    def test_full_disk_retains_in_memory_evidence_without_raising(self):
        journal = web.RunJournal(self.root)
        with patch.object(Path, "open", side_effect=OSError("disk full")):
            journal.record("qemu_exited", qemu_returncode=9)
        self.assertEqual(journal.snapshot()["qemu_returncode"], 9)
        self.assertEqual(journal.snapshot()["journal_error"], "disk full")

    def test_close_interrupts_a_blocked_qmp_reader(self):
        client_socket, peer = socket.socketpair()
        self.addCleanup(peer.close)
        client = web.QMPClient(self.root / "unused.qmp")
        client.sock = client_socket
        client.stream = client_socket.makefile("rwb", buffering=65536)
        self.addCleanup(client.close)
        result = []

        def request():
            try:
                client.execute("query-status")
            except web.QMPError as error:
                result.append(str(error))

        worker = threading.Thread(target=request, daemon=True)
        worker.start()
        peer.settimeout(2)
        self.assertIn(b"query-status", peer.recv(1024))
        client.close()
        worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(result), 1)
        self.assertRegex(result[0], r"QMP (connection closed|is not connected|read failed:)")

    @unittest.skipUnless(sys.platform == "win32", "Windows socket shutdown race")
    def test_windows_qmp_close_race_is_bounded(self):
        # A single close often succeeds. Repeated real socketpair/read/close
        # cycles exposed a 120-second stall; keep a process deadline so a
        # regression cannot hang this test runner in BufferedRWPair.close().
        script = (
            "import sys, unittest; "
            f"sys.path.insert(0, {str(Path(__file__).resolve().parent)!r}); "
            "from test_np560_web_lifecycle import WebLifecycleTests; "
            "suite = unittest.TestSuite(WebLifecycleTests("
            "'test_close_interrupts_a_blocked_qmp_reader') for _ in range(200)); "
            "result = unittest.TextTestRunner().run(suite); "
            "sys.exit(not result.wasSuccessful())"
        )
        result = subprocess.run([sys.executable, "-c", script],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_refused_connect_closes_each_socket(self):
        connection = Mock()
        connection.connect.side_effect = FileNotFoundError()
        with patch.object(web.socket, "AF_UNIX", 1, create=True), \
                patch.object(web.socket, "socket", return_value=connection), \
                patch.object(web.time, "monotonic", side_effect=[0, 0, 0, 10]), \
                patch.object(web.time, "sleep"):
            with self.assertRaisesRegex(web.QMPError, "did not open"):
                web.QMPClient(self.root / "missing.qmp").connect(timeout=1)
        connection.close.assert_called_once()

    def test_command_timeout_disconnects_without_claiming_command_failed(self):
        client_socket, peer = socket.socketpair()
        self.addCleanup(peer.close)
        client = web.QMPClient(self.root / "unused.qmp")
        client.sock = client_socket
        client.stream = client_socket.makefile("rwb", buffering=65536)
        self.addCleanup(client.close)
        with self.assertRaisesRegex(web.QMPError, "outcome unknown"):
            client.execute("query-status", timeout=0.02)
        self.assertIsNone(client.sock)
        self.assertFalse(client.lock.locked())
        peer.settimeout(2)
        self.assertIn(b"query-status", peer.recv(1024))

    def test_buffered_qmp_flushes_commands_and_reads_large_event_interleaved_replies(self):
        client_socket, peer = socket.socketpair()
        client_socket.settimeout(2)
        peer.settimeout(2)
        self.addCleanup(peer.close)
        client = web.QMPClient(self.root / 'unused.qmp')
        client.sock = client_socket
        client.stream = client_socket.makefile('rwb', buffering=65536)
        self.addCleanup(client.close)
        payload = 'A' * 180000
        failures = []
        def server():
            try:
                with peer.makefile('rwb', buffering=65536) as stream:
                    for _ in range(2):
                        request = json.loads(stream.readline())
                        stream.write(b'{"event":"STOP"}\n')
                        stream.write(json.dumps({'id': request['id'], 'return': payload}).encode() + b'\n')
                        stream.flush()
            except Exception as error:
                failures.append(error)
        worker = threading.Thread(target=server, daemon=True)
        worker.start()
        for _ in range(2):
            self.assertEqual(client.execute('qom-get', {'path': '/machine', 'property': 'audio-pcm'}), payload)
        worker.join(timeout=3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(failures, [])

    def test_busy_qmp_does_not_send_or_close_in_flight_transport(self):
        client = web.QMPClient(self.root / "unused.qmp")
        client.stream = Mock()
        client.lock.acquire()
        try:
            with self.assertRaisesRegex(web.QMPError, "command was not sent"):
                client.execute("qom-set", timeout=0.01)
            self.assertEqual(client.stream.mock_calls, [])
        finally:
            client.lock.release()

    def test_save_failure_still_reaps_child_and_preserves_error(self):
        child = Mock(pid=126)
        child.poll.return_value = None
        with patch.object(web.subprocess, "Popen", return_value=child), \
                patch.object(web.QMPClient, "connect"), \
                patch.object(web.QMPClient, "execute", return_value=[]), \
                patch.object(web.threading, "Thread"):
            emulator = web.Emulator(Path("unused"), Path("unused"),
                                    journal=web.RunJournal(self.root),
                                    nand_save_on_exit=self.root / "save.nand")
            emulator.save_nand = Mock(side_effect=web.QMPError("outcome unknown"))
            with self.assertRaisesRegex(web.QMPError, "outcome unknown"):
                emulator.close()
        emulator.save_nand.assert_called_once_with(self.root / "save.nand", timeout=30.0)
        child.terminate.assert_called_once()
        self.assertTrue(emulator.log.closed)

    def test_failed_handshake_cleans_child_and_does_not_save_nand(self):
        journal = web.RunJournal(self.root)
        child = Mock(pid=123)
        child.poll.return_value = None
        child.wait.return_value = -15
        with patch.object(web.subprocess, "Popen", return_value=child), \
                patch.object(web.QMPClient, "connect", side_effect=web.QMPError("bad greeting")), \
                patch.object(web.Emulator, "save_nand") as save:
            with self.assertRaisesRegex(web.QMPError, "bad greeting"):
                web.Emulator(Path("unused-qemu"), Path("unused-prg"),
                             journal=journal, nand_save_on_exit=self.root / "save.nand")
        child.terminate.assert_called_once()
        child.wait.assert_called_once_with(timeout=2)
        save.assert_not_called()
        self.assertTrue((journal.directory / "qemu.log").is_file())

    def test_journal_passes_to_qemu_without_enabling_checkpoint_export(self):
        child = Mock(pid=127)
        child.poll.return_value = None
        path = self.root / "saved.npj"
        with patch.object(web.subprocess, "Popen", return_value=child) as spawn, \
                patch.object(web.QMPClient, "connect"), \
                patch.object(web.QMPClient, "execute", return_value=[]), \
                patch.object(web.threading, "Thread"), \
                patch.object(web.Emulator, "save_nand") as save:
            emulator = web.Emulator(Path("unused"), Path("unused"),
                                    nand_journal=path)
            self.assertIn(f"nand-journal={path}", spawn.call_args.args[0][2])
            self.assertIsNone(emulator.nand_save_on_exit)
            emulator.close()
            save.assert_not_called()

    def test_export_cannot_replace_active_journal_or_seed(self):
        seed = self.root / "seed.nand"
        path = self.root / "saved.npj"
        for protected in (path, seed):
            with self.subTest(protected=protected), \
                    patch.object(web.subprocess, "Popen") as spawn:
                with self.assertRaisesRegex(ValueError, "must not overwrite"):
                    web.Emulator(Path("unused"), Path("unused"),
                                 nand_checkpoint=seed, nand_journal=path,
                                 nand_save_on_exit=protected)
                spawn.assert_not_called()

    def test_spawn_failure_closes_log(self):
        journal = web.RunJournal(self.root)
        with patch.object(web.subprocess, "Popen", side_effect=OSError("cannot exec")):
            with self.assertRaisesRegex(OSError, "cannot exec"):
                web.Emulator(Path("unused"), Path("unused"), journal=journal)
        # Windows refuses this rename if the log handle was leaked.
        (journal.directory / "qemu.log").rename(journal.directory / "closed.log")

    def test_export_protects_boot_inputs_without_journal(self):
        for name in ('qemu', 'firmware', 'mask_rom', 'soc_rom', 'usb_loader',
                     'burn_code', 'driver_code'):
            protected = self.root / (name + '.bin')
            protected.write_bytes(b'original input')
            args = dict(qemu=self.root / 'qemu', firmware=self.root / 'firmware')
            args[name] = protected
            with self.subTest(name=name), patch.object(
                    web.subprocess, 'Popen', side_effect=RuntimeError('unexpected spawn')) as spawn:
                with self.assertRaisesRegex(ValueError, 'must not overwrite'):
                    web.Emulator(**args, nand_save_on_exit=protected)
                spawn.assert_not_called()
            self.assertEqual(protected.read_bytes(), b'original input')

    def test_export_protects_journal_lock(self):
        journal = self.root / 'saved.npj'
        with patch.object(web.subprocess, 'Popen', side_effect=RuntimeError('unexpected spawn')) as spawn:
            with self.assertRaisesRegex(ValueError, 'must not overwrite'):
                web.Emulator(self.root / 'qemu', self.root / 'firmware',
                             nand_journal=journal,
                             nand_save_on_exit=Path(str(journal) + '.lock'))
            spawn.assert_not_called()

    def test_export_rechecks_explicit_target_and_late_hardlink(self):
        protected = self.root / 'firmware.bin'
        protected.write_bytes(b'original firmware')
        emulator = web.Emulator.__new__(web.Emulator)
        emulator._export_protected = (protected,)
        emulator.nand_save_on_exit = self.root / 'output.nand'
        emulator.qmp = Mock()
        # Ordinary separate exports still reach the actual QMP interface.
        self.assertEqual(emulator.save_nand(), emulator.nand_save_on_exit)
        emulator.qmp.execute.assert_called_once_with('qom-set', {
            'path': '/machine', 'property': 'nand-save',
            'value': str(emulator.nand_save_on_exit.resolve()),
        })
        emulator.qmp.reset_mock()
        # Resolve aliases afresh rather than trusting the startup path check.
        import os
        os.link(protected, emulator.nand_save_on_exit)
        for target in (None, protected):
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, 'must not overwrite'):
                emulator.save_nand(target)
        emulator.qmp.execute.assert_not_called()
        self.assertEqual(protected.read_bytes(), b'original firmware')

    def test_forced_cleanup_reaps_child(self):
        child = Mock(pid=124)
        child.poll.return_value = None
        child.wait.side_effect = [subprocess.TimeoutExpired("qemu", 2), -9]
        with patch.object(web.subprocess, "Popen", return_value=child), \
                patch.object(web.QMPClient, "connect", side_effect=web.QMPError("not ready")):
            with self.assertRaises(web.QMPError):
                web.Emulator(Path("unused"), Path("unused"),
                             journal=web.RunJournal(self.root))
        child.kill.assert_called_once()
        self.assertEqual(child.wait.call_count, 2)

    def test_close_is_idempotent(self):
        child = Mock(pid=124)
        child.poll.return_value = None
        with patch.object(web.subprocess, "Popen", return_value=child), \
                patch.object(web.QMPClient, "connect"), \
                patch.object(web.QMPClient, "execute", return_value=[]), \
                patch.object(web.threading, "Thread"):
            emulator = web.Emulator(Path("unused"), Path("unused"),
                                    journal=web.RunJournal(self.root))
            emulator.close()
            emulator.close()
        child.terminate.assert_called_once()

    def test_key_snapshot_capability_is_detected_without_input_writes(self):
        for supported in (False, True):
            child = Mock(pid=130)
            child.poll.return_value = None
            properties = ([{"name": "key-input-snapshot", "type": "string"}]
                          if supported else [{"name": "key-state", "type": "uint32"}])
            with self.subTest(supported=supported), \
                    patch.object(web.subprocess, "Popen", return_value=child), \
                    patch.object(web.QMPClient, "connect"), \
                    patch.object(web.QMPClient, "execute", return_value=properties) as execute, \
                    patch.object(web.threading, "Thread"):
                emulator = web.Emulator(Path("unused"), Path("unused"))
                try:
                    self.assertEqual(emulator.atomic_key_input, supported)
                    self.assertEqual(emulator.health()["key_input_transport"],
                                     "atomic-snapshot" if supported else "legacy-properties")
                    execute.assert_called_once_with("qom-list", {"path": "/machine"})
                finally:
                    emulator.close()

    def test_dead_child_is_reported_without_qmp_or_automatic_restart(self):
        emulator = web.Emulator.__new__(web.Emulator)
        emulator.journal = web.RunJournal(self.root)
        emulator.process = Mock(pid=125)
        emulator.process.wait.return_value = 7
        emulator.process.poll.return_value = 7
        emulator.qmp = Mock()
        emulator.log_path = emulator.journal.directory / "qemu.log"
        emulator._closing = threading.Event()
        emulator._observe_exit()
        state = emulator.health()
        self.assertFalse(state["qemu_alive"])
        self.assertEqual(state["qemu_returncode"], 7)
        self.assertTrue(state["unexpected_qemu_exit"])
        self.assertEqual(state["guest_health"], "not_checked")
        self.assertEqual(emulator.qmp.mock_calls, [])

    def test_dead_npe_codec_is_not_reported_as_healthy_audio(self):
        emulator = web.Emulator.__new__(web.Emulator)
        emulator.journal = None
        emulator.log_path = self.root / "qemu.log"
        emulator.process = Mock(pid=125)
        emulator.process.poll.return_value = None
        emulator.codec_process = Mock(pid=126)
        emulator.codec_process.poll.return_value = 9
        emulator.qmp = Mock()

        state = emulator.health()
        self.assertTrue(state["qemu_alive"])
        self.assertFalse(state["npe_codec_alive"])
        self.assertEqual(state["npe_codec_returncode"], 9)
        self.assertEqual(state["npe_codec_pid"], 126)
        with self.assertRaisesRegex(web.QMPError,
                                    "NPE codec exited with status 9"):
            emulator.audio()
        self.assertEqual(emulator.qmp.mock_calls, [])

        emulator.codec_process = None
        self.assertIsNone(emulator.health()["npe_codec_alive"])

    def test_duplicate_port_never_starts_qemu(self):
        with patch("sys.argv", ["np560_web"]):
            args = web.parse_args()
        args.run_log_dir = self.root
        with socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen()
            args.host, args.port = occupied.getsockname()
            with patch.object(web, "start_emulator") as start:
                with self.assertRaises(OSError):
                    web.run_server(args)
            start.assert_not_called()
        status_path, = self.root.glob("*/status.json")
        status = json.loads(status_path.read_text(encoding="utf-8"))
        self.assertEqual(status["phase"], "failed")
        self.assertEqual(status["bridge_returncode"], 1)
        self.assertIn("Traceback", status["traceback"])

    def test_debug_initialization_failure_closes_runtime_and_port(self):
        with patch("sys.argv", ["np560_web"]):
            args = web.parse_args()
        args.run_log_dir = self.root
        args.port = 0
        args.debug_program_load = [(0x200000, self.root / "diagnostic.bin")]
        emulator = Mock()
        emulator.load_program.side_effect = web.QMPError("diagnostic load failed")
        with patch.object(web, "artifact_identity", return_value=(1, "0" * 64)), \
                patch.object(web, "start_emulator", return_value=emulator):
            with self.assertRaisesRegex(web.QMPError, "diagnostic load failed"):
                web.run_server(args)
        emulator.close.assert_called_once()
        status_path, = self.root.glob("*/status.json")
        state = json.loads(status_path.read_text(encoding="utf-8"))
        self.assertEqual(state["phase"], "failed")
        with socket.socket() as check:
            check.bind(("127.0.0.1", state["port"]))


if __name__ == "__main__":
    unittest.main()
