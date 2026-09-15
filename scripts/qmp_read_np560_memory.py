#!/usr/bin/env python3
"""Read physical-memory ranges from a running NP560 QEMU instance."""

import argparse
import json
import socket


def receive_reply(stream, request_id):
    while True:
        line = stream.readline()
        if not line:
            raise RuntimeError("QMP connection closed")
        message = json.loads(line)
        if message.get("id") == request_id:
            return message


def send(stream, message):
    stream.write((json.dumps(message) + "\n").encode("ascii"))


def parse_range(value):
    """Parse NAME=ADDRESS:SIZE, accepting decimal or 0x-prefixed integers."""
    try:
        name, specification = value.split("=", 1)
        address_text, size_text = specification.rsplit(":", 1)
        address = int(address_text, 0)
        size = int(size_text, 0)
    except (ValueError, TypeError) as error:
        raise argparse.ArgumentTypeError(
            "range must be NAME=ADDRESS:SIZE"
        ) from error
    if not name or address < 0 or size <= 0:
        raise argparse.ArgumentTypeError(
            "range name must be non-empty, address non-negative, and size positive"
        )
    return name, address, size


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "socket_path", nargs="?", default="/tmp/np560-21.qmp",
        help="QMP Unix socket path",
    )
    parser.add_argument(
        "--range", dest="ranges", action="append", type=parse_range,
        metavar="NAME=ADDRESS:SIZE",
        help="physical-memory range to read; repeat for multiple ranges",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    sock = socket.socket(socket.AF_UNIX)
    sock.connect(args.socket_path)
    stream = sock.makefile("rwb", buffering=0)
    greeting = json.loads(stream.readline())
    print(json.dumps(greeting, sort_keys=True))

    send(stream, {"execute": "qmp_capabilities", "id": "cap"})
    print(json.dumps(receive_reply(stream, "cap"), sort_keys=True))

    ranges = args.ranges or [
        ("catalog_destination", 0x201142, 64),
        ("catalog_source", 0x3D1142, 64),
        ("first_name_destination", 0x336D44, 32),
        ("first_name_source", 0x506D44, 32),
    ]
    for request_id, address, size in ranges:
        command = f"xp /{size}bx 0x{address:x}"
        send(
            stream,
            {
                "execute": "human-monitor-command",
                "arguments": {"command-line": command},
                "id": request_id,
            },
        )
        print(json.dumps(receive_reply(stream, request_id), sort_keys=True))


if __name__ == "__main__":
    main()
