#!/usr/bin/env python3
"""Extract original audio-mode data; does not infer EQ frequencies or implement DSP."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

PRG_SHA = 'd555609e03ece17f42c1881beeb88361572f18621161de67bc9dc765857089f5'


def extract(raw):
    if hashlib.sha256(raw).hexdigest() != PRG_SHA:
        raise ValueError('unsupported PRG identity')
    table = raw[0x2d5966:0x2d5a6a]
    mode_bytes = raw[0x305a2e:0x305a3c]
    # Word storage is little-endian; DMCU byte addressing is high lane first.
    menu_modes = [mode_bytes[i ^ 1] for i in range(14)]
    assert sorted(menu_modes) == list(range(14))
    # Check the caller reads player+087B and indexes exactly this byte table.
    assert raw[0xa5980:0xa5984] == struct.pack('<HH', 0x70f1, 0x087b)
    assert raw[0xa59a2:0xa59aa] == struct.pack('<4H', 0x68f3, 0x5a2e, 0x68f2, 0x0033)
    assert raw[0xa59be:0xa59c2] == struct.pack('<HH', 0xbd33, 0x4d82)
    rows = [list(struct.unpack_from('<10H', table, 20*i)) for i in range(13)]
    return dict(prg_sha256=PRG_SHA,
                table_sha256=hashlib.sha256(table).hexdigest(),
                menu_map_sha256=hashlib.sha256(mode_bytes).hexdigest(),
                menu_index_to_mode=menu_modes,
                menu_rows=[dict(menu_index=i, mode=mode, enabled=mode != 0,
                                table_address=0x305966 + 20*(max(mode, 1)-1),
                                coefficient_words=rows[max(mode, 1)-1])
                           for i, mode in enumerate(menu_modes)],
                entries=dict(load=0x014674, enable=0x0146cc, disable=0x0146d0),
                coefficient_count=10,
                caller=dict(player_state=0x087a, required_state=10, selection=0x087b,
                            dispatch=0x0d59be, wrapper=0x334d82, mode_function=0x31f312),
                dsp_implemented=False, coefficient_format_verified=False,
                frequency_mapping_verified=False,
                caveat='static original-data contract; mode names and DSP algorithm not recovered')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prg', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = extract(args.prg.read_bytes())
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(output=str(args.output), menu_index_to_mode=report['menu_index_to_mode'])))


if __name__ == '__main__':
    main()
