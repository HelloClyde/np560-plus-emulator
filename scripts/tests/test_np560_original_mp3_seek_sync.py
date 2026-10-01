#!/usr/bin/env python3
"""Run byte-exact factory sync search on a verified LONG22 seek window.

This isolates header matching, not file seeking, IRQ timing or end-to-end
playback. Initialization is test guest code; no production patches.
"""
import argparse
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_np560_dtu import execute, write_word, read_word


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, required=True)
    parser.add_argument('--mp3', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    prg = (root / 'NP560+V3.80版系统升级程序/NP560.PRG').read_bytes()
    assert hashlib.sha256(prg).hexdigest() == 'd555609e03ece17f42c1881beeb88361572f18621161de67bc9dc765857089f5'
    mp3 = args.mp3.read_bytes()
    assert hashlib.sha256(mp3).hexdigest() == '27521fc999c954d7e05cc56f2ba54253d4bdd32ac65c0ea7204fdda58945ec73'
    assert mp3[45:49] == bytes.fromhex('fff370c0')
    assert mp3[58:62] == b'Info'
    assert mp3[227:231] == bytes.fromhex('fff360c4')
    # Actual seek-file window identified in the owned reload snapshot.
    window = mp3[0x16152:0x16752]
    assert window[56:60] == bytes.fromhex('fff362c4')
    # Separate bitrate (0x1000) from the MPEG original flag (0x0004).
    # The original dynamic mask can relax bitrate but always retains bit 2.
    # These are diagnostic saved-header values, never production RAM edits.
    for header in (0x70c0, 0x60c4, 0x70c4, 0x60c0):
        for flags in range(4):
            expected = 56 if header == 0x60c4 or (header == 0x70c4 and flags & 1) else 0xfffa
            # BIT[8C] is not direct REG[8C]. Use the original bit opcodes
            # and read the effective mask bits back into a result register.
            words = [0x6800, 2, 0x68ff, 0x6000,
                     0xec8c if flags & 1 else 0xfc8c,
                     0xed8c if flags & 2 else 0xfd8c]
            for i in range(0, len(window), 2):
                write_word(words, 0x1000+i, int.from_bytes(window[i:i+2], 'big'))
            words.extend([0x6810, 0xa2])
            for address, value in ((0x2846, 0xfff3), (0x2848, header),
                                   (0x284a, 0), (0x284c, 0)):
                write_word(words, address, value, banked=True)
            # C stack arguments: far buffer, length, forward direction (0).
            for value in (0, len(window), 0x1000, 0):
                words.extend([0x68f0, value, 0x58f0])
            words.extend([0xbd20, 0xe2b4, 0x70ff, 8])
            words.extend([0x68f6, 0, 0x7c8c, 0x76c0, 0x7c8c, 0x76d1])
            execute(args.qemu, f'sync header={header:04x} flags={flags}', words,
                    {0: expected, 6: flags, 15: 0x6000},
                    extra_regions=((0x20e2b4, prg[0x13e2b4:0x13e45e]),),
                    verify_extra_code=True)
    # Headers straddling a refill boundary use three bytes retained by the
    # caller in A84A..A84C. Exercise both search directions independently
    # of the Info mismatch above; expected offsets come from byte position.
    header_bytes = bytes.fromhex('fff360c4')
    for backward in (False, True):
        for split in (1, 2, 3):
            if backward:
                window = bytes(12) + header_bytes[:split]
                retained = (header_bytes[split:] + bytes(3))[:3]
                expected = split
            else:
                window = header_bytes[split:] + bytes(12)
                retained = (bytes(3) + header_bytes[:split])[-3:]
                expected = (-split) & 0xffff
            words = [0x6800, 2, 0x68ff, 0x6000, 0xfc8c, 0xfd8c]
            padded = window + bytes(len(window) % 2)
            for i in range(0, len(padded), 2):
                write_word(words, 0x1000+i, int.from_bytes(padded[i:i+2], 'big'))
            words.extend([0x6810, 0xa2])
            for address, value in ((0x2846, 0xfff3), (0x2848, 0x60c4),
                                   (0x284a, int.from_bytes(retained[:2], 'big')),
                                   (0x284c, retained[2] << 8)):
                write_word(words, address, value, banked=True)
            for value in (int(backward), len(window), 0x1000, 0):
                words.extend([0x68f0, value, 0x58f0])
            words.extend([0xbd20, 0xe2b4, 0x70ff, 8])
            execute(args.qemu, f'split sync backward={backward} split={split}', words,
                    {0: expected, 15: 0x6000},
                    extra_regions=((0x20e2b4, prg[0x13e2b4:0x13e45e]),),
                    verify_extra_code=True)
    # Execute the actual metadata classifier as well. The only synthetic
    # variant replaces the four-byte Info signature with Xing; it tests the
    # branch contract, not whether rewriting real files repairs playback.
    for signature, kind, flags in ((b'Info', 0x0003, 1),
                                    (b'Xing', 0x0103, 3)):
        frame = bytearray(mp3[45:45+0x600])
        frame[13:17] = signature
        words = [0x6800, 2, 0x68ff, 0x6000, 0xfc8c, 0xfd8c, 0xfe8c]
        for i in range(0, len(frame), 2):
            write_word(words, 0x1000+i, int.from_bytes(frame[i:i+2], 'big'))
        words.extend([0x6810, 0xa2])
        fields = {0x25ac: len(mp3) >> 16, 0x25ae: len(mp3) & 65535,
                  0x25b0: 0, 0x25b2: 45, 0x25b8: 0, 0x25ba: 0,
                  0x25c8: 0x0203, 0x25ca: 0x0003, 0x25cc: 56,
                  0x25ce: 22050, 0x25d0: 182, 0x25d2: 576, 0x25da: 0}
        for address, value in fields.items():
            write_word(words, address, value, banked=True)
        for value in (0x1000, 0):
            words.extend([0x68f0, value, 0x58f0])
        words.extend([0xbd20, 0xe5b8, 0x70ff, 4])
        read_word(words, 0x25ca, 4, banked=True)
        words.extend([0x68f5, 0, 0x7c8c, 0x75c0, 0x7c8c, 0x75e1])
        execute(args.qemu, 'factory metadata ' + signature.decode(), words,
                {0: 0, 4: kind, 5: flags, 15: 0x6000},
                extra_regions=((0x20e5b8, prg[0x13e5b8:0x13e844]),),
                verify_extra_code=True)
    print('PASS: original-bit mismatch survives all masks; bitrate mismatch is conditional; six split-header directions; Xing/Info classifier cases')


if __name__ == '__main__':
    main()
