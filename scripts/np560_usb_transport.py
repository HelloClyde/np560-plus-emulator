"""Serialize USB wire bytes as the original loader's data-RAM stores do.

usb_dll.dll passes the payload unchanged to bulk OUT. USB_Loader_Noah.bin's
00:194C..1952 reads F230 into R0 and executes MOVB [R8++],RB1 (R0's low byte).
The DMCU memory byte lane selects the high byte at even logical addresses; the emulator's
physical RAM backing serializes 16-bit words little-endian. Consequently an
aligned, even-length wire stream needs adjacent-byte exchange before a raw
physical RAM load. This is a diagnostic transport boundary, not USB hardware
emulation or a NAND/display correction. Callers must split/pad their protocol
messages explicitly; do not guess the untouched half of an odd final word.
"""

from np560_upd import word_swap


USB_RECEIVE_STORE_PC = 0x1950
USB_RECEIVE_STORE_WORD = 0x1B81


def usb_data_to_physical_ram(payload: bytes) -> bytes:
    if not payload or len(payload) % 2:
        raise ValueError("USB staging requires a nonempty even-length payload")
    return word_swap(payload)
