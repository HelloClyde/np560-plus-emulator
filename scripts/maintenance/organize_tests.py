"""One-time mechanical migration of flat Python/JS tests into scripts/tests.

Run from the checkout; existing test bodies are preserved, with import/path fixes.
Refuses destination collisions. Kept as an auditable record of the migration.
"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
TARGET = SCRIPTS / "tests"


def main():
    files = sorted(p for p in SCRIPTS.iterdir()
                   if p.name.startswith("test_") and p.suffix in (".py", ".js"))
    if not files:
        print("Already organized")
        return
    TARGET.mkdir(exist_ok=True)
    if any((TARGET / p.name).exists() for p in files):
        raise RuntimeError("Test destination already exists")
    names = {p.name for p in files}
    for path in files:
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".py":
            text = re.sub(r'Path\(\s*__file__\s*\)\.resolve\(\)\.parents\[1\]',
                          'Path(__file__).resolve().parents[2]', text)
            text = text.replace('Path(__file__).resolve().parent.parent',
                                'Path(__file__).resolve().parents[2]')
            # with_name used to locate root-level tools or C reference sources.
            def sibling(match):
                name = match.group(2)
                if name in names:
                    return match.group(0)
                return '(Path(__file__).resolve().parent.parent / ' + repr(name) + ')'
            text = re.sub(r'Path\(__file__\)(?:\.resolve\(\))?\.with_name\(([\'"])([^\'"]+)\1\)',
                          sibling, text)
            tree = ast.parse(text)
            insert = 0
            for i, node in enumerate(tree.body):
                if (i == 0 and isinstance(node, ast.Expr) and
                        isinstance(node.value, (ast.Str, ast.Constant))):
                    insert = node.end_lineno
                elif isinstance(node, ast.ImportFrom) and node.module == "__future__":
                    insert = node.end_lineno
                else:
                    break
            # Keep shebang/comments before the bootstrap for files without docstrings.
            if not insert and tree.body:
                insert = tree.body[0].lineno - 1
            lines = text.splitlines(keepends=True)
            lines.insert(insert, '\n# Standalone and discovery-mode test imports.\n'
                         'import sys as _test_sys\nfrom pathlib import Path as _TestPath\n'
                         '_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))\n'
                         '_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))\n'
                         '_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))\n\n')
            text = ''.join(lines)
        else:
            text = text.replace('require("./web/', 'require("../web/')
            text = text.replace('__dirname, "web/', '__dirname, "../web/')
        (TARGET / path.name).write_bytes(text.encode("utf-8"))
        path.unlink()
    # Update checked-in code/docs callers, not generated tmp evidence or QEMU.
    candidates = [ROOT / 'README.md', *SCRIPTS.rglob('*'), * (ROOT / 'doc').rglob('*.md')]
    for path in candidates:
        if not path.is_file() or path.suffix not in ('.py', '.ps1', '.js', '.md'):
            continue
        if path == Path(__file__).resolve() or 'vendor' in path.parts:
            continue
        original = text = path.read_text(encoding='utf-8')
        for name in names:
            text = text.replace('scripts/' + name, 'scripts/tests/' + name)
            text = text.replace('scripts\\' + name, 'scripts\\tests\\' + name)
            for quote in ('"', "'"):
                text = re.sub(r'([\'"]scripts[\'"]\s*/\s*)' + re.escape(quote + name + quote),
                              lambda m: m.group(1) + quote + 'tests' + quote + ' / ' + quote + name + quote, text)
                if path.suffix == '.ps1':
                    text = text.replace('$PSScriptRoot ' + quote + name + quote,
                                        '$PSScriptRoot ' + quote + 'tests/' + name + quote)
        if text != original:
            path.write_bytes(text.encode('utf-8'))
    print(f'Moved {len(files)} tests')


if __name__ == '__main__':
    main()
