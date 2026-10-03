#!/usr/bin/env python3
"""Serve experimental candidate-compatible NPE PCM over a local Unix socket.

The owned mode-5 backend has no DLL runtime dependency.  The optional CYBIT
candidate backend emulates a user-supplied DLL in Unicorn, never executing it
natively or distributing it.  Neither backend proves the missing NP560 ROM
service ABI or true-device PCM is identical.

Wire protocol (all lengths unsigned little-endian):
  I, mode:u8                 -> K, frame_bits:u16
  D, frame_bytes:u16, frame  -> P, samples:u16, PCM16LE[samples]
  R                          -> K
  Error                      -> E, utf8_bytes:u16, message
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import struct

try:
    from .np560_mobivoice_decoder import CandidateMode5Decoder
except ImportError:  # Direct scripts/ execution.
    from np560_mobivoice_decoder import CandidateMode5Decoder


MAX_FRAME_BYTES = 36
MAX_ERROR_BYTES = 240


class OwnedMode5Codec:
    """Adapt the independently modeled mode-5 decoder to the socket contract."""

    def __init__(self) -> None:
        self.decoder = CandidateMode5Decoder()

    def init(self, mode: int) -> tuple[int, int]:
        if mode != 5:
            raise ValueError("owned NPE codec currently supports mode 5 only")
        self.decoder = CandidateMode5Decoder()
        return 1, 21 * 8

    def decode(self, frame: bytes, context: int) -> tuple[int, bytes]:
        if context != 1:
            raise ValueError("invalid owned NPE codec context")
        samples = self.decoder.decode_frame(frame)
        return len(samples), struct.pack("<160h", *samples)


def read_exact(stream: socket.socket, count: int) -> bytes:
    if count < 0:
        raise ValueError("negative protocol read")
    result = bytearray()
    while len(result) < count:
        chunk = stream.recv(count - len(result))
        if not chunk:
            raise EOFError("codec client disconnected")
        result.extend(chunk)
    return bytes(result)


def error_packet(error: Exception) -> bytes:
    message = str(error).encode("utf-8", errors="replace")[:MAX_ERROR_BYTES]
    return b"E" + struct.pack("<H", len(message)) + message


def serve_connection(stream: socket.socket, decoder_factory, trace_frame=None) -> None:
    decoder = None
    context = None
    frame_bits = 0
    while True:
        operation = stream.recv(1)
        if not operation:
            return
        try:
            if operation == b"I":
                # A failed reinitialization must not leave the previous stream
                # eligible for further decode requests.
                decoder = None
                context = None
                frame_bits = 0
                mode = read_exact(stream, 1)[0]
                if not 1 <= mode <= 10:
                    raise ValueError("codec mode must be 1..10")
                candidate = decoder_factory()
                candidate_context, candidate_bits = candidate.init(mode)
                expected_bits = (mode * 3 + 6) * 8
                if not candidate_context or candidate_bits != expected_bits:
                    raise ValueError("decoder returned an unexpected frame specification")
                decoder = candidate
                context = candidate_context
                frame_bits = candidate_bits
                stream.sendall(b"K" + struct.pack("<H", frame_bits))
            elif operation == b"D":
                size = struct.unpack("<H", read_exact(stream, 2))[0]
                if not 1 <= size <= MAX_FRAME_BYTES:
                    stream.sendall(error_packet(ValueError(
                        "compressed frame size is invalid")))
                    return  # Framing cannot be recovered without consuming unknown input.
                frame = read_exact(stream, size)
                if decoder is None or context is None:
                    raise ValueError("decoder was not initialized")
                if size * 8 != frame_bits:
                    raise ValueError("compressed frame does not match initialized mode")
                if trace_frame is not None:
                    trace_frame(mode, frame)
                samples, pcm = decoder.decode(frame, context)
                if samples != 160 or len(pcm) != samples * 2:
                    raise ValueError("decoder returned an unexpected PCM frame")
                stream.sendall(b"P" + struct.pack("<H", samples) + pcm)
            elif operation == b"R":
                decoder = None
                context = None
                frame_bits = 0
                stream.sendall(b"K")
            else:
                raise ValueError("unknown codec operation")
        except (ValueError, RuntimeError) as error:
            stream.sendall(error_packet(error))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("candidate", "owned"),
                        default="candidate")
    parser.add_argument("--dll", type=Path,
                        help="reviewed local DLL; required for candidate backend only")
    endpoint = parser.add_mutually_exclusive_group(required=True)
    endpoint.add_argument("--socket", type=Path)
    endpoint.add_argument("--tcp", help="Windows loopback endpoint, 127.0.0.1:PORT")
    parser.add_argument("--trace-first", type=int, default=0,
                        help="record this many initial compressed frames for a local diagnostic")
    parser.add_argument("--trace-path", type=Path,
                        help="new JSONL trace; required when --trace-first is set")
    args = parser.parse_args()
    if args.backend == "candidate" and args.dll is None:
        parser.error("candidate backend requires --dll")
    if args.backend == "owned" and args.dll is not None:
        parser.error("owned backend must not be given --dll")
    if args.trace_first < 0 or bool(args.trace_first) != bool(args.trace_path):
        parser.error("--trace-first and --trace-path must be set together")
    if args.trace_path is not None and args.trace_path.exists():
        parser.error(f"trace path already exists: {args.trace_path}")
    if args.socket is not None and not hasattr(socket, "AF_UNIX"):
        parser.error("this codec transport requires Unix-domain sockets")
    if args.socket is not None and args.socket.exists():
        parser.error(f"socket path already exists: {args.socket}")
    if args.tcp is not None:
        host, separator, port_text = args.tcp.partition(":")
        if (host != "127.0.0.1" or separator != ":" or
                not port_text.isdecimal() or not 1 <= int(port_text) <= 65535):
            parser.error("--tcp requires 127.0.0.1:PORT")
        tcp_address = (host, int(port_text))
    if args.backend == "candidate":
        # Import/verify the third-party diagnostic dependency only on request.
        from probe_np560_mobivoice_sp_decoder import IsolatedDecoder

        dll = args.dll.read_bytes()
        IsolatedDecoder(dll)
        decoder_factory = lambda: IsolatedDecoder(dll)
    else:
        decoder_factory = OwnedMode5Codec
    trace_count = 0
    trace = None

    def trace_frame(mode: int, frame: bytes) -> None:
        nonlocal trace_count
        if trace is not None and trace_count < args.trace_first:
            trace.write(json.dumps({"index": trace_count, "mode": mode,
                                    "frame_hex": frame.hex()}) + "\n")
            trace.flush()
        trace_count += 1

    if args.trace_path is not None:
        args.trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace = args.trace_path.open("x", encoding="utf-8")
    listener = socket.socket(socket.AF_INET if args.tcp else socket.AF_UNIX,
                             socket.SOCK_STREAM)
    listener.bind(tcp_address if args.tcp else str(args.socket))
    try:
        if args.socket is not None:
            os.chmod(args.socket, 0o600)
        listener.listen(1)
        with listener:
            try:
                while True:
                    client, _ = listener.accept()
                    with client:
                        try:
                            serve_connection(client, decoder_factory, trace_frame)
                        except (EOFError, OSError):
                            pass
            except KeyboardInterrupt:
                pass
    finally:
        if args.socket is not None:
            args.socket.unlink(missing_ok=True)
        if trace is not None:
            trace.close()


if __name__ == "__main__":
    main()
