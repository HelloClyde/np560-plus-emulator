#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exhaustively check indexed observer dispatch against the archived linear map.

Compiles the production C lookup, not a Python translation. All 2^24 guest
addresses, first-match duplicate semantics and out-of-range keys are checked.
This proves lookup equivalence, not complete emulator or audio performance.
"""

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cc', default='cc')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[2]
    header = root/'qemu-dmcu/target/dmcu/observer-sites.h'
    reference = root/'scripts/fixtures/np560_application_observer_sites.json'
    original = json.loads(reference.read_text())['entries']
    count = int(re.search(r'#define DMCU_APPLICATION_TRACE_ENTRIES (\d+)',
                         (header.parent/'cpu.h').read_text()).group(1))
    assert len(original) == count == 191
    expected = {}
    for index, address in enumerate(original): expected.setdefault(address, index)
    pairs = ',\n'.join('{%du,%du}' % pair for pair in sorted(expected.items()))
    source = '''#include <stdint.h>
#include <stdio.h>
#define DMCU_APPLICATION_TRACE_ENTRIES %d
#include "%s"
static const unsigned reference[][2] = {%s};
int main(void) {
    unsigned cursor = 0;
    for (uint32_t pc = 0; pc < 0x1000000u; pc++) {
        unsigned want = DMCU_APPLICATION_TRACE_ENTRIES;
        if (cursor < sizeof(reference)/sizeof(reference[0]) && pc == reference[cursor][0]) {
            want = reference[cursor++][1];
        }
        unsigned got = dmcu_application_trace_index(pc);
        if (got != want) { fprintf(stderr,"pc=%%06x got=%%u want=%%u\\n",pc,got,want); return 1; }
    }
    for (unsigned i = 0; i < sizeof(reference)/sizeof(reference[0]); i++) {
        if (dmcu_application_trace_index(reference[i][0] | 0x1000000u) != DMCU_APPLICATION_TRACE_ENTRIES) return 2;
    }
    if (dmcu_application_trace_index(0xffffffffu) != DMCU_APPLICATION_TRACE_ENTRIES) return 3;
    puts("All 16777216 guest addresses and out-of-range keys match original first-match semantics.");
    return 0;
}
''' % (count, header.as_posix(), pairs)
    path = args.output/'lookup-test.c'; binary = args.output/'lookup-test'
    path.write_text(source)
    report = dict(passed=False, reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
                  header_sha256=hashlib.sha256(header.read_bytes()).hexdigest(),
                  original_slots=count, unique_sites=len(expected), tested_guest_addresses=1 << 24)
    try:
        subprocess.run([args.cc, '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        str(path), '-o', str(binary)], check=True, timeout=30)
        result = subprocess.run([str(binary.resolve())], capture_output=True, text=True, timeout=30)
        report.update(passed=result.returncode == 0, exit_code=result.returncode,
                      stdout=result.stdout, stderr=result.stderr)
        print(result.stdout+result.stderr, end='')
    finally:
        (args.output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
