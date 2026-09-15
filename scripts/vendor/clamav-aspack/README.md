# ClamAV ASPack decompression for NP560 static analysis

Retrieved 2026-09-07 from the upstream Cisco-Talos repository:

- https://raw.githubusercontent.com/Cisco-Talos/clamav/main/libclamav/aspack.c
  Original SHA-256: `48fd1200df6f2313004df5dbb0a102efeeca88d9ad846da18fdf252fcd1a635b`.
- https://raw.githubusercontent.com/Cisco-Talos/clamav/main/libclamav/aspack.h
  Original SHA-256: `8cb7d141b557b274de469a9bbb48ea6bc4327d53edd8bed85a9cacfdad65c4e5`.
- https://raw.githubusercontent.com/Cisco-Talos/clamav/main/libclamav/pe.c
  Original SHA-256: `8deb265875c10d31e53ecb759ef08cfcc6e0e06fab4893f40e76e995906e75c4`.

Only `aspack.c` is compiled here. Original source copyright and GPLv2 terms
are retained. `COPYING` is the GPLv2 text copied from the workspace's QEMU tree
(SHA-256 `6f04ae8364d0079a192b14635f4b1da294ce18724c034c39a6a41d1b09df6100`).

Local changes to upstream `aspack.c`: replace ClamAV includes with the minimal
`np560_aspack_compat.h` adapter; replace the successful PE rebuild log message
with one explicitly identifying an RVA-only dump. Decompression and call/jump
unfiltering are unchanged. The adapter does **not** rebuild an executable PE or
its import table, and never invokes the target program's entry point.

`scripts/unpack_np560_aspack.c` supports recognized ASPack 2.12 x86 PE32 inputs
only, checks image/section/block bounds, limits allocations and refuses to
overwrite results. Compile with AddressSanitizer and UndefinedBehaviorSanitizer
as shown in its file header. Run under a bounded timeout.

Validated input: NoahMediaMaker `Compile.dll`, SHA-256
`4287f1b6608eb708ca67c0ff7b0957c5d7cd1a89bc3c4855659359f5b8eb200a`.
All five blocks decompressed without sanitizer diagnostics. Refusal tests for
an existing destination and a UPX input return 1; wrong-format input creates no
output. This validates the analysis adapter, not any NP560 audio algorithm.
