# 测试目录

本目录包含 219 个 Python 测试文件和 2 个 JavaScript 测试文件；不是全部都能用同一个命令运行。

- **工具/逻辑回归**：例如 `test_import_np560_vendor_file.py`、`test_np560_web_speed.py`、
  `test_probe_np560_matrix_route.py`。通常定义 unittest.TestCase，可单独运行或定向 discovery。
- **浏览器逻辑回归**：`test_np560_pointer_input.js`、`test_np560_audio_output.js`，使用 Node.js。
- **固件依赖回归**：如 `test_np560_web_frontend.py`，会读取合法取得的本地原厂固件。
- **QEMU/硬件集成**：如 `test_np560_instruction_clock.py`、`test_np560_nand.py`，
  需要构建后的 QEMU、固件/ROM 或命令行参数。查看文件帮助后使用独立实例运行。
- **科学计算依赖**：`test_np560_audio_delivery_analysis.py` 需要 NumPy。

不能直接把全目录 discovery 的结果当成无依赖单元测试成绩：
`test_np560_arena_release_mapping.py` 是带必填参数的独立硬件检查入口。
不要让诊断测试连接到正在试玩的实例，除非明确知道它会执行哪些操作。

PS1 测试包装器和 C 参考实现暂时保留在 `scripts/` 根目录，路径已适配这里的测试入口。
完整脚本分类见 [../CATALOG.md](../CATALOG.md)。
