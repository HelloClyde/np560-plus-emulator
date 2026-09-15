#!/usr/bin/env python3
"""Back up or restore a stopped NP560+ device without launching QEMU."""

import argparse
import json
from pathlib import Path
import sys
import zipfile

from web.device_backup import backup_device, restore_device


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("backup", help="Package all inputs and the exclusively guarded saved journal")
    backup.add_argument("--device", type=Path, required=True)
    backup.add_argument("--output", type=Path, required=True)
    backup.add_argument("--qemu", type=Path, help="Explicit core override if the configured core moved")
    restore = commands.add_parser("restore", help="Verify and restore to a new directory; never overwrite a device")
    restore.add_argument("--backup", type=Path, required=True)
    restore.add_argument("--output-directory", type=Path, required=True)
    restore.add_argument("--qemu", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "backup":
            result = backup_device(args.device, args.output, qemu=args.qemu)
        else:
            result = restore_device(args.backup, args.output_directory, qemu=args.qemu)
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile,
            RuntimeError, NotImplementedError) as error:
        print(f"Device {args.command} failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
