#!/usr/bin/env python3
"""Issue one QOM get/set request to a running local NP560 QEMU instance."""

from __future__ import annotations

import argparse
import json
import socket
from pathlib import Path


def read_message(stream) -> dict:
    while True:
        line = stream.readline()
        if not line:
            raise RuntimeError("QMP connection closed")
        message = json.loads(line)
        if "event" not in message:
            return message


def execute(stream, command: str, arguments: dict | None = None) -> object:
    request: dict[str, object] = {"execute": command, "id": 1}
    if arguments:
        request["arguments"] = arguments
    stream.write(json.dumps(request).encode("utf-8") + b"\r\n")
    while True:
        response = read_message(stream)
        if response.get("id") != 1:
            continue
        if "error" in response:
            raise RuntimeError(response["error"].get("desc", response["error"]))
        return response.get("return")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("socket", type=Path)
    parser.add_argument("operation", choices=("get", "set"))
    parser.add_argument("property")
    parser.add_argument("value", nargs="?")
    args = parser.parse_args()
    if args.operation == "set" and args.value is None:
        parser.error("set requires VALUE")
    if args.operation == "get" and args.value is not None:
        parser.error("get does not accept VALUE")

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(str(args.socket))
        with connection.makefile("rwb", buffering=0) as stream:
            greeting = read_message(stream)
            if "QMP" not in greeting:
                raise RuntimeError("QMP greeting missing")
            execute(stream, "qmp_capabilities")
            command = "qom-get" if args.operation == "get" else "qom-set"
            arguments = {"path": "/machine", "property": args.property}
            if args.operation == "set":
                arguments["value"] = args.value
            result = execute(stream, command, arguments)
            print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
