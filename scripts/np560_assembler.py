"""Existing small DMCU label resolver, without ROM-builder import side effects.

Mechanically extracted from build_np560_reconstructed_rom.py; this is not
a C compiler or a new instruction set implementation.
"""
from __future__ import annotations


class _DMCUAssembler:
    """Tiny label resolver for clean-room same-segment DMCU routines."""

    def __init__(self, address: int):
        self.address = address
        self.words: list[int] = []
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str]] = []

    @property
    def pc(self) -> int:
        return (self.address + len(self.words) * 2) & 0xFFFFFF

    def emit(self, *words: int) -> None:
        if any(not 0 <= word <= 0xFFFF for word in words):
            raise ValueError("DMCU instruction word is outside 16 bits")
        self.words.extend(words)

    def label(self, name: str) -> None:
        if name in self.labels:
            raise ValueError(f"duplicate DMCU label {name}")
        self.labels[name] = self.pc

    def ajmp(self, label: str, condition: int = 0) -> None:
        if not 0 <= condition <= 0x0E:
            raise ValueError("invalid DMCU condition")
        self.emit(0xAC00 | condition, 0)
        self.fixups.append((len(self.words) - 1, label))

    def acall(self, label: str) -> None:
        self.emit(0xBC00, 0)
        self.fixups.append((len(self.words) - 1, label))

    def finish(self) -> list[int]:
        segment = self.address >> 16
        result = list(self.words)
        for index, label in self.fixups:
            if label not in self.labels:
                raise ValueError(f"undefined DMCU label {label}")
            target = self.labels[label]
            if target >> 16 != segment:
                raise ValueError(f"DMCU near target crosses segment: {label}")
            result[index] = target & 0xFFFF
        return result
