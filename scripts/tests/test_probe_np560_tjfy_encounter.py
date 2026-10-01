"""The bounded Tianjiang walk must read the guest's actual map/battle mode."""

from __future__ import annotations

import base64
import json
from unittest.mock import Mock

import pytest

from scripts import probe_np560_tjfy_encounter as encounter

guest_mode = encounter.guest_mode


def snapshot(mode: int) -> dict:
    raw = bytearray(0x36)
    raw[0x34:0x36] = mode.to_bytes(2, "little")
    return {"source": "data", "format": "packed",
            "frame": base64.b64encode(raw).decode()}


def test_guest_mode_reads_only_the_original_mode_word() -> None:
    assert guest_mode(snapshot(1)) == 1
    assert guest_mode(snapshot(3)) == 3
    with pytest.raises(ValueError, match="raw guest data"):
        guest_mode({**snapshot(1), "source": "lcd"})
    with pytest.raises(ValueError, match="length"):
        guest_mode({**snapshot(1), "frame": base64.b64encode(b"short").decode()})


def test_delayed_battle_transition_stops_before_another_direction(
        monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    bridge = Mock()
    monkeypatch.setattr(encounter, "WebBridge", Mock(return_value=bridge))
    modes = iter((1, 1, 1, 3, 3))
    monkeypatch.setattr(encounter, "read_mode", lambda _bridge: next(modes))
    monkeypatch.setattr(encounter, "read_map", lambda _bridge: 80)
    replay = Mock(return_value={"maps_before": 4, "maps_after": 5})
    monkeypatch.setattr(encounter, "replay_step", replay)
    output = tmp_path / "encounter.json"
    monkeypatch.setattr("sys.argv", ["probe_np560_tjfy_encounter.py",
                                  "--output", str(output),
                                  "--expected-map", "80"])
    assert encounter.main() == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["outcome"] == "battle_after_settle"
    assert report["final_mode"] == 3
    assert report["initial_map"] == 80
    assert len(report["steps"]) == 1
    replay.assert_called_once()


def test_wrong_map_is_rejected_before_movement(
        monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(encounter, "WebBridge", Mock())
    monkeypatch.setattr(encounter, "read_mode", lambda _bridge: 1)
    monkeypatch.setattr(encounter, "read_map", lambda _bridge: 1)
    replay = Mock()
    monkeypatch.setattr(encounter, "replay_step", replay)
    output = tmp_path / "wrong-map.json"
    monkeypatch.setattr("sys.argv", ["probe_np560_tjfy_encounter.py",
                                  "--output", str(output),
                                  "--expected-map", "80"])
    with pytest.raises(SystemExit, match="2"):
        encounter.main()
    assert not output.exists()
    replay.assert_not_called()
