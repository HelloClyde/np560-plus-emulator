#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Inventory the control observer's writes/calls using a C syntax tree.

This is a source-audit aid, NOT alias analysis or a proof of harmlessness.
External call boundaries, output pointers and consumers still need review.
Requires pycparser. Does not compile, execute or modify any guest code.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

from pycparser import c_ast, c_generator, c_parser


TYPE_PREFIX = """typedef int CPUDMCUState;
typedef unsigned int uint32_t; typedef unsigned short uint16_t;
typedef unsigned char uint8_t; typedef unsigned long long uint64_t;
typedef int int32_t; typedef short int16_t; typedef int bool;
typedef unsigned long size_t;
"""
EXTRA = {'reset_npe_game_trace', 'clock_resource_release_bitmap',
         'npe_stream_position', 'rom_argument', 'log_application_far_words'}
TOKEN = r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*'


def clean(source):
    return re.sub(TOKEN, lambda m: re.sub(r'[^\n]', ' ', m[0])
                  if m[0].startswith('/') else m[0], source)


def function(source, name):
    found = re.search(r'(?m)^static [^;{}]*?\b'+re.escape(name)+
                      r'\([^;{}]*\)\s*\{', source)
    if found is None:
        raise ValueError(f'missing definition: {name}')
    masked = re.sub(TOKEN, lambda m: re.sub(r'[^\n]', ' ', m[0]), source)
    pos = found.end(); depth = 1
    while depth:
        if masked[pos] == '{': depth += 1
        elif masked[pos] == '}': depth -= 1
        pos += 1
    return source[found.start():pos], source.count('\n', 0, found.start())+1


class Inventory(c_ast.NodeVisitor):
    def __init__(self):
        self.calls = set(); self.fields = set(); self.pointer_writes = set()
        self.memory_destinations = set(); self.indirect_calls = set()
        self.pointer_parameters = set()
        self.generator = c_generator.CGenerator()

    def write(self, expr):
        original = expr
        if isinstance(expr, c_ast.UnaryOp) and expr.op == '&': expr = expr.expr
        while isinstance(expr, c_ast.ArrayRef): expr = expr.name
        if isinstance(expr, c_ast.StructRef) and isinstance(expr.name, c_ast.ID) and expr.name.name == 'env':
            self.fields.add(expr.field.name)
        elif not isinstance(expr, c_ast.ID):
            self.pointer_writes.add(self.generator.visit(expr))
        elif expr.name in self.pointer_parameters:
            self.pointer_writes.add(self.generator.visit(original))

    def visit_FuncDef(self, node):
        for param in node.decl.type.args.params:
            if isinstance(param.type, (c_ast.PtrDecl, c_ast.ArrayDecl)):
                self.pointer_parameters.add(param.name)
        self.generic_visit(node)

    def visit_Assignment(self, node):
        self.write(node.lvalue); self.generic_visit(node)

    def visit_UnaryOp(self, node):
        if node.op in ('++', '--', 'p++', 'p--'): self.write(node.expr)
        self.generic_visit(node)

    def visit_FuncCall(self, node):
        if isinstance(node.name, c_ast.ID):
            self.calls.add(node.name.name)
            if node.name.name in ('memset', 'memcpy'):
                dst = node.args.exprs[0]
                self.memory_destinations.add(self.generator.visit(dst)); self.write(dst)
        else: self.indirect_calls.add(self.generator.visit(node.name))
        self.generic_visit(node)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True); args = p.parse_args()
    root = Path(__file__).resolve().parent.parent
    path = root/'qemu-dmcu/target/dmcu/helper.c'
    raw = path.read_bytes(); source = clean(raw.decode('utf-8'))
    report = dict(source_sha256=hashlib.sha256(raw).hexdigest(), functions={},
                  alias_analysis=False, guest_semantics_proven=False)
    pending = ['trace_control_transfer']; fields = set(); external = set()
    while pending:
        name = pending.pop()
        if name in report['functions']: continue
        body, line = function(source, name)
        tree = c_parser.CParser().parse(TYPE_PREFIX+body)
        inv = Inventory(); inv.visit(tree); fields |= inv.fields
        follow = {c for c in inv.calls if c.startswith(('trace_', 'snapshot_')) or c in EXTRA}
        pending.extend(follow); external |= inv.calls-follow
        report['functions'][name] = dict(line=line, lines=body.count('\n')+1,
            calls=sorted(inv.calls), written_env_fields=sorted(inv.fields),
            pointer_writes=sorted(inv.pointer_writes),
            memory_destinations=sorted(inv.memory_destinations),
            indirect_calls=sorted(inv.indirect_calls))
    migration = (path.parent/'machine.c').read_text(encoding='utf-8')
    serialized = set(re.findall(r'ENV_(?:U32|BOOL)\((\w+)\)', migration)) | {'gpr', 'sfr'}
    report.update(written_env_fields=sorted(fields), external_calls=sorted(external),
                  serialized_field_writes=sorted(fields & serialized))
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2); stream.write('\n')
    print(json.dumps(dict(output=str(args.output), functions=len(report['functions']),
        written_fields=len(fields), serialized_field_writes=report['serialized_field_writes'],
        external_calls=report['external_calls'])))


if __name__ == '__main__': main()
