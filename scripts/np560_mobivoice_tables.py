"""Mode-5 lookup values reconstructed from the isolated codec candidate.

These are numeric lookup values for interoperability tests, not a copy of the
candidate DLL and not evidence of the NP560 mask ROM's exact tables.  The
independent excitation stages use these values without reading candidate
runtime memory; the diagnostic trace checks them against the reviewed DLL.
"""

from __future__ import annotations


# The interpolator's pointer is centered at element 47.  The 29-tap path
# accesses element 47 + 3 * step + fraction for step -14..14.
INTERPOLATION_TAPS = (
    16384, 32767, 0, 49, 53, 0, -64, -72, 0, 95, 109, 0, -145, -166, 0, 217,
    247, 0, -316, -355, 0, 446, 498, 0, -617, -684, 0, 839, 928, 0, -1135, -1256,
    0, 1543, 1715, 0, -2145, -2418, 0, 3150, 3662, 0, -5269, -6653, 0, 13488, 27067, 32767,
    27067, 13488, 0, -6653, -5269, 0, 3662, 3150, 0, -2418, -2145, 0, 1715, 1543, 0, -1256,
    -1135, 0, 928, 839, 0, -684, -617, 0, 498, 446, 0, -355, -316, 0, 247, 217,
    0, -166, -145, 0, 109, 95, 0, -72, -64, 0, 53, 49, 0, 0,
)

PULSE_POSITIONS = (
    8, 15, 27, 53, 11, 17, 40, 57, 7, 9, 16, 34, 9, 52, 56, 74,
    40, 41, 51, 58, 11, 24, 25, 49, 17, 19, 29, 42, 36, 46, 62, 67,
    15, 40, 41, 45, 4, 18, 25, 42, 5, 20, 47, 50, 11, 32, 63, 66,
    0, 7, 19, 65, 0, 8, 39, 62, 22, 25, 46, 74, 12, 48, 55, 61,
    0, 5, 26, 40, 15, 25, 39, 71, 40, 49, 49, 60, 9, 10, 21, 37,
    5, 7, 10, 75, 28, 39, 58, 67, 2, 22, 23, 55, 18, 20, 23, 28,
    10, 25, 47, 54, 22, 29, 68, 72, 24, 34, 34, 63, 20, 31, 62, 79,
    8, 21, 66, 69, 39, 40, 41, 62, 21, 62, 72, 75, 24, 48, 79, 79,
    20, 22, 25, 42, 16, 56, 67, 75, 0, 28, 73, 74, 11, 45, 49, 60,
    14, 19, 40, 41, 10, 26, 28, 28, 2, 6, 45, 46, 18, 29, 37, 71,
    2, 2, 13, 63, 1, 14, 58, 69, 3, 4, 7, 72, 17, 21, 27, 69,
    4, 13, 28, 31, 3, 30, 37, 39, 46, 52, 53, 76, 13, 40, 42, 76,
    11, 21, 76, 79, 2, 10, 25, 61, 9, 30, 41, 67, 28, 29, 29, 66,
    27, 41, 42, 48, 27, 37, 37, 77, 2, 12, 42, 47, 6, 16, 32, 47,
    14, 28, 32, 36, 15, 22, 23, 49, 8, 53, 67, 71, 11, 35, 47, 61,
    50, 61, 62, 70, 12, 31, 63, 70, 33, 56, 66, 71, 27, 57, 62, 76,
)

PULSE_AMPLITUDES = (
    0, 1, 2, 4, 8, 16, 32, 64, 112, 176, 256, 352, 464, 592, 736, 896,
    1072, 1264, 1472, 1696, 1936, 2192, 2464, 2752, 3056, 3376, 3712, 4064, 4432, 4816, 5216, 5632,
)

PITCH_GAINS = (
    0, 1489, 2979, 4468, 5958, 7447, 8937, 10426,
    11916, 13405, 14895, 16384, 17874, 19363, 20853, 22342,
)

# Per-dimension recursive LSF predictor parameters, config +0x24/+0x28.
LSF_BIAS = (
    1242, 2051, 3362, 4965, 6570, 8099, 9715, 11236, 12895, 14285,
)
LSF_PREDICTOR_GAIN = (
    27514, 27196, 26827, 27361, 27631, 27177, 26337, 24235, 24862, 25297,
)

# 65 indexed cosine/interpolation values, config +0x08.  Entry 64 is the
# candidate's observed boundary/sentinel value; the following word belongs
# to the adjacent pulse-amplitude table and is deliberately excluded.
LSF_COSINE_TABLE = (
    32767, 32728, 32610, 32413, 32138, 31785, 31357, 30852,
    30273, 29621, 28898, 28106, 27245, 26319, 25330, 24279,
    23170, 22005, 20787, 19519, 18204, 16846, 15446, 14010,
    12539, 11039, 9512, 7961, 6392, 4808, 3211, 1607,
    0, -1607, -3211, -4808, -6392, -7961, -9512, -11039,
    -12539, -14010, -15446, -16846, -18204, -19519, -20787, -22005,
    -23170, -24279, -25330, -26319, -27245, -28106, -28898, -29621,
    -30273, -30852, -31357, -31785, -32138, -32413, -32610, -32728,
    32767,
)


def interpolation_phase_taps(fraction: int) -> tuple[int, ...]:
    """Return the 29 coefficients for a fractional adaptive excitation."""
    if fraction not in (-1, 0, 1):
        raise ValueError("candidate interpolation fraction must be -1, 0 or 1")
    return tuple(INTERPOLATION_TAPS[47 + 3 * step + fraction]
                 for step in range(-14, 15))
