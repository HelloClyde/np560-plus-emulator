"""Fixed numeric codebooks from the reviewed candidate mode-5 decoder.

Only the signed 16-bit lookup data is represented here, compressed for
readability.  It is not the vendor DLL or evidence that the missing NP560
mask ROM uses byte-identical codebooks.  SHA-256 guards accidental changes.
"""

from __future__ import annotations

import base64
import hashlib
import struct
import zlib


_BOOKS = (
    (
        3,
        "126e413d82415aab4c8db1fa14405243535cdc363bc6b2d3d8d3d48b754325d3",
        (
            "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"
        ),
    ),
    (
        3,
        "096f1a091dc94710a596c1821539a7b0ec40eced37f255676ba321583391bb5e",
        (
            "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"
            "Ark="
        ),
    ),
    (
        4,
        "10842bfcb3510c1eec1f96d7349d8046ed142269064333843c78b6c6c9713f4f",
        (
            "eNoNlHl0z1caxp/3fn/5MY4SlNZyVHSEQatKqZbJiKWtorXvQlUsUcIQY+2RCuKIvQSNLQdJI639dJSWTmxjiS32GDGqKLGkQ/L7"
            "fe/7zP3r/nHf+573Pp/3ecr4Hb8S1S/RBL3MDY5ltsyVkXzBjhJhbtl17Ihp6Mf9avA1pug+fYEk9GCCXSNzEaffYCnrooCClixG"
            "FbyPQ1ookEhEaqqJxF8klT7Oc7B5pLNwkb/LSnQVRS3vEK8jQYowEseZzbXSGp9iFM7IYUzCIG4xcciURG7AHkxFMu5jO2JkHhrK"
            "KLkiExGWP1BmRqE6bmMiU/GUARmmSXiIAjzjh5KDPFTkQLMFha7LKnTASZPJfzIoCZKt7Zkkrb326vEgmyKDX/MXd3dKi/VlbYXZ"
            "7Mh4e5M12Rf7dRfv6HrOs3m8bCtzm85huqqdZxfrc62s61ikUXzMizqAs5mDKF6ytfk2ztrRmqF72BWNOFQLeQpddIE9xxK9pHfs"
            "z1jIoA7w+zh1slgTcSjUqliH7vK7pmsPHpeT9qjWY0v5jC9JfQ7hp7wAtXf1onpmA7vgib0gyZrCO27yAxwmNZHDJM2WhajBZ9xp"
            "8pmqA/SMR6YgWuLlY0cvEW1MBF/FaR4xyU6J9zA+kIlKiGcm/o5BuKXfMNJRiHUE9rh+KwHZhCbcwulog9Fah/Vki1zlMWZKqtml"
            "D/Sx5PAUb+hk5GljtNIjGIENvOmfxnSexZ/95xws33OiZqCHBOWObSQNTTtU0WRmmVFs4SdxMyY4ZjksZawYrORyp/k70gkH2ErO"
            "41Wks6dc43zJZgNvG8skn3OMoifGaLp3DtcctRSJNvtQwnhz1/uQe/GDeS5H2YSRgWLzGcqb1eaoTMFhiQ1kSAdJkVyvuzzQpnIw"
            "4h0ks6Js4DGtywz5iDM5R63cYzLzOC6QyJe4mMnoiL06SH+WDHypm2wjr56pru/rzMBQpGuhf5xJbK83bYmritSLNs2x7G3PayQK"
            "2cCPs+lco7GMtAnspC3183CeVMBqJoR3SBtWs154E14wGk/0DezlRoZtW+etWXyPJVynb7l5espip+h6zZO2zgF7bSbqy1Hk6x8Y"
            "Z6rijqsPYz3nOzZpGMBe6rqa2likC7jApOszO9e58gZz/SpYgkTd56+wvXFPZ9iZtqIU6PZQU5kg/3OqP0ap3MAh1jXxsh/d0ccc"
            "NjHuZZrpL8t4Qvd5WVKCtbrUq+iY90VuRJrkYgriZKxx5OULs0q2UuWsiMRzDF7xBphaugj5Zo5pZjqbjd4X3gI4MlKM/yBk5nrl"
            "ZYnsDDzl6xp0P4iRWjqUGdyKCy5T6rG8pNjO8kSjGWNHMFaVj8Kd2cfG4LE/XTP4Ll8LF2hX/MgZugy5WMdoHsI2qSkTdAxOoI6k"
            "2YaSJc35kW2DR6iG1X4CGuKuPggXyVbct8NCB9HKtMcpJstmjJXp/FVOo5786JKvjrnGybwltb0KbIIYM0uW8Cp2e82kDP35L8/I"
            "CD7V1IhYGYVlsggnMVnS3XblSF8MNzGyXfJw3aTJSi8T89DN5Eot0ww/mUHmEqJNqcmXr+SY/BQwgQ3sxMYYxx3akGtciqzmPR2B"
            "TzRR12gbWWh36nkuQ5Hz2Ant4LzagB+73V3JVXaIzZXNHKRTsVH+hChbnZPkA9Rid26TSZiks1jB28xE7aEVpbn00hl6Bi29c9pV"
            "d5s10trv5nuBY07hTdjIwci05WWkc/40PYlPOFuK/Vz0ZFvzbx0ipXjgqEyWfpJgXrF7xJcJWBp+y7uJX9HCLnIZ15jNw1tYSU5r"
            "J/8ZurpMehpa6Lb3e820O9nbOfycf5UzZapZG45nZRzBwLIzfIg98i4naZo+dIl8S7vYgRzMCjrWRukM5Pvnw6ucDgV+QBezwNb1"
            "W4SXs5p20x7h+s4rt21RaSUc0DdZ7Bf6BzVLp4e+DQe1h+9piT/Gtvff9quE2tmddqJdob+Eff+ybrC7Qx002b/i576I8Q/518M7"
            "9IqthGY8bHOdl/uxyNWGXKoO8/PsAe7jcBtpH7GKy9pv/Wla3fSzlXSgfUO6hyP1lM3FZH9quJGO5yb7cugYg7wcaujHuqSNKY0L"
            "+/o3HvdXlPX3K2hl/0xpSllnmxyqVrbEhiWrrFJpKNyOTbxFMlzuo34gSqK8/6JqRIZ33/zD1ChXw0jgpvncHHfndiyUTmZpcJrM"
            "N4WBvwbum+88GxwdfCyvBUZ7UVLIPoE3A8PRzu4KXvNW6mVKuV6BFdIKL7xlgd9MObltlgfHm/5oGtwYXGB+kN/KZQe3Bz6Q/wPl"
            "xglY"
        ),
    ),
)


def _decode_book(width: int, expected_sha256: str, encoded: str) -> tuple[int, ...]:
    raw = zlib.decompress(base64.b64decode(encoded))
    if len(raw) != 256 * width * 2:
        raise ValueError("candidate LSF codebook size differs")
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("candidate LSF codebook digest differs")
    return struct.unpack(f"<{256 * width}h", raw)


CODEBOOKS = tuple(_decode_book(*entry) for entry in _BOOKS)
