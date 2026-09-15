from __future__ import annotations

# Standalone and discovery-mode test imports.
import sys as _test_sys
from pathlib import Path as _TestPath
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[2]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parents[1]))
_test_sys.path.insert(0, str(_TestPath(__file__).resolve().parent))


import struct
import tempfile
from pathlib import Path
import unittest

try:
    from scripts import preprocess_np560_nand as preprocess
except ModuleNotFoundError:  # Direct execution from scripts/.
    import preprocess_np560_nand as preprocess


def checkpoint_bytes(pages: list[bytes], oob_size: int = 4) -> bytes:
    page_data = len(pages[0])
    data = b"".join(pages)
    oob = b"\xff" * (len(pages) * oob_size)
    header = bytearray(preprocess.HEADER_SIZE)
    header[:8] = preprocess.CHECKPOINT_MAGIC
    struct.pack_into(
        preprocess.HEADER_FORMAT,
        header,
        8,
        1,
        preprocess.HEADER_SIZE,
        page_data,
        oob_size,
        2,
        len(pages) // 2,
        len(data),
        len(oob),
        0,
        0,
    )
    return bytes(header) + data + oob


def maskrom_bytes(payload: bytes) -> bytes:
    image = bytearray(preprocess.MASKROM_HEADER_SIZE)
    signature = b"MASKROM NP560 TEST"
    image[:len(signature)] = signature
    image.extend(payload)
    struct.pack_into(
        "<III",
        image,
        0x20,
        (len(image) + 0x1ff) // 0x200,
        0x12345678,
        len(image),
    )
    return bytes(image)


class PreprocessNandTests(unittest.TestCase):
    def test_maskrom_stream_is_scanned_as_2048_byte_nand_pages(self) -> None:
        logical = bytearray(b"\xff" * (preprocess.MASKROM_PAGE_DATA + 7))
        logical[32:45] = b"NEPLAYERV0.99"
        logical[preprocess.MASKROM_PAGE_DATA + 1:] = b"NPEFILE"
        physical = preprocess.pair_swap(bytes(logical))

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "MASKROM.bin"
            path.write_bytes(maskrom_bytes(physical))
            with preprocess.open_nand_source(path) as source:
                report = preprocess.build_report(
                    source, scan_all=True, include_pages=False,
                    needles={"npe": b"NPEFILE"},
                )

        self.assertEqual(report["source_format"], "maskrom-logical-stream")
        self.assertEqual(report["source_metadata"]["payload_2048_byte_pages"], 2)
        hits = {(hit["name"], hit["page"], hit["view"])
                for hit in report["hits"]}
        self.assertIn(("nwf-header", 0, "logical"), hits)
        self.assertIn(("npe", 1, "logical"), hits)

    def test_delta_finds_physical_and_logical_needles(self) -> None:
        erased = b"\xff" * 64
        direct = bytearray(erased)
        signature = b"NEPLAYERV0.99"
        direct[4:4 + len(signature)] = signature
        swapped = bytearray(erased)
        logical = bytearray(erased)
        logical[8:19] = b"LIRT    NWF"
        logical[24:35] = b"USERINFOSYS"
        swapped[:] = preprocess.pair_swap(bytes(logical))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base_path = root / "base.nand"
            candidate_path = root / "candidate.nand"
            base_path.write_bytes(checkpoint_bytes([erased] * 4))
            candidate_path.write_bytes(checkpoint_bytes([
                erased, bytes(direct), bytes(swapped), erased
            ]))
            with preprocess.Checkpoint(base_path) as base:
                with preprocess.Checkpoint(candidate_path) as candidate:
                    report = preprocess.build_report(candidate, base=base)

        self.assertEqual(report["page_count"], 2)
        self.assertEqual(report["page_ranges"], ["00000001-00000002"])
        self.assertTrue(all(page["change"] == "programmed"
                            for page in report["pages"]))
        hits = {(hit["name"], hit["page"], hit["view"])
                for hit in report["hits"]}
        self.assertIn(("nwf-header", 1, "physical"), hits)
        self.assertIn(("lirt-short", 2, "logical"), hits)
        self.assertIn(("userinfo-short", 2, "logical"), hits)

    def test_rejects_inconsistent_geometry(self) -> None:
        malformed = bytearray(checkpoint_bytes([b"\xff" * 16] * 2))
        struct.pack_into("<Q", malformed, 32, 1)
        with self.assertRaisesRegex(ValueError, "inconsistent sizes"):
            preprocess.parse_geometry(malformed)

    def test_needles_only_omits_page_payload_and_finds_factory_defaults(self) -> None:
        erased = b"\xff" * 64
        logical = bytearray(erased)
        logical[2:12] = b"7107169335"
        logical[16:20] = "阿诺".encode("gb18030")
        physical = preprocess.pair_swap(bytes(logical))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.nand"
            path.write_bytes(checkpoint_bytes([physical, erased]))
            with preprocess.Checkpoint(path) as candidate:
                report = preprocess.build_report(
                    candidate, scan_all=True, include_pages=False,
                )

        self.assertFalse(report["pages_included"])
        self.assertEqual(report["pages"], [])
        hits = {(hit["name"], hit["view"]) for hit in report["hits"]}
        self.assertIn(("userinfo-id", "logical"), hits)
        self.assertIn(("userinfo-owner-gb18030", "logical"), hits)

    def test_custom_text_and_hex_needles(self) -> None:
        needles = preprocess.custom_needles(
            ["label=hello"], ["binary=02 40 01 20 0f 00"],
        )
        self.assertEqual(needles["label"], b"hello")
        self.assertEqual(needles["binary"], b"\x02\x40\x01\x20\x0f\x00")

    def test_can_restrict_scan_to_custom_logical_needles(self) -> None:
        erased = b"\xff" * 64
        logical = bytearray(erased)
        logical[8:19] = b"USERINFOSYS"
        physical = preprocess.pair_swap(bytes(logical))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.nand"
            path.write_bytes(checkpoint_bytes([physical, erased]))
            with preprocess.Checkpoint(path) as candidate:
                report = preprocess.build_report(
                    candidate,
                    scan_all=True,
                    needles={"only-userinfo": b"USERINFOSYS"},
                    include_default_needles=False,
                    views=("logical",),
                )

        self.assertEqual(report["views"], ["logical"])
        self.assertEqual(set(report["needles"]), {"only-userinfo"})
        self.assertEqual(len(report["hits"]), 1)
        self.assertEqual(report["hits"][0]["view"], "logical")


if __name__ == "__main__":
    unittest.main()
