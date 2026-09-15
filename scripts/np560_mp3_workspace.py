# SPDX-License-Identifier: GPL-2.0-or-later
"""MP3 component workspace selection, not machine memory reservation.

Default bank zero preserves the existing diagnostic workspace selection.
None retains the caller's DS0 for all near descriptors, spectra and state;
bank ownership/allocation and interrupt-safe lifetime remain caller duties.
Every nested component must be built with the same selection.
"""


def select_workspace(bank):
    if bank is None:
        return ()
    if not isinstance(bank, int) or not 0 <= bank <= 0x1ff:
        raise ValueError("workspace bank must be None or 0..0x1ff")
    return (0x6810, bank)
