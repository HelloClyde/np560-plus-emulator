#!/usr/bin/env python3
"""Exercise real Web/QEMU lifecycle failures in owned, dynamically bound instances.

Run under Linux/WSL. Never connects to or stops the user's existing Web instance.
Does not save or modify the input NAND checkpoint. Logs and a manifest are retained.
"""

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from web.np560_web import DEFAULT_FIRMWARE, DEFAULT_QEMU, ROOT


def request(root, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    query = Request(root + path, data=data,
                    headers={"Content-Type": "application/json"})
    try:
        response = urlopen(query, timeout=3)
    except HTTPError as error:
        response = error
    with response:
        return response.status, json.load(response)


def wait_until(predicate, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.1)
    raise TimeoutError("lifecycle condition did not become true")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, default=DEFAULT_QEMU)
    parser.add_argument("--firmware", type=Path, default=DEFAULT_FIRMWARE)
    parser.add_argument("--soc-rom", type=Path, required=True)
    parser.add_argument("--nand-checkpoint", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if os.name != "posix":
        parser.error("run this owned-process probe under Linux/WSL")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    records = output / "runs"
    token = "owned-lifecycle-probe"
    command = [
        sys.executable, "-u", str(ROOT / "np560_web.py"),
        "--qemu", str(args.qemu), "--firmware", str(args.firmware),
        "--soc-rom", str(args.soc_rom), "--nand-checkpoint", str(args.nand_checkpoint),
        "--boot-mode", "firmware-vma03", "--port", "0",
        "--shutdown-token", token, "--run-log-dir", str(records),
    ]
    manifest = {"schema": "np560-web-lifecycle-probe-v1", "passed": False}
    root = None
    with (output / "bridge.log").open("wb") as log:
        process = subprocess.Popen(command, stdout=log, stderr=log)
        try:
            def serving():
                if process.poll() is not None:
                    raise RuntimeError(f"bridge startup failed: {process.returncode}")
                for path in records.glob("*/status.json"):
                    state = json.loads(path.read_text(encoding="utf-8"))
                    if state.get("phase") == "serving":
                        return state
                return None

            state = wait_until(serving)
            root = f"http://127.0.0.1:{state['port']}"
            status, before = request(root, "/api/health")
            assert status == 200 and before["qemu_alive"]
            assert before["bridge_pid"] == process.pid
            manifest["initial_health"] = before

            duplicate = command.copy()
            duplicate[duplicate.index("--port") + 1] = str(state["port"])
            with (output / "duplicate.log").open("wb") as duplicate_log:
                failed = subprocess.run(duplicate, stdout=duplicate_log,
                                        stderr=duplicate_log, timeout=15)
            assert failed.returncode != 0
            failed_states = [json.loads(path.read_text(encoding="utf-8"))
                             for path in records.glob("*/status.json")]
            duplicate_state, = [item for item in failed_states if item["phase"] == "failed"]
            assert "qemu_pid" not in duplicate_state
            status, unchanged = request(root, "/api/health")
            assert status == 200 and unchanged["qemu_pid"] == before["qemu_pid"]
            manifest["duplicate_port"] = duplicate_state

            # Only this bridge's positively identified child is fault-injected.
            # Keep Web alive to prove that QMP loss does not hang /api/health.
            os.kill(before["qemu_pid"], signal.SIGTERM)

            def exited():
                status, health = request(root, "/api/health")
                if status == 503 and health.get("unexpected_qemu_exit"):
                    return health
                return None

            after = wait_until(exited, timeout=10)
            assert after["qemu_pid"] == before["qemu_pid"]
            assert after["qemu_returncode"] is not None
            manifest["unexpected_exit"] = after
            status, _ = request(root, "/api/control", {"action": "shutdown", "token": token})
            assert status == 200
            assert process.wait(timeout=10) == 1
            final = json.loads((Path(before["directory"]) / "status.json").read_text(encoding="utf-8"))
            assert final["phase"] == "stopped" and final["bridge_returncode"] == 1
            assert final["unexpected_qemu_exit"]
            assert not Path(f"/proc/{before['qemu_pid']}").exists()
            manifest["final_status"] = final

            # A real child exits before QMP opens. The startup failure must be
            # logged and the child reaped, with no persistent server remaining.
            no_qmp = command.copy()
            no_qmp[no_qmp.index("--qemu") + 1] = "/bin/false"
            with (output / "startup-failure.log").open("wb") as failure_log:
                failed = subprocess.run(no_qmp, stdout=failure_log,
                                        stderr=failure_log, timeout=20)
            assert failed.returncode != 0
            failed_states = [json.loads(path.read_text(encoding="utf-8"))
                             for path in records.glob("*/status.json")]
            startup_state, = [item for item in failed_states
                              if item["phase"] == "failed" and "qemu_pid" in item]
            assert startup_state["qemu_returncode"] == 1
            assert not Path(f"/proc/{startup_state['qemu_pid']}").exists()
            manifest["startup_failure"] = startup_state
            manifest["passed"] = True
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            with (output / "manifest.json").open("w", encoding="utf-8") as stream:
                json.dump(manifest, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
    print(json.dumps({"passed": manifest["passed"], "manifest": str(output / "manifest.json")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
