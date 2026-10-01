import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analyze_np560_npe_audio_corpus import inspect, summarize
from analyse_np560_npe import MAGIC, SECTION_TABLE_END, SECTION_TABLE_OFFSET


def container(payload):
    blob = bytearray(SECTION_TABLE_END)
    blob[:len(MAGIC)] = MAGIC
    for index, data in enumerate([b'X']*16 + [payload]):
        pos = SECTION_TABLE_OFFSET + index*8
        blob[pos:pos+4] = len(blob).to_bytes(4,'big')
        blob[pos+4:pos+8] = len(data).to_bytes(4,'big')
        blob.extend(data)
    return bytes(blob)


class AudioCorpusTests(unittest.TestCase):
    def test_retains_nonzero_extra_byte(self):
        payload = b'\x20\x0d\x00\x01' + b'\x55'*21 + b'\xcf'
        a = inspect(container(payload), 'a')
        sound = a['sound_candidates'][0]
        self.assertTrue(sound['matches_word_aligned_21byte_relation'])
        self.assertEqual(sound['extra_byte_hex'], 'cf')
        b = inspect(container(payload[:-1]+b'\x00'), 'b')
        self.assertEqual(summarize([a,b])['unique_count'], 2)
        self.assertEqual(summarize([a,a])['unique_count'], 1)
        self.assertFalse(summarize([a])['codec_verified'])

    def test_does_not_hide_unknown_or_bad_length(self):
        result = inspect(container(b'\x20\x01\x00\x01\x55'), 'other')
        sound = result['sound_candidates'][0]
        self.assertFalse(sound['format13_prefix'])
        self.assertEqual(len(summarize([result])['length_relation_mismatches']), 1)

    def test_rejects_truncated_or_uncovered_container(self):
        for blob in (b'', container(b'1234')[:-1], container(b'1234')+b'extra'):
            with self.assertRaises(ValueError):
                inspect(blob, 'bad')


if __name__ == '__main__':
    unittest.main()
