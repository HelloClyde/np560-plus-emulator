#!/usr/bin/env python3
"""Execute factory key-table selection and M26 state transitions, not LCD or debounce."""
import argparse
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_np560_dtu import execute, write_word


def call_key(words, index, result):
    words.extend([0x68F0, index, 0x58F0, 0xBD20, 0xF4A4,
                  0x50F2, 0x0800 | (result << 4)])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, required=True)
    parser.add_argument('--numeric-only', action='store_true',
                        help='Run the full shared number/top-letter row in all modes only')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    prg = (root / 'NP560+V3.80版系统升级程序/NP560.PRG').read_bytes()
    assert hashlib.sha256(prg).hexdigest() == (
        'd555609e03ece17f42c1881beeb88361572f18621161de67bc9dc765857089f5')
    # Keep original PC offsets: local branches need no patching. Only the
    # three external LCD-side calls are stubbed; the worker and key tables
    # are byte-exact. This fixture makes no assertion about LCD output.
    regions = (
        (0x20F4A4, prg[0x25F4A4:0x25F782]),
        # Production exact overlays read these source addresses for their
        # 31:4D24/5014 runtime views; writable views are initialized below.
        (0x4E4D24, b'\x20\xc6'),
        (0x4E5014, b'\x20\xc6'),
    )

    def setup(mode):
        words = [0x6800, 2, 0x68FF, 0x6000, 0x6810, 0x64]
        # The production loader populates a writable Harvard data view;
        # placing bytes on the instruction bus does not initialize it.
        tables = prg[0x2F29B2:0x2F2B32]
        for offset in range(0, len(tables), 2):
            write_word(words, 0x29B2 + offset,
                       int.from_bytes(tables[offset:offset + 2], 'little'), banked=True)
        # The LCD refresh entry is another loader-populated writable code
        # view. Install a test-only RETS there, leaving the worker intact.
        words.extend([0x6810, 0x66])
        write_word(words, 0x3C86, 0xC620, banked=True)
        words.extend([0x6810, 0xA2])
        write_word(words, 0x28D2, 0xA500 | mode, banked=True)
        write_word(words, 0x28DA, 0xFFFF, banked=True)
        return words

    # All ten number buttons share the physical letter row. Reset before
    # each call so one-shot mode consumption cannot hide later-key errors.
    # Expected text is independent of the PRG tables under execution.
    for mode in range(8):
        text = ('qwertyuiop' if mode & 4 or mode == 0 else
                'QWERTYUIOP' if mode & 1 else '1234567890')
        words = setup(mode)
        expected = {15: 0x6000}
        for register, (index, character) in enumerate(zip(
                (2, 3, 0, 8, 16, 24, 32, 40, 48, 56), text), 4):
            words.extend([0x6810, 0xA2])
            write_word(words, 0x28D2, 0xA500 | mode, banked=True)
            call_key(words, index, register)
            expected[register] = ord(character)
        execute(args.qemu, f'factory complete number row mode {mode}', words,
                expected, extra_regions=regions, verify_extra_code=True)
    if args.numeric_only:
        print('PASS: all ten shared number/top-letter contacts in eight modes; LCD calls stubbed')
        return

    # Independently named expectations, not values read back from the table
    # under test. Numeric mode shares Q/1; app-forced bit 2 overrides both.
    for mode in range(8):
        words = setup(mode)
        expected_values = ((0x71, 0x84, 0x20, 0xE2) if mode & 4 or mode == 0
                           else (0x51, 0x27, 0x2E, 0xDD) if mode & 1
                           else (0x31, 0x84, 0x20, 0xE2))
        for register, index in enumerate((2, 28, 54, 60), 4):
            call_key(words, index, register)
        expected = dict(enumerate(expected_values, 4))
        expected[15] = 0x6000
        execute(args.qemu, f'factory key mode {mode}', words, expected,
                extra_regions=regions, verify_extra_code=True)

        # Check the other mode-dependent Web contacts independently too.
        # Start each call with the same mode: the real worker consumes the
        # one-shot uppercase flag, so consecutive calls are not equivalent.
        upper = bool(mode & 1) and not bool(mode & 4)
        for label, index, value in (
            ('F2', 52, 0xDC if upper else 0xE1),
            ('F3', 44, 0xDF if upper else 0xEA),
            ('comma', 20, 0x2C if upper else 0x85),
        ):
            words = setup(mode)
            call_key(words, index, 4)
            execute(args.qemu, f'factory key mode {mode} {label}', words,
                    {4: value, 15: 0x6000}, extra_regions=regions,
                    verify_extra_code=True)

        # Navigation must remain mode-independent, including app-forced and
        # one-shot uppercase modes. Reset the mode before EACH contact so a
        # preceding key cannot consume the one-shot flag and hide a mismatch.
        for batch in (
            ((45, 0x80), (29, 0x81), (61, 0x82), (37, 0x83)),
            ((53, 0x86), (55, 0xB0), (4, 0x8E)),
        ):
            words = setup(mode)
            expected = {15: 0x6000}
            for register, (index, value) in enumerate(batch, 4):
                words.extend([0x6810, 0xA2])
                write_word(words, 0x28D2, 0xA500 | mode, banked=True)
                call_key(words, index, register)
                expected[register] = value
            execute(args.qemu, f'factory navigation mode {mode} {batch[0][0]}',
                    words, expected, extra_regions=regions,
                    verify_extra_code=True)

    words = setup(0)
    for index, register in ((26, 4), (2, 5), (2, 6), (26, 7), (26, 8)):
        call_key(words, index, register)
    words.extend([0x6810, 0xA2, 0x88F9, 0x28D2])
    execute(args.qemu, 'M26 next-key consumption and double-toggle', words,
            {4: 0x8C, 5: 0x51, 6: 0x71, 7: 0x8C, 8: 0x8C,
             9: 0xA500, 15: 0x6000}, extra_regions=regions,
            verify_extra_code=True)

    # Check independently named normal-mode contacts, not expectations copied
    # from the table being executed. This tests the worker's output, not the
    # physical key labels, browser transport, debounce, or application dispatch.
    letters = {
        'E': 0, 'D': 1, 'Q': 2, 'W': 3, 'X': 6, 'R': 8, 'F': 9,
        'A': 10, 'C': 14, 'T': 16, 'G': 17, 'S': 18, 'V': 22,
        'Y': 24, 'H': 25, 'B': 30, 'U': 32, 'J': 33, 'Z': 34,
        'N': 38, 'I': 40, 'K': 41, 'M': 46, 'O': 48, 'L': 49, 'P': 56,
    }
    contacts = [(label, index, ord(label.lower())) for label, index in letters.items()]
    contacts += [
        ('left', 45, 0x80), ('right', 29, 0x81),
        ('up', 61, 0x82), ('down', 37, 0x83),
        ('escape', 28, 0x84), ('enter', 53, 0x86),
        ('space', 54, 0x20), ('start', 55, 0xB0),
        ('F1', 60, 0xE2), ('F2', 52, 0xE1),
        ('F3', 44, 0xEA), ('F4', 4, 0x8E),
    ]
    for start in range(0, len(contacts), 4):
        batch = contacts[start:start + 4]
        words = setup(0)
        expected = {15: 0x6000}
        for register, (label, index, value) in enumerate(batch, 4):
            call_key(words, index, register)
            expected[register] = value
        execute(args.qemu, 'normal contacts ' + '/'.join(item[0] for item in batch),
                words, expected, extra_regions=regions, verify_extra_code=True)
    print(f'PASS: eight mode combinations including F2/F3/comma and mode-reset navigation, M26 transitions and {len(contacts)} named '
          'normal contacts; LCD calls stubbed')


if __name__ == '__main__':
    main()
