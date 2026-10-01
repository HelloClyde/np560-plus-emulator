"""Owned candidate mode-5 PCM regressions using Tianjiang Fengyunlu frames."""

from __future__ import annotations

import hashlib
from pathlib import Path
import struct

import pytest

from scripts.analyse_np560_npe import _parse_sections
from scripts.np560_mobivoice_decoder import CandidateMode5Decoder


GAME = Path(r"D:\Downloads\NP560plus游戏全集\天降风云V1.3.npe")
GAME_SHA256 = "df4b52df6b69e1105a5ea6100e43f35f832ed859c10cb8714879e44ad4d8cb40"
ARNO_GAME = Path(r"D:\Downloads\NP560plus游戏全集\阿诺创世纪.npe")
ARNO_GAME_SHA256 = "0bd0e23f18461ce13e5745dba16c7acb1f9318a718d1671599eced6ccfc811a9"
ARNO_SECTION_22_PCM_SHA256 = "b368d2dfa74a9b69bf50c72d561de0624f4802da0b4e303377cc8629436e06fe"
SAMPLES = {
    20: (
        ("488e2b000e1d3579d9a81be12ccb06057dd54c76ec", "7d68146ede3a8706cb01914eecad402abb653c7dbbd8681b0552b7d8d1c34a4f"),
        ("3ad5b9064c5c46f98782d5cbe08085ec4ae700560f", "01e8929f4045949349eb429b3e8af6a807b28c096c39b4d324d2522363782179"),
        ("041f4e06ad739d76b9cd5c25234288783ce70d6fc7", "2830d6158a096c0732a97ce288bc3670369ab5d3194c34a8015c05459b895588"),
    ),
    23: (
        ("f2bcfc5d09003406403586401a0f21021511d31559", "a409aefbf1d1c2e10b5cf194e7fef451c9cb1a8a5b484368b55190f7b1220ca2"),
        ("46c3334b03b04f274c49c42c481c91cb9de10a19c9", "af35d72cd7bc203eeefd059ff6a29fe8d7d95717f3a9bb1bcf7565f2b17f560d"),
        ("0fd5a2dd00207287c02f06002e15a1499599f51621", "307e4901b97a511508aa649c89ecc5d6a1d7d3e8700ffa1092282680171f6788"),
    ),
}
FULL_SECTIONS = {
    16: (1332, "db557921bfdff2823227a02a36320d2e374e03faee5d89afc6013dc1fc3dcf41"),
    17: (717, "062184b06cdb454ff0cefedb0644a7c6731be645804f353aa0ef7b4d7642cfe3"),
    18: (581, "b3d7f0cf513568cf0ed37b39109dfd2340c34b4c032c364337d1bebe615c7cd7"),
    19: (1095, "4c53a63a318643c2cd4c18f68faaa633689c5787caeed34f1debe5dce7c41efa"),
    20: (2020, "53951460b27c576b7d607d96b783bd95101bdf5495845d81423581220530d302"),
    21: (1741, "efa505383f9740d59c68fbfc9782f32ee34620c822bafb5d5973aa843b6b4c00"),
    22: (1440, "5d033b258fe83a4413055c09b28173cdbd3f09937edf839d4077c2cdcc37b993"),
    23: (196, "f18f2a20424fdfa0c6346b03b5a8a5072f90083ca338dd9bbd7cc492f0befc57"),
    24: (280, "8610a6bb495aecc97e068b62dabf07dd5a46a9a11f46e56a89429a602c6f976e"),
    25: (98, "7df141ba2dbbb78cd6f46aad1b962e36b06b5258e9b07bbc4088764c5dcaf359"),
    26: (115, "92890b85dddb8152648c411259b243e5a59f5d3dd745d683f8f500a82ef3847c"),
    27: (180, "4d0d906c791cd090dad1038ab68853d41b030eed56c2b5695813b891ef9bbf86"),
    28: (86, "f902814792257dfd31e789568b9fcb34ba54d6d7114f94fda3c6779195a19cba"),
    29: (155, "27934d73fee16a376627e0bd7aaa23b9570fe422df4d09476f9be35eb7cc75c2"),
    30: (93, "208308aafb6d260e9746e5c469546e5f39f573fc11358e613f3c712ce2a20df5"),
    31: (25, "00f637eb55b9fe70a35c46e4d737c1bfaf9c5fa3fc093cd788cb25b68e978563"),
    32: (49, "138b8113f5af287131b7d68206aaff5eaa986e2cfa9665f117d2990b065df6da"),
    33: (9, "914cb11077be1b667321c6909dd4e3e56d16daf2792a93cdbd0c65ab631eeb75"),
    34: (35, "dffaa9a5978343206cd3c18bd37a011ec01c9cd94f742adee88b018fa62382d1"),
    35: (94, "39245b76ed9c45338652d6477db2dff3fa30190d91afe2e8eac4611da1785489"),
    36: (24, "5bb21b0268a0e875e93f65e8acf97b0859fb61e4ae21264c6b51377f75ef85d2"),
    37: (121, "535a3b139dd3fe1fb3030792612b966c08d959af55252f79b2c4a0026eb6bb83"),
}


