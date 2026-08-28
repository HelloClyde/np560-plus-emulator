#!/usr/bin/env python3
"""Read selected physical-memory ranges from a running NP560 QEMU instance."""

import json
import socket
import sys


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


def main():
    socket_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/np560-21.qmp"
    sock = socket.socket(socket.AF_UNIX)
    sock.connect(socket_path)
    stream = sock.makefile("rwb", buffering=0)
    greeting = json.loads(stream.readline())
    print(json.dumps(greeting, sort_keys=True))

    send(stream, {"execute": "qmp_capabilities", "id": "cap"})
    print(json.dumps(receive_reply(stream, "cap"), sort_keys=True))

    ranges = {
        "catalog_destination": (0x201142, 64),
        "catalog_source": (0x3D1142, 64),
        "first_name_destination": (0x336D44, 32),
        "first_name_source": (0x506D44, 32),
    }
    for request_id, (address, size) in ranges.items():
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
