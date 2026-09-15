# SPDX-License-Identifier: GPL-2.0-or-later
"""Explicit fragment and address checks for the native MP3 ROM builders."""


def code_span(address, data):
    assert address % 2 == 0 and len(data) % 2 == 0 and data
    assert 0 <= address < address+len(data) <= 0x1000000
    assert address >> 16 == (address+len(data)-1) >> 16, "near code crosses CS"


def near_table(address, data):
    assert address % 2 == 0 and len(data) % 2 == 0 and data
    assert 0 <= address < address+len(data) <= 0x1000000
    assert address >> 15 == (address+len(data)-1) >> 15, "near table crosses DS bank"


def fragments(core):
    yield "code",core["code_address"],core["code"]
    if "tables" in core:
        yield "tables",core["table_address"],core["tables"]
    for part in core.get("table_parts",()):
        yield part["name"],part["address"],part["data"]


def validate(cores):
    ranges = []
    for name,core in cores.items():
        code_span(core["code_address"],core["code"])
        for kind,address,data in fragments(core):
            assert address % 2 == 0 and len(data) % 2 == 0
            assert 0 <= address < address+len(data) <= 0x1000000
            ranges.append((address,address+len(data),name+"-"+kind))
    ranges.sort()
    for left,right in zip(ranges,ranges[1:]):
        assert left[1] <= right[0], ("overlapping native MP3 fragments",left,right)
    return ranges