def pcm_bytes(samples: tuple[int, ...]) -> bytes:
    assert len(samples) == 160
    return struct.pack("<160h", *samples)


@pytest.mark.parametrize("section", (20, 23))
def test_first_three_frames_match_isolated_candidate_pcm(section: int) -> None:
    decoder = CandidateMode5Decoder()
    for frame_hex, expected_sha256 in SAMPLES[section]:
        actual = pcm_bytes(decoder.decode_frame(bytes.fromhex(frame_hex)))
        assert hashlib.sha256(actual).hexdigest() == expected_sha256


def test_invalid_frame_does_not_advance_decoder_state() -> None:
    first, second = (bytes.fromhex(value[0]) for value in SAMPLES[20][:2])
    decoder = CandidateMode5Decoder()
    decoder.decode_frame(first)
    with pytest.raises(ValueError):
        decoder.decode_frame(b"\x00")
    expected = CandidateMode5Decoder()
    expected.decode_frame(first)
    assert decoder.decode_frame(second) == expected.decode_frame(second)


@pytest.fixture(scope="module")
def installed_game() -> bytes:
    if not GAME.is_file():
        pytest.skip("local Tianjiang Fengyun V1.3 NPE is not installed")
    game = GAME.read_bytes()
    assert hashlib.sha256(game).hexdigest() == GAME_SHA256
    return game


def full_section_pcm_sha256(game: bytes, section: int, expected_frames: int) -> str:
    sections = _parse_sections(game)
    offset, size = sections[section]
    payload = game[offset:offset + size]
    assert payload[:2] == b"\x20\x0d"
    frames = int.from_bytes(payload[2:4], "big")
    assert frames == expected_frames
    assert size == (4 + frames * 21 + 1) & ~1
    encoded = bytearray(payload[4:4 + frames * 21])
    assert len(encoded) == frames * 21
    # Normalize the entire section before splitting odd-sized 21-byte frames.
    for index in range(0, len(encoded) - 1, 2):
        encoded[index], encoded[index + 1] = encoded[index + 1], encoded[index]
    decoder = CandidateMode5Decoder()
    digest = hashlib.sha256()
    for index in range(frames):
        digest.update(pcm_bytes(decoder.decode_frame(
            bytes(encoded[index * 21:(index + 1) * 21])
        )))
    return digest.hexdigest()


@pytest.mark.parametrize("section", tuple(FULL_SECTIONS))
def test_local_full_game_pcm_regression(
    section: int, installed_game: bytes
) -> None:
    frames, expected_sha256 = FULL_SECTIONS[section]
    assert full_section_pcm_sha256(installed_game, section, frames) == expected_sha256


def test_arno_negative_pcm_boundary_regression() -> None:
    if not ARNO_GAME.is_file():
        pytest.skip("local Arno Genesis NPE is not installed")
    game = ARNO_GAME.read_bytes()
    assert hashlib.sha256(game).hexdigest() == ARNO_GAME_SHA256
    assert full_section_pcm_sha256(game, 22, 948) == ARNO_SECTION_22_PCM_SHA256
