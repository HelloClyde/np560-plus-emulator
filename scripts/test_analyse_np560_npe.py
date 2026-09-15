from __future__ import annotations

import unittest

from scripts import analyse_np560_npe as npe


def sample_blob(
        *, title: str = "英雄传奇", second_payload: bytes = b"MThd" + b"B" * 12,
) -> bytes:
    first_payload = b"A" * 0x100
    payloads = (first_payload, second_payload)
    blob = bytearray(npe.SECTION_TABLE_END + sum(map(len, payloads)))
    blob[:len(npe.MAGIC)] = npe.MAGIC
    encoded_title = title.encode("gb18030") + b"\0"
    blob[npe.TITLE_OFFSET:npe.TITLE_OFFSET + npe.TITLE_SIZE] = (
        encoded_title.ljust(npe.TITLE_SIZE, b"\xCC")
    )

    first_end = npe.SECTION_TABLE_END + len(first_payload)
    vectors = (0, npe.SECTION_TABLE_END, first_end - 2, 1, 2, 3, 4, 5, 6)
    for index, value in enumerate(vectors):
        start = npe.VECTOR_OFFSET + index * 2
        blob[start:start + 2] = value.to_bytes(2, "big")
    blob[npe.FIRST_SECTION_END_OFFSET:npe.FIRST_SECTION_END_OFFSET + 2] = (
        first_end.to_bytes(2, "big")
    )

    offset = npe.SECTION_TABLE_END
    for index, payload in enumerate(payloads):
        record = npe.SECTION_TABLE_OFFSET + index * npe.SECTION_RECORD_SIZE
        blob[record:record + 4] = offset.to_bytes(4, "big")
        blob[record + 4:record + 8] = len(payload).to_bytes(4, "big")
        blob[offset:offset + len(payload)] = payload
        offset += len(payload)
    return bytes(blob)


class NpeAnalysisTests(unittest.TestCase):
    def test_recognises_indexed_question_records(self) -> None:
        records = [
            "问题一\0A.甲\0B.乙\0C.丙\0D.丁\0".encode("gb18030") + b"\0" * 10,
            "问题二\0A.春\0B.夏\0C.秋\0D.冬\0".encode("gb18030") + b"\0" * 10,
        ]
        table_end = 22 + len(records) * 4
        offsets = []
        cursor = table_end + 4
        for record in records:
            offsets.append(cursor)
            cursor += len(record)
        payload = bytearray(cursor)
        payload[0:2] = len(records).to_bytes(2, "big")
        payload[2:4] = len(records).to_bytes(2, "big")
        for index, offset in enumerate(offsets):
            start = 22 + index * 4
            payload[start:start + 4] = offset.to_bytes(4, "big")
        payload[table_end:table_end + 4] = b"\xFF" * 4
        for offset, record in zip(offsets, records):
            payload[offset:offset + len(record)] = record
        detected = npe._indexed_question_records(bytes(payload))
        self.assertIsNotNone(detected)
        assert detected is not None
        self.assertEqual(detected["record_count"], 2)
        self.assertEqual(detected["category_counts"], [2] + [0] * 9)
        self.assertEqual(detected["first_record_offset"], table_end + 4)

    def test_recognises_repeated_fullscreen_packed4_structure(self) -> None:
        header = (
            (0x1001).to_bytes(2, "little") + b"\0\0\0\0" +
            (240).to_bytes(2, "little") + (120).to_bytes(2, "little")
        )
        payload = (header + bytes(npe.PACKED4_PAYLOAD_SIZE)) * 3
        detected = npe._packed4_fullscreen_array(payload)
        self.assertIsNotNone(detected)
        assert detected is not None
        self.assertEqual(detected["record_count"], 3)
        self.assertEqual(detected["record_size"], 0x384A)
        self.assertEqual(detected["width"], 240)
        self.assertEqual(detected["height"], 120)

    def test_rejects_near_miss_fullscreen_structure(self) -> None:
        self.assertIsNone(
            npe._packed4_fullscreen_array(bytes(npe.PACKED4_RECORD_SIZE))
        )

    def test_recovers_observed_header_and_contiguous_sections(self) -> None:
        result = npe.analyse_blob(sample_blob(), name="hero.npe")
        self.assertEqual(result["magic"], "NP560 RPG2.1")
        self.assertEqual(result["title"], "英雄传奇")
        self.assertEqual(result["layout"]["active_sections"], 2)
        self.assertTrue(result["layout"]["sections_are_contiguous"])
        self.assertTrue(result["layout"]["sections_cover_file"])
        self.assertTrue(result["layout"]["first_section_end_marker_matches"])
        self.assertEqual(result["signature_hits"]["MIDI"], ["0x0000045A"])

    def test_rejects_wrong_magic(self) -> None:
        damaged = bytearray(sample_blob())
        damaged[0] ^= 1
        with self.assertRaisesRegex(ValueError, "magic mismatch"):
            npe.analyse_blob(bytes(damaged))

    def test_rejects_noncontiguous_descriptor(self) -> None:
        damaged = bytearray(sample_blob())
        second = npe.SECTION_TABLE_OFFSET + npe.SECTION_RECORD_SIZE
        offset = int.from_bytes(damaged[second:second + 4], "big")
        damaged[second:second + 4] = (offset - 1).to_bytes(4, "big")
        with self.assertRaisesRegex(ValueError, "not contiguous"):
            npe.analyse_blob(bytes(damaged))

    def test_rejects_active_descriptor_after_unused_slot(self) -> None:
        damaged = bytearray(sample_blob())
        first = npe.SECTION_TABLE_OFFSET
        second = first + npe.SECTION_RECORD_SIZE
        damaged[first:first + 4] = b"\0\0\0\0"
        with self.assertRaisesRegex(ValueError, "follows a zero-offset slot"):
            npe.analyse_blob(bytes(damaged))

    def test_collection_reports_layout_clusters_and_duplicates(self) -> None:
        first = npe.analyse_blob(sample_blob(), name="first.npe")
        second = npe.analyse_blob(sample_blob(), name="second.npe")
        groups = {
            npe._layout_cluster_key(first): [first, second],
        }
        self.assertEqual(len(groups), 1)
        self.assertEqual(first["sha256"], second["sha256"])

    def test_title_must_be_gb18030(self) -> None:
        damaged = bytearray(sample_blob())
        damaged[npe.TITLE_OFFSET:npe.TITLE_OFFSET + 2] = b"\x81\x30"
        damaged[npe.TITLE_OFFSET + 2] = 0
        with self.assertRaisesRegex(ValueError, "invalid GB18030"):
            npe.analyse_blob(bytes(damaged))


if __name__ == "__main__":
    unittest.main()
