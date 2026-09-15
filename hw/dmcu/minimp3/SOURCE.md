# minimp3 source pin

Upstream: https://github.com/lieff/minimp3

Commit: `ea99364f61c14656440e8d77e9c233ccf3124633`, obtained 2026-09-07.

Unmodified upstream files:

- `minimp3.h`: SHA256 `57e437c5c1f0e8b243885d3929c8973b5e6c778451e0100ab4251d19915cb3ad`
- `LICENSE`: SHA256 `6a1ee543e5282cd9061881edf462e6fdab181f328da71fc2c9a6950a80e94d01` (CC0-1.0)

Used by the new ROM 01/02 MP3 HLE codec kernel, not by the legacy `rom-hle`
UI. Initial build uses `MINIMP3_ONLY_MP3` and `MINIMP3_NO_SIMD`; no whole-file
API, resampling, gain adjustment, automatic delay trimming, or file I/O.
The kernel is used by the opt-in `rom-mp3-hle-base` adapter for registered
missing ROM 01/02 services. It decodes only compressed frames already staged
by the guest; it does not open music files or bypass the device audio path.
