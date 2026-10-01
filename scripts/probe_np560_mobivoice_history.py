#!/usr/bin/env python3
"""Check the candidate's excitation history against a zero-seeded model.

Only the reviewed DLL is interpreted in Unicorn.  Its mixed subframe output
is used to advance the model; this does not independently decode PCM or
establish what the missing NP560 mask ROM does.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from unicorn import UC_HOOK_CODE
from unicorn.x86_const import (
    UC_X86_REG_EAX, UC_X86_REG_EBP, UC_X86_REG_ESP,
)

from analyse_np560_npe import _parse_sections
from np560_mobivoice_codebooks import candidate_codebook_vector
from np560_mobivoice_fields import parse_mode5_frame
from np560_mobivoice_history import CandidateExcitationHistory
from np560_mobivoice_lsf import normalize_candidate_words, signed16
from np560_mobivoice_lsf_predict import CandidateLsfPredictor
from np560_mobivoice_lsf_subframes import CandidateLsfSubframes
from np560_mobivoice_lpc import candidate_lpc_from_lsf
from np560_mobivoice_pitch import pitch_calls_from_candidate_frame
from np560_mobivoice_tables import LSF_COSINE_TABLE
from probe_np560_mobivoice_sp_decoder import (
    BASE, IsolatedDecoder, candidate_bytes,
)


ADAPTIVE_START = BASE + 0x198C
MIX_END = BASE + 0x1C04
PITCH_STEP = BASE + 0x1680
CODEBOOK_READY = BASE + 0x185B
LSF_PREDICTED_READY = BASE + 0x18B5
LSF_NORMALIZED_RETURN = BASE + 0x127E
LSF_INTERPOLATED_READY = BASE + 0x1940
LPC_STEP = BASE + 0x1320
LPC_STEP_RETURN = BASE + 0x1963


def check_history(decoder: IsolatedDecoder, context: int,
                  frames: tuple[bytes, ...]) -> dict:
    history = CandidateExcitationHistory()
    lsf_predictor = CandidateLsfPredictor()
    lsf_subframes = CandidateLsfSubframes()
    state = {"frame": 0, "subframe": 0, "buffer_pointer": None,
             "checked": 0, "fractional": 0, "max_needed": 0,
             "pitch_calls": 0, "pitch_checked": 0, "frame_pitches": None,
             "frame_fields": None, "lsf_pending": None, "lsf_checked": 0,
             "normalized_pending": None, "normalized_checked": 0,
             "lsf_subframe_checked": 0, "lsf_source": None,
             "lpc_pending": None, "lpc_checked": 0}

    def on_codebook(uc, _address: int, _size: int, _user) -> None:
        if state["lsf_pending"] is not None:
            raise RuntimeError("nested candidate LSF codebook stage")
        vector = candidate_codebook_vector(state["frame_fields"])
        esp = uc.reg_read(UC_X86_REG_ESP)
        if struct.unpack("<10h", uc.mem_read(esp + 0x40, 20)) != vector:
            raise RuntimeError(f"candidate frame {state['frame']} codebook differs")
        ebp = uc.reg_read(UC_X86_REG_EBP)
        prior = struct.unpack("<10h", uc.mem_read(ebp + 0x414, 20))
        if prior != lsf_predictor.state:
            raise RuntimeError(f"candidate frame {state['frame']} LSF state differs")
        predicted = lsf_predictor.step(vector)
        state["lsf_pending"] = (ebp, predicted, lsf_predictor.state)

    def on_lsf_predicted(uc, _address: int, _size: int, _user) -> None:
        pending = state["lsf_pending"]
        if pending is None:
            raise RuntimeError("candidate LSF prediction lacks codebook stage")
        ebp, expected_lsf, expected_state = pending
        actual_lsf = struct.unpack("<10h", uc.mem_read(ebp + 0x3EC, 20))
        actual_state = struct.unpack("<10h", uc.mem_read(ebp + 0x414, 20))
        if (actual_lsf, actual_state) != (expected_lsf, expected_state):
            raise RuntimeError(f"candidate frame {state['frame']} LSF prediction differs")
        state["lsf_pending"] = None
        state["lsf_checked"] += 1
        state["normalized_pending"] = normalize_candidate_words(expected_lsf)

    def on_lsf_normalized(uc, _address: int, _size: int, _user) -> None:
        pending = state["normalized_pending"]
        if pending is None:
            raise RuntimeError("candidate LSF normalization lacks predicted input")
        expected, expected_status = pending
        actual = struct.unpack("<10h", uc.mem_read(context + 0x424, 20))
        status = signed16(uc.reg_read(UC_X86_REG_EAX))
        if (actual, status) != (expected, expected_status):
            raise RuntimeError(f"candidate frame {state['frame']} normalized LSF differs")
        if struct.unpack("<10h", uc.mem_read(context + 0x438, 20)) != (
            lsf_subframes.previous
        ):
            raise RuntimeError(f"candidate frame {state['frame']} previous LSF differs")
        lsf_subframes.begin_frame(expected)
        state["normalized_pending"] = None
        state["normalized_checked"] += 1

    def on_lsf_interpolated(uc, _address: int, _size: int, _user) -> None:
        esp = uc.reg_read(UC_X86_REG_ESP)
        subframe = struct.unpack("<I", uc.mem_read(esp + 0x10, 4))[0]
        expected = lsf_subframes.subframe(subframe)
        actual = struct.unpack("<10h", uc.mem_read(esp + 0x40, 20))
        if actual != expected:
            raise RuntimeError(
                f"candidate frame {state['frame']} subframe {subframe} LSF differs"
            )
        state["lsf_subframe_checked"] += 1
        state["lsf_source"] = expected

    def on_lpc(uc, _address: int, _size: int, _user) -> None:
        if state["lpc_pending"] is not None or state["lsf_source"] is None:
            raise RuntimeError("candidate LPC conversion has invalid stage order")
        esp = uc.reg_read(UC_X86_REG_ESP)
        _, source, output, table_pointer = struct.unpack(
            "<4I", uc.mem_read(esp, 16)
        )
        lsf = struct.unpack("<10h", uc.mem_read(source, 20))
        if lsf != state["lsf_source"]:
            raise RuntimeError(f"candidate frame {state['frame']} LPC input differs")
        if struct.unpack("<65h", uc.mem_read(table_pointer, 130)) != LSF_COSINE_TABLE:
            raise RuntimeError("candidate LPC table differs from owned data")
        state["lpc_pending"] = (output, candidate_lpc_from_lsf(lsf))

    def on_lpc_return(uc, _address: int, _size: int, _user) -> None:
        pending = state["lpc_pending"]
        if pending is None:
            raise RuntimeError("candidate LPC return lacks entry")
        output, expected = pending
        if struct.unpack("<11h", uc.mem_read(output, 22)) != expected:
            raise RuntimeError(f"candidate frame {state['frame']} LPC coefficients differ")
        state["lpc_pending"] = None
        state["lsf_source"] = None
        state["lpc_checked"] += 1

    def on_pitch(uc, _address: int, _size: int, _user) -> None:
        index = state["pitch_calls"]
        if index >= 2:
            raise RuntimeError("candidate frame has excess pitch calls")
        esp = uc.reg_read(UC_X86_REG_ESP)
        _, _, _, previous, code = struct.unpack("<5I", uc.mem_read(esp, 20))
        previous &= 0xFFFF
        code &= 0xFFFF
        from_frame = state["frame_pitches"][index]
        if (previous, code) != (from_frame.previous_delay, from_frame.code):
            raise RuntimeError(
                f"candidate pitch call differs from frame={state['frame']} "
                f"subframe={index} compressed fields"
            )
        state["pitch_calls"] += 1
        state["pitch_checked"] += 1

    def on_start(uc, _address: int, _size: int, _user) -> None:
        esp = uc.reg_read(UC_X86_REG_ESP)
        buffer_pointer = struct.unpack("<I", uc.mem_read(esp + 0x18, 4))[0]
        delay = struct.unpack("<h", uc.mem_read(esp + 0x20, 2))[0]
        fraction = uc.reg_read(UC_X86_REG_EAX) & 0xFFFF
        if fraction & 0x8000:
            fraction -= 0x10000
        if not 1 <= delay <= 160 or fraction not in (-1, 0, 1):
            raise ValueError("unexpected candidate adaptive delay/fraction")
        from_frame = state["frame_pitches"][state["subframe"]]
        if (delay, fraction) != (from_frame.delay, from_frame.fraction):
            raise RuntimeError(
                f"candidate adaptive pitch differs from frame={state['frame']} "
                f"subframe={state['subframe']} compressed fields"
            )
        needed = delay + (14 if fraction else 0)
        actual = struct.unpack(
            f"<{needed}h",
            uc.mem_read(buffer_pointer - needed * 2, needed * 2),
        )
        expected = history.tail(needed)
        if actual != expected:
            first = next(index for index, pair in enumerate(zip(actual, expected))
                         if pair[0] != pair[1])
            raise RuntimeError(
                f"candidate excitation history differs at frame={state['frame']} "
                f"subframe={state['subframe']} sample={first}"
            )
        state["buffer_pointer"] = buffer_pointer
        state["checked"] += 1
        state["fractional"] += bool(fraction)
        state["max_needed"] = max(state["max_needed"], needed)

    def on_mix_end(uc, _address: int, _size: int, _user) -> None:
        pointer = state["buffer_pointer"]
        if pointer is None:
            raise RuntimeError("candidate mix completed before adaptive start")
        samples = struct.unpack("<80h", uc.mem_read(pointer, 160))
        history.append_subframe(samples)
        state["buffer_pointer"] = None
        state["subframe"] += 1

    decoder.uc.hook_add(UC_HOOK_CODE, on_codebook,
                        begin=CODEBOOK_READY, end=CODEBOOK_READY)
    decoder.uc.hook_add(UC_HOOK_CODE, on_lsf_predicted,
                        begin=LSF_PREDICTED_READY, end=LSF_PREDICTED_READY)
    decoder.uc.hook_add(UC_HOOK_CODE, on_lsf_normalized,
                        begin=LSF_NORMALIZED_RETURN, end=LSF_NORMALIZED_RETURN)
    decoder.uc.hook_add(UC_HOOK_CODE, on_lsf_interpolated,
                        begin=LSF_INTERPOLATED_READY, end=LSF_INTERPOLATED_READY)
    decoder.uc.hook_add(UC_HOOK_CODE, on_lpc, begin=LPC_STEP, end=LPC_STEP)
    decoder.uc.hook_add(UC_HOOK_CODE, on_lpc_return,
                        begin=LPC_STEP_RETURN, end=LPC_STEP_RETURN)
    decoder.uc.hook_add(UC_HOOK_CODE, on_pitch, begin=PITCH_STEP, end=PITCH_STEP)
    decoder.uc.hook_add(
        UC_HOOK_CODE, on_start, begin=ADAPTIVE_START, end=ADAPTIVE_START,
    )
    decoder.uc.hook_add(UC_HOOK_CODE, on_mix_end, begin=MIX_END, end=MIX_END)
    for index, frame in enumerate(frames):
        state["frame"] = index
        state["frame_fields"] = parse_mode5_frame(frame)
        state["frame_pitches"] = pitch_calls_from_candidate_frame(state["frame_fields"])
        state["pitch_calls"] = 0
        lsf_count_before = state["lsf_checked"]
        normalized_before = state["normalized_checked"]
        interpolated_before = state["lsf_subframe_checked"]
        lpc_before = state["lpc_checked"]
        decoder.decode(frame, context)
        if (state["pitch_calls"] != 2 or state["subframe"] != 2 or
                state["buffer_pointer"] is not None or
                state["lsf_pending"] is not None or
                state["normalized_pending"] is not None or
                state["lpc_pending"] is not None or
                state["lsf_source"] is not None or
                state["lsf_checked"] != lsf_count_before + 1 or
                state["normalized_checked"] != normalized_before + 1 or
                state["lsf_subframe_checked"] != interpolated_before + 2 or
                state["lpc_checked"] != lpc_before + 2):
            raise RuntimeError(f"candidate frame {index} lacks required stages")
        history.finish_frame()
        lsf_subframes.finish_frame()
        if struct.unpack("<10h", decoder.uc.mem_read(context + 0x438, 20)) != (
            lsf_subframes.previous
        ):
            raise RuntimeError(f"candidate frame {index} saved previous LSF differs")
        state["subframe"] = 0
    return {
        "frames": len(frames),
        "checked_subframes": state["checked"],
        "fractional_subframes": state["fractional"],
        "pitch_calls_from_fields_checked": state["pitch_checked"],
        "lsf_codebook_and_prediction_frames_checked": state["lsf_checked"],
        "lsf_normalization_frames_checked": state["normalized_checked"],
        "lsf_interpolated_subframes_checked": state["lsf_subframe_checked"],
        "lpc_coefficient_subframes_checked": state["lpc_checked"],
        "maximum_history_samples": state["max_needed"],
        "matches_owned_history_model": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dll", type=Path, required=True)
    parser.add_argument("--npe", type=Path, required=True)
    parser.add_argument("--section", type=int, required=True)
    parser.add_argument("--frame-count", type=int, default=100)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.frame_count < 1 or args.output.exists():
        parser.error("frame count must be positive and output must be new")
    npe = args.npe.read_bytes()
    offset, size = _parse_sections(npe)[args.section]
    section = npe[offset:offset + size]
    if section[:2] != b"\x20\x0d":
        parser.error("section is not format 13")
    declared = int.from_bytes(section[2:4], "big")
    if args.frame_count > declared or size != ((4 + declared * 21 + 1) & ~1):
        parser.error("section length or frame count does not match header")
    # The NPE's swap16 transform spans frame boundaries (21 bytes is odd).
    # Transform the entire section before taking a prefix of frames.
    compressed = candidate_bytes(
        section[4:4 + declared * 21], "swap16", 0,
    )[:args.frame_count * 21]
    frames = tuple(compressed[index:index + 21]
                   for index in range(0, len(compressed), 21))
    dll = args.dll.read_bytes()
    decoder = IsolatedDecoder(dll)
    context, frame_bits = decoder.init(5)
    if frame_bits != 168:
        raise RuntimeError("candidate mode 5 frame bits changed")
    result = check_history(decoder, context, frames)
    result.update({
        "schema": "np560-mobivoice-history-v1",
        "candidate_not_mask_rom_truth": True,
        "dll_sha256": hashlib.sha256(dll).hexdigest(),
        "npe_sha256": hashlib.sha256(npe).hexdigest(),
        "section": args.section,
        "section_sha256": hashlib.sha256(section).hexdigest(),
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
