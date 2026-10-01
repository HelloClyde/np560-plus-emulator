#!/usr/bin/env python3
"""Read-only compare a stopped NPE audio RAM window with its original section.

Use only with an isolated Web bridge. The `/api/state?source=data` endpoint
reads the guest data bus; it does not patch RAM, the ROM, or the NPE file.
"""

import argparse
import base64
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from analyse_np560_npe import _parse_sections


def matching_prefix(actual: bytes, expected: bytes) -> int:
    for index, (left, right) in enumerate(zip(actual, expected)):
        if left != right:
            return index
    return min(len(actual), len(expected))


def compare_window(guest: bytes, section: bytes) -> dict:
    if len(guest) > len(section):
        raise ValueError("requested guest window exceeds NPE section length")
    prefix = matching_prefix(guest, section)
    return {
        "window_bytes": len(guest),
        "matching_prefix_bytes": prefix,
        "full_window_equal": prefix == len(guest),
        "guest_sha256": hashlib.sha256(guest).hexdigest(),
        "npe_window_sha256": hashlib.sha256(section[:len(guest)]).hexdigest(),
        "first_guest_mismatch_hex": guest[prefix:prefix + 32].hex(),
        "first_npe_mismatch_hex": section[prefix:prefix + 32].hex(),
        "guest_remaining_zero": (None if prefix == len(guest)
                                 else not any(guest[prefix:])),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True,
                        help="isolated local Web bridge, e.g. http://127.0.0.1:39607")
    parser.add_argument("--npe", type=Path, required=True)
    parser.add_argument("--section", type=int, default=16)
    parser.add_argument("--base", type=lambda value: int(value, 0), default=0x8800)
    parser.add_argument("--size", type=int, default=4096)
    parser.add_argument("--report-json", type=Path)
    args = parser.parse_args()
    if not 1 <= args.size <= 65536 or not 0 <= args.base <= 0xffffff:
        parser.error("base or size outside the supported diagnostic range")
    if args.report_json is not None and args.report_json.exists():
        parser.error(f"report already exists: {args.report_json}")
    source = args.npe.read_bytes()
    offset, length = _parse_sections(source)[args.section]
    section = source[offset:offset + length]
    if args.size > length:
        parser.error("requested window exceeds section length")
    query = urlencode({"source": "data", "base": hex(args.base),
                       "size": args.size, "diagnostics": 0})
    with urlopen(args.root.rstrip("/") + "/api/state?" + query, timeout=15) as response:
        state = json.load(response)
    if state.get("source") != "data" or state.get("format") != "packed":
        raise ValueError("Web bridge did not return a raw guest data window")
    guest = base64.b64decode(state["frame"], validate=True)
    if len(guest) != args.size:
        raise ValueError(f"guest returned {len(guest)} bytes, expected {args.size}")
    report = {
        "schema": "np560-npe-stream-window-v1",
        "npe": str(args.npe), "npe_sha256": hashlib.sha256(source).hexdigest(),
        "section": args.section, "section_offset": offset,
        "section_bytes": length, "section_sha256": hashlib.sha256(section).hexdigest(),
        "guest_base": args.base, "guest_status": state.get("status"),
        **compare_window(guest, section),
    }
    if args.report_json is not None:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
