#!/usr/bin/env python3

from pathlib import PurePath
import errno
import json
import os
import subprocess
import sys

def destdir_join(d1: str, d2: str) -> str:
    if not d1:
        return d2
    # c:\destdir + c:\prefix must produce c:\destdir\prefix
    return str(PurePath(d1, *PurePath(d2).parts[1:]))

introspect = os.environ.get('MESONINTROSPECT')
out = subprocess.run([*introspect.split(' '), '--installed'],
                     stdout=subprocess.PIPE, check=True).stdout
warned_no_windows_symlink_privilege = False
for source, dest in json.loads(out).items():
    bundle_dest = destdir_join('qemu-bundle', dest)
    path = os.path.dirname(bundle_dest)
    try:
        os.makedirs(path, exist_ok=True)
    except BaseException as e:
        print(f'error making directory {path}', file=sys.stderr)
        raise e
    try:
        os.symlink(source, bundle_dest)
    except OSError as e:
        if e.errno == errno.EEXIST:
            continue
        # The install-tree bundle is optional when running a build-tree QEMU
        # binary directly.  Standard Windows accounts cannot create symlinks
        # without Developer Mode; do not make that OS setting a build
        # prerequisite or silently replace links with stale file copies.
        if os.name == 'nt' and getattr(e, 'winerror', None) == 1314:
            if not warned_no_windows_symlink_privilege:
                print('Windows symlink privilege unavailable; skipping the '
                      'optional qemu-bundle link tree', file=sys.stderr)
                warned_no_windows_symlink_privilege = True
            continue
        print(f'error making symbolic link {dest}', file=sys.stderr)
        raise
