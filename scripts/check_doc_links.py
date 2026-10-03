#!/usr/bin/env python3
"""Check local Markdown links in the NP560 documentation and entry READMEs."""

from __future__ import annotations

from pathlib import Path
import re
import sys
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
INLINE = re.compile(r"\]\((<[^>]+>|[^\s)]+)")
REFERENCE = re.compile(r"^\s*\[[^]]+\]:\s*(<[^>]+>|\S+)", re.MULTILINE)


def check() -> int:
    candidates = [ROOT / "README.md", ROOT / "scripts" / "README.md",
                  *(ROOT / "doc").rglob("*.md")]
    failures = []
    checked = 0
    optional = 0
    for source in candidates:
        if not source.is_file():
            continue
        content = source.read_text(encoding="utf-8")
        for match in [*INLINE.finditer(content), *REFERENCE.finditer(content)]:
            raw = match.group(1).strip("<>")
            if not raw or raw.startswith(("#", "//", "/")) or re.match(
                    r"^[A-Za-z][A-Za-z0-9+.-]*:", raw):
                continue
            target = unquote(raw.split("#", 1)[0].split("?", 1)[0])
            if not target:
                continue
            target_path = (source.parent / target).resolve()
            if target_path.is_relative_to(ROOT / "tmp"):
                optional += 1  # Local, ignored experiment outputs are not part of Git.
                continue
            checked += 1
            if not target_path.exists():
                line = content.count("\n", 0, match.start()) + 1
                failures.append(f"{source.relative_to(ROOT)}:{line}: {raw}")
    if failures:
        print("Broken local Markdown links:")
        print("\n".join(failures))
    print(f"Checked {checked} local links in {len(candidates)} Markdown files; "
          f"{len(failures)} broken; {optional} optional tmp links skipped")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(check())
