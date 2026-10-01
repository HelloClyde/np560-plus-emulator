"""Generate the checked-in script-purpose index; --check detects stale output."""
import argparse
import ast
from collections import defaultdict
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
OUTPUT = SCRIPTS / "CATALOG.md"
TITLES = {
    "runtime": "模拟器运行与管理",
    "tests": "自动测试、测试包装器与 C 参考程序",
    "reverse": "逆向分析、反汇编与格式研究",
    "diagnostics": "运行时调试、采样、交互探针与性能测量",
    "builders": "ROM/HLE 构建、补丁与 NAND 内容加工",
    "shared": "共享模块与早期实验模型",
    "maintenance": "仓库维护与整理",
}


def category(path):
    name = path.name
    if "maintenance" in path.parts:
        return "maintenance"
    if "tests" in path.parts or name.startswith(("test_", "test-")) or name in (
            "np560_cpu_vmstate_test.c", "np560_journal_faults.c"):
        return "tests"
    if "web" in path.parts or name.startswith("serve_") or name in (
            "run-np560.ps1", "run-np560-web.ps1", "build-np560.ps1",
            "np560_lan_proxy.py", "np560_device_backup.py", "manage-np560-device.ps1",
            "move-np560-restored-device.ps1", "preflight-np560.ps1"):
        return "runtime"
    if name.startswith(("analyse_", "analyze_", "audit_", "compare_", "scan_", "extract_",
                        "disassemble_", "unpack_", "inspect_", "preprocess_")) or name in (
            "np560_disasm.py", "np560_aux_disasm.py", "np560_upd.py", "np560_aspack_compat.h"):
        return "reverse"
    if name.startswith(("probe_", "probe-", "monitor_", "capture_", "dump_", "trace_", "watch_",
                        "watch-", "benchmark_", "triage_", "search_", "wait_", "verify_",
                        "explore_", "render_", "qmp_read_", "merge_")):
        return "diagnostics"
    if name.startswith(("build_", "patch_", "seed_", "inject_", "ensure_", "repair_",
                        "finalize_", "mirror_", "publish_", "import_", "burn_")) or name == "np560_checkpoint_rehash.c":
        return "builders"
    if name == "cleanup_expired_nand.ps1":
        return "maintenance"
    return "shared"


def summary(path):
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        doc = ast.get_docstring(ast.parse(text))
        if doc:
            return " ".join(doc.splitlines()[0].split()).replace("|", "\\|")
    return {"tests": "测试/参考实现；依赖及运行参数见文件。",
            "runtime": "运行入口或运行实现，参数/用途见文件。",
            "maintenance": "仓库或本地资产维护，运行前检查目标范围。"}.get(category(path), "用途与参数见源文件。")


def render():
    groups = defaultdict(list)
    for path in sorted(SCRIPTS.rglob("*")):
        if (not path.is_file() or path.suffix not in (".py", ".ps1", ".js", ".c", ".h", ".html", ".css")
                or any(part in ("vendor", "fixtures", "__pycache__", "qemu-patches") for part in path.relative_to(SCRIPTS).parts)):
            continue
        groups[category(path)].append(path)
    lines = ["# 脚本分类全表", "", "由 `maintenance/catalog_scripts.py` 生成；分类是用途，不代表生产可用或安全只读。",
             "具体使用入口与风险见 [README](README.md)。目录名 tests 不意味着全部是不依赖固件的单元测试。", ""]
    for key, title in TITLES.items():
        lines += [f"## {title}（{len(groups[key])}）", "", "| 文件 | 用途 |", "| --- | --- |"]
        for path in groups[key]:
            rel = path.relative_to(SCRIPTS).as_posix()
            lines.append(f"| [{rel}]({rel}) | {summary(path)} |")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = render()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != result:
            raise SystemExit("CATALOG.md is stale; run catalog_scripts.py")
    else:
        OUTPUT.write_bytes(result.encode("utf-8"))
