#!/usr/bin/env python3
"""Trace candidate decoder bit reads against an independent MSB-first reader.

The reviewed, user-supplied DLL is interpreted in Unicorn, never executed
natively or copied into the report. This is an algorithm-boundary probe, not
proof that the candidate PCM matches the missing NP560 mask ROM.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from unicorn import UC_HOOK_CODE
from unicorn.x86_const import (
    UC_X86_REG_EAX, UC_X86_REG_EBP, UC_X86_REG_EBX, UC_X86_REG_EDI,
    UC_X86_REG_ESP,
)

from analyse_np560_npe import _parse_sections
from np560_mobivoice_adaptive import generate_candidate_adaptive
from np560_mobivoice_codebooks import (
    CODEBOOK_WIDTHS, candidate_codebook_vector,
)
from np560_mobivoice_codebook_data import CODEBOOKS
from np560_mobivoice_fields import msb_bits, parse_mode5_frame
from np560_mobivoice_fir import candidate_dot_sample, signed32
from np560_mobivoice_fixed import (
    CandidatePulseGroup, accumulate_candidate_pulses,
    candidate_amplitude_indices, candidate_sign_bits, groups_from_candidate_frame,
)
from np560_mobivoice_history import CandidateExcitationHistory
from np560_mobivoice_interpolate import interpolate_candidate_table
from np560_mobivoice_lsf import normalize_candidate_words, signed16
from np560_mobivoice_lsf_predict import CandidateLsfPredictor
from np560_mobivoice_lsf_subframes import CandidateLsfSubframes
from np560_mobivoice_lpc import candidate_lpc_from_lsf
from np560_mobivoice_mix import mix_candidate_excitation
from np560_mobivoice_pitch import (
    decode_candidate_pitch, pitch_calls_from_candidate_frame,
)
from np560_mobivoice_synthesis import synthesize_candidate_block
from np560_mobivoice_tables import (
    INTERPOLATION_TAPS, LSF_BIAS, LSF_COSINE_TABLE, LSF_PREDICTOR_GAIN, PITCH_GAINS,
    PULSE_AMPLITUDES, PULSE_POSITIONS, interpolation_phase_taps,
)
from probe_np560_mobivoice_sp_decoder import (
    BASE, IsolatedDecoder, candidate_bytes,
)


BIT_READER = BASE + 0x1ED0
BIT_READER_RETURNS = frozenset((BASE + 0x1F32, BASE + 0x1FBA))
LSF_STEP = BASE + 0x1220
LSF_STEP_RETURN = BASE + 0x127E
INTERPOLATE_STEP = BASE + 0x1280
INTERPOLATE_STEP_RETURN = BASE + 0x1318
DOT_STEP = BASE + 0x1610
DOT_STEP_RETURN = BASE + 0x167D
SYNTHESIS_STEP = BASE + 0x1CA0
SYNTHESIS_STEP_RETURN = BASE + 0x1D30
PITCH_STEP = BASE + 0x1680
PITCH_STEP_RETURNS = frozenset((
    BASE + 0x16CE, BASE + 0x16D5, BASE + 0x16EB,
    BASE + 0x1739, BASE + 0x1788, BASE + 0x1790,
))
ADAPTIVE_START = BASE + 0x198C
ADAPTIVE_END = BASE + 0x1A00
FIXED_START = BASE + 0x1A55
FIXED_GROUP_READY = BASE + 0x1B5F
FIXED_GROUP_END = BASE + 0x1B90
FIXED_END = BASE + 0x1BAE
MIX_END = BASE + 0x1C04
CODEBOOK_READY = BASE + 0x185B
LSF_PREDICTED_READY = BASE + 0x18B5
LSF_INTERPOLATED_READY = BASE + 0x1940
LPC_STEP = BASE + 0x1320
LPC_STEP_RETURN = BASE + 0x1963


def verify_candidate_mode5_tables(uc, config_pointer: int) -> None:
    """Check the reviewed candidate's static tables against owned values."""
    for pointer_offset, values in (
        (0x04, INTERPOLATION_TAPS),
        (0x10, PULSE_POSITIONS),
        (0x2C, PITCH_GAINS),
        (0x30, PULSE_AMPLITUDES),
        (0x24, LSF_BIAS),
        (0x28, LSF_PREDICTOR_GAIN),
        (0x08, LSF_COSINE_TABLE),
    ):
        pointer = struct.unpack(
            "<I", uc.mem_read(config_pointer + pointer_offset, 4)
        )[0]
        candidate = struct.unpack(
            f"<{len(values)}h", uc.mem_read(pointer, len(values) * 2)
        )
        if candidate != values:
            raise RuntimeError(
                f"candidate mode-5 table at config +{pointer_offset:#x} differs"
            )
    interpolation_base = struct.unpack(
        "<I", uc.mem_read(config_pointer + 0x04, 4)
    )[0]
    interpolation_center = struct.unpack(
        "<I", uc.mem_read(config_pointer + 0x0C, 4)
    )[0]
    if interpolation_center != interpolation_base + 47 * 2:
        raise RuntimeError("candidate interpolation table center differs")


def trace_frame(decoder: IsolatedDecoder, context: int, frame: bytes,
                history: CandidateExcitationHistory | None = None,
                lsf_predictor: CandidateLsfPredictor | None = None,
                lsf_subframes: CandidateLsfSubframes | None = None) -> dict:
    parsed_fields = parse_mode5_frame(frame)
    frame_pitches = pitch_calls_from_candidate_frame(parsed_fields)
    fields: list[dict] = []
    pending: dict | None = None
    lsf_stages: list[dict] = []
    pending_lsf: dict | None = None
    interpolation_stages: list[dict] = []
    pending_interpolation: dict | None = None
    dot_results: list[int] = []
    pending_dot: dict | None = None
    synthesis_stages: list[dict] = []
    pending_synthesis: dict | None = None
    pitch_stages: list[dict] = []
    pending_pitch: dict | None = None
    adaptive_stages: list[dict] = []
    pending_adaptive: dict | None = None
    fixed_stages: list[dict] = []
    pending_fixed: dict | None = None
    mix_stages: list[dict] = []
    pending_mix: dict | None = None
    codebook_stages: list[dict] = []
    lsf_predictor_stages: list[dict] = []
    pending_lsf_prediction: dict | None = None
    lsf_subframe_stages: list[dict] = []
    active_spectra: CandidateLsfSubframes | None = None
    lpc_stages: list[dict] = []
    pending_lpc: dict | None = None
    owned_intermediate: tuple[int, ...] | None = None
    static_tables_verified = False

    def observe(uc, address: int, _size: int, _user) -> None:
        nonlocal pending, pending_lsf, pending_interpolation, pending_dot
        nonlocal pending_synthesis, pending_pitch, pending_adaptive, pending_fixed
        nonlocal pending_mix, static_tables_verified, pending_lsf_prediction
        nonlocal active_spectra, pending_lpc, owned_intermediate
        if address == CODEBOOK_READY:
            if pending_lsf_prediction is not None:
                raise RuntimeError("nested candidate LSF prediction")
            config_pointer = uc.reg_read(UC_X86_REG_EDI)
            lengths_pointer = struct.unpack(
                "<I", uc.mem_read(config_pointer + 0x20, 4)
            )[0]
            widths = struct.unpack("<3h", uc.mem_read(lengths_pointer, 6))
            if widths != CODEBOOK_WIDTHS:
                raise RuntimeError("candidate LSF codebook widths differ")
            pointers = struct.unpack(
                "<3I", uc.mem_read(config_pointer + 0x14, 12)
            )
            books = tuple(
                struct.unpack(
                    f"<{256 * width}h",
                    uc.mem_read(pointer, 256 * width * 2),
                )
                for pointer, width in zip(pointers, widths)
            )
            if books != CODEBOOKS:
                raise RuntimeError("candidate LSF codebooks differ from owned data")
            expected = candidate_codebook_vector(parsed_fields)
            esp = uc.reg_read(UC_X86_REG_ESP)
            actual = struct.unpack("<10h", uc.mem_read(esp + 0x40, 20))
            if actual != expected:
                raise RuntimeError("candidate LSF codebook vector differs from fields")
            ebp = uc.reg_read(UC_X86_REG_EBP)
            prior = struct.unpack("<10h", uc.mem_read(ebp + 0x414, 20))
            predictor = lsf_predictor or CandidateLsfPredictor(prior)
            if predictor.state != prior:
                raise RuntimeError("candidate LSF history differs from owned state")
            expected_lsf = predictor.step(expected)
            pending_lsf_prediction = {
                "ebp": ebp,
                "expected_lsf": expected_lsf,
                "expected_state": predictor.state,
            }
            codebook_stages.append({
                "indices": [field.value for field in parsed_fields[:3]],
                "vector": list(actual),
                "matches_compressed_fields": True,
            })
        elif address == LSF_PREDICTED_READY and pending_lsf_prediction is not None:
            ebp = pending_lsf_prediction["ebp"]
            actual_lsf = struct.unpack("<10h", uc.mem_read(ebp + 0x3EC, 20))
            actual_state = struct.unpack("<10h", uc.mem_read(ebp + 0x414, 20))
            if (actual_lsf != pending_lsf_prediction["expected_lsf"] or
                    actual_state != pending_lsf_prediction["expected_state"]):
                raise RuntimeError("candidate LSF predictor differs from owned model")
            lsf_predictor_stages.append({
                "pre_normalization": list(actual_lsf),
                "state": list(actual_state),
                "matches_independent_model": True,
            })
            pending_lsf_prediction = None
        elif address == LSF_STEP:
            if pending_lsf is not None:
                raise RuntimeError("nested candidate preparation step")
            ret, pointer = struct.unpack(
                "<2I", uc.mem_read(uc.reg_read(UC_X86_REG_ESP), 8)
            )
            pending_lsf = {
                "return": ret,
                "pointer": pointer,
                "input": struct.unpack("<10h", uc.mem_read(pointer, 20)),
            }
        elif address == LSF_STEP_RETURN and pending_lsf is not None:
            actual = struct.unpack(
                "<10h", uc.mem_read(pending_lsf["pointer"], 20)
            )
            status = signed16(uc.reg_read(UC_X86_REG_EAX))
            expected, expected_status = normalize_candidate_words(
                pending_lsf["input"]
            )
            if actual != expected or status != expected_status:
                raise RuntimeError("candidate preparation differs from owned model")
            lsf_stages.append({
                "pointer_from_context": pending_lsf["pointer"] - context,
                "input": list(pending_lsf["input"]),
                "output": list(actual),
                "status": status,
                "matches_independent_model": True,
            })
            if active_spectra is not None:
                raise RuntimeError("candidate has nested normalized LSF frames")
            active_spectra = lsf_subframes or CandidateLsfSubframes()
            candidate_previous = struct.unpack(
                "<10h", uc.mem_read(context + 0x438, 20)
            )
            if lsf_subframes is None:
                active_spectra.previous = candidate_previous
            elif active_spectra.previous != candidate_previous:
                raise RuntimeError(
                    "candidate prior LSF differs from owned state: "
                    f"candidate={candidate_previous} owned={active_spectra.previous}"
                )
            active_spectra.begin_frame(expected)
            pending_lsf = None
        elif address == LSF_INTERPOLATED_READY:
            if active_spectra is None:
                raise RuntimeError("candidate LSF subframe lacks normalized frame")
            esp = uc.reg_read(UC_X86_REG_ESP)
            subframe = struct.unpack("<I", uc.mem_read(esp + 0x10, 4))[0]
            actual = struct.unpack("<10h", uc.mem_read(esp + 0x40, 20))
            expected = active_spectra.subframe(subframe)
            if actual != expected:
                raise RuntimeError("candidate LSF subframe differs from owned interpolation")
            lsf_subframe_stages.append({
                "subframe": subframe,
                "vector": list(actual),
                "matches_independent_model": True,
            })
        elif address == LPC_STEP:
            if pending_lpc is not None:
                raise RuntimeError("nested candidate LPC conversion")
            ret, source, output, table_pointer = struct.unpack(
                "<4I", uc.mem_read(uc.reg_read(UC_X86_REG_ESP), 16)
            )
            lsf = struct.unpack("<10h", uc.mem_read(source, 20))
            if not lsf_subframe_stages or lsf != tuple(
                lsf_subframe_stages[-1]["vector"]
            ):
                raise RuntimeError("candidate LPC input differs from owned LSF subframe")
            table = struct.unpack("<65h", uc.mem_read(table_pointer, 130))
            if table != LSF_COSINE_TABLE:
                raise RuntimeError("candidate LPC cosine table differs from owned data")
            pending_lpc = {
                "return": ret,
                "output": output,
                "expected": candidate_lpc_from_lsf(lsf),
            }
        elif address == LPC_STEP_RETURN and pending_lpc is not None:
            actual = struct.unpack(
                "<11h", uc.mem_read(pending_lpc["output"], 22)
            )
            if actual != pending_lpc["expected"]:
                raise RuntimeError("candidate LPC coefficients differ from owned model")
            lpc_stages.append({
                "coefficients": list(actual),
                "matches_independent_model": True,
            })
            pending_lpc = None
        elif address == INTERPOLATE_STEP:
            if pending_interpolation is not None:
                raise RuntimeError("nested candidate interpolation")
            ret, source, count, fractional_bits, table_pointer, output = struct.unpack(
                "<6I", uc.mem_read(uc.reg_read(UC_X86_REG_ESP), 24)
            )
            if count > 64 or not 1 <= fractional_bits <= 15:
                raise ValueError("unexpected candidate interpolation geometry")
            positions = struct.unpack(
                f"<{count}h", uc.mem_read(source, count * 2)
            )
            maximum_index = max(position >> fractional_bits for position in positions)
            table = struct.unpack(
                f"<{maximum_index + 2}h",
                uc.mem_read(table_pointer, (maximum_index + 2) * 2),
            )
            pending_interpolation = {
                "return": ret, "output": output, "count": count,
                "fractional_bits": fractional_bits,
                "positions": positions,
                "expected": interpolate_candidate_table(
                    positions, table, fractional_bits,
                ),
            }
        elif address == INTERPOLATE_STEP_RETURN and pending_interpolation is not None:
            actual = struct.unpack(
                f"<{pending_interpolation['count']}h",
                uc.mem_read(pending_interpolation["output"],
                            pending_interpolation["count"] * 2),
            )
            if actual != pending_interpolation["expected"]:
                raise RuntimeError("candidate interpolation differs from owned model")
            interpolation_stages.append({
                "count": pending_interpolation["count"],
                "fractional_bits": pending_interpolation["fractional_bits"],
                "positions": list(pending_interpolation["positions"]),
                "output": list(actual),
                "matches_independent_model": True,
            })
            pending_interpolation = None
        elif address == DOT_STEP:
            if pending_dot is not None:
                raise RuntimeError("nested candidate dot product")
            ret, history_pointer, lag_word, coefficient_pointer, radius_word = struct.unpack(
                "<5I", uc.mem_read(uc.reg_read(UC_X86_REG_ESP), 20)
            )
            # The x86 helper sign-extends only the low 16 bits of this arg.
            lag = signed16(lag_word)
            radius = signed16(radius_word)
            if radius < 0 or radius > 32:
                raise ValueError("unexpected candidate dot-product radius")
            dot_history = tuple(
                struct.unpack("<h", uc.mem_read(history_pointer + step * 2, 2))[0]
                for step in range(-radius, radius + 1)
            )
            taps = tuple(
                struct.unpack("<h", uc.mem_read(
                    coefficient_pointer + (step * 3 - lag) * 2, 2,
                ))[0]
                for step in range(-radius, radius + 1)
            )
            pending_dot = {
                "return": ret,
                "expected": candidate_dot_sample(dot_history, taps),
            }
        elif address == DOT_STEP_RETURN and pending_dot is not None:
            actual = signed32(uc.reg_read(UC_X86_REG_EAX))
            if actual != pending_dot["expected"]:
                raise RuntimeError("candidate dot product differs from owned model")
            dot_results.append(actual)
            pending_dot = None
        elif address == SYNTHESIS_STEP:
            if pending_synthesis is not None:
                raise RuntimeError("nested candidate synthesis")
            ret, source, count, coefficient_pointer, output = struct.unpack(
                "<5I", uc.mem_read(uc.reg_read(UC_X86_REG_ESP), 20)
            )
            if count > 160 or count == 0:
                raise ValueError("unexpected candidate synthesis block size")
            intermediate = struct.unpack(
                f"<{count}h", uc.mem_read(source, count * 2)
            )
            if owned_intermediate is not None and intermediate != owned_intermediate:
                raise RuntimeError("candidate synthesis input differs from owned excitation")
            previous = struct.unpack(
                "<10h", uc.mem_read(output - 20, 20)
            )
            taps = struct.unpack(
                "<10h", uc.mem_read(coefficient_pointer + 2, 20)
            )
            if not lpc_stages or taps != tuple(lpc_stages[-1]["coefficients"][1:]):
                raise RuntimeError("candidate synthesis taps differ from owned LPC")
            pending_synthesis = {
                "return": ret, "output": output, "count": count,
                "expected": synthesize_candidate_block(
                    intermediate, previous, taps,
                ),
            }
        elif address == SYNTHESIS_STEP_RETURN and pending_synthesis is not None:
            actual = struct.unpack(
                f"<{pending_synthesis['count']}h",
                uc.mem_read(pending_synthesis["output"],
                            pending_synthesis["count"] * 2),
            )
            if actual != pending_synthesis["expected"]:
                raise RuntimeError("candidate synthesis differs from owned model")
            synthesis_stages.append({
                "count": len(actual),
                "first_eight": list(actual[:8]),
                "pcm_sha256": hashlib.sha256(struct.pack(
                    f"<{len(actual)}h", *actual,
                )).hexdigest(),
                "matches_independent_model": True,
                "output": actual,
            })
            pending_synthesis = None
        elif address == PITCH_STEP:
            if pending_pitch is not None:
                raise RuntimeError("nested candidate pitch mapping")
            ret, delay_pointer, fraction_pointer, previous_word, code_word = struct.unpack(
                "<5I", uc.mem_read(uc.reg_read(UC_X86_REG_ESP), 20)
            )
            previous = signed16(previous_word)
            code = signed16(code_word)
            if len(pitch_stages) >= len(frame_pitches):
                raise RuntimeError("candidate has excess pitch calls")
            from_frame = frame_pitches[len(pitch_stages)]
            if (previous, code) != (from_frame.previous_delay, from_frame.code):
                raise RuntimeError("candidate pitch call differs from compressed fields")
            pending_pitch = {
                "return": ret,
                "delay_pointer": delay_pointer,
                "fraction_pointer": fraction_pointer,
                "previous_delay": previous,
                "code": code,
                "expected": decode_candidate_pitch(previous, code),
                "from_frame": from_frame,
            }
        elif address in PITCH_STEP_RETURNS and pending_pitch is not None:
            actual = (
                struct.unpack("<h", uc.mem_read(pending_pitch["delay_pointer"], 2))[0],
                struct.unpack("<h", uc.mem_read(pending_pitch["fraction_pointer"], 2))[0],
            )
            if actual != pending_pitch["expected"]:
                raise RuntimeError("candidate pitch differs from owned model")
            from_frame = pending_pitch["from_frame"]
            if actual != (from_frame.delay, from_frame.fraction):
                raise RuntimeError("candidate pitch result differs from compressed fields")
            pitch_stages.append({
                "previous_delay": pending_pitch["previous_delay"],
                "code": pending_pitch["code"],
                "delay": actual[0],
                "fraction": actual[1],
                "matches_independent_model": True,
                "matches_compressed_fields": True,
            })
            pending_pitch = None
        elif address == ADAPTIVE_START:
            if pending_adaptive is not None:
                raise RuntimeError("nested candidate adaptive subframe")
            esp = uc.reg_read(UC_X86_REG_ESP)
            fraction = signed16(uc.reg_read(UC_X86_REG_EAX))
            buffer_pointer = struct.unpack("<I", uc.mem_read(esp + 0x18, 4))[0]
            delay = struct.unpack("<h", uc.mem_read(esp + 0x20, 2))[0]
            if len(adaptive_stages) >= len(frame_pitches):
                raise RuntimeError("candidate has excess adaptive subframes")
            expected_pitch = frame_pitches[len(adaptive_stages)]
            if (delay, fraction) != (expected_pitch.delay,
                                     expected_pitch.fraction):
                raise RuntimeError("candidate adaptive pitch differs from fields")
            config_pointer = struct.unpack(
                "<I", uc.mem_read(esp + 0xE4, 4)
            )[0]
            if not static_tables_verified:
                verify_candidate_mode5_tables(uc, config_pointer)
                static_tables_verified = True
            needed = delay + 14 if fraction else delay
            if not 1 <= delay <= 255 or fraction not in (-1, 0, 1):
                raise ValueError("unexpected candidate adaptive geometry")
            candidate_history = struct.unpack(
                f"<{needed}h",
                uc.mem_read(buffer_pointer - needed * 2, needed * 2),
            )
            history_input = candidate_history
            if history is not None:
                history_input = history.tail(needed)
                if candidate_history != history_input:
                    raise RuntimeError(
                        "candidate adaptive history differs from owned state"
                    )
            taps = interpolation_phase_taps(fraction) if fraction else None
            pending_adaptive = {
                "buffer_pointer": buffer_pointer,
                "delay": delay,
                "fraction": fraction,
                "expected": generate_candidate_adaptive(
                    history_input, delay, fraction, taps,
                ),
            }
        elif address == ADAPTIVE_END and pending_adaptive is not None:
            actual = struct.unpack(
                "<80h", uc.mem_read(pending_adaptive["buffer_pointer"], 160)
            )
            if actual != pending_adaptive["expected"]:
                raise RuntimeError("candidate adaptive excitation differs from owned model")
            adaptive_stages.append({
                "delay": pending_adaptive["delay"],
                "fraction": pending_adaptive["fraction"],
                "output_sha256": hashlib.sha256(struct.pack("<80h", *actual)).hexdigest(),
                "matches_independent_model": True,
            })
            esp = uc.reg_read(UC_X86_REG_ESP)
            ebp = uc.reg_read(UC_X86_REG_EBP)
            subframe = struct.unpack("<h", uc.mem_read(esp + 0x10, 2))[0]
            delay = struct.unpack("<h", uc.mem_read(esp + 0x20, 2))[0]
            gain_code = struct.unpack(
                "<h", uc.mem_read(ebp + 0x434 + subframe * 2, 2)
            )[0]
            if not 0 <= gain_code < len(PITCH_GAINS):
                raise ValueError("candidate pitch gain code exceeds owned table")
            gain = PITCH_GAINS[gain_code]
            pending_mix = {
                "buffer_pointer": pending_adaptive["buffer_pointer"],
                "adaptive": pending_adaptive["expected"],
                "delay": delay,
                "gain_code": gain_code,
                "gain": gain,
            }
            pending_adaptive = None
        elif address == FIXED_START:
            if pending_fixed is not None:
                raise RuntimeError("nested candidate fixed excitation")
            ebp = uc.reg_read(UC_X86_REG_EBP)
            esp = uc.reg_read(UC_X86_REG_ESP)
            count = struct.unpack("<h", uc.mem_read(ebp + 0x428, 2))[0]
            if not 0 <= count <= 32:
                raise ValueError("unexpected candidate fixed-excitation groups")
            pending_fixed = {
                "buffer_pointer": esp + 0x40,
                "group_count": count,
                "config_pointer": struct.unpack(
                    "<I", uc.mem_read(esp + 0xE4, 4)
                )[0],
                "groups": [],
                "group_snapshots": [],
            }
            if pending_mix is None:
                raise RuntimeError("candidate mix did not start after adaptive stage")
            scaled = struct.unpack(
                "<80h", uc.mem_read(pending_mix["buffer_pointer"], 160)
            )
            expected_scaled = mix_candidate_excitation(
                pending_mix["adaptive"], (0,) * 80,
                pending_mix["gain"], pending_mix["delay"],
            )
            if scaled != expected_scaled:
                raise RuntimeError("candidate adaptive gain differs from owned model")
        elif address == FIXED_GROUP_READY and pending_fixed is not None:
            esp = uc.reg_read(UC_X86_REG_ESP)
            ebp = uc.reg_read(UC_X86_REG_EBP)
            group_index = struct.unpack("<I", uc.mem_read(esp + 0x14, 4))[0]
            subframe = struct.unpack("<I", uc.mem_read(esp + 0x10, 4))[0]
            config_pointer = struct.unpack("<I", uc.mem_read(esp + 0xE4, 4))[0]
            amplitude_index = struct.unpack("<h", uc.mem_read(esp + 0x30, 2))[0]
            if not 0 <= amplitude_index < len(PULSE_AMPLITUDES):
                raise ValueError("candidate pulse amplitude index exceeds owned table")
            amplitude = PULSE_AMPLITUDES[amplitude_index]
            position_code = struct.unpack(
                "<h", uc.mem_read(
                    ebp + 0x438 + subframe * 20 + group_index * 2, 2,
                ),
            )[0]
            sign_code = struct.unpack(
                "<h", uc.mem_read(
                    ebp + 0x460 + subframe * 20 + group_index * 2, 2,
                ),
            )[0]
            amplitude_code = struct.unpack(
                "<h", uc.mem_read(
                    ebp + 0x488 + subframe * 20 + group_index * 2, 2,
                ),
            )[0]
            position_table_pointer = struct.unpack(
                "<I", uc.mem_read(config_pointer + 0x10, 4)
            )[0]
            expected_position_pointer = (
                position_table_pointer + position_code * 8 +
                (0x100 if group_index & 1 else 0)
            )
            if uc.reg_read(UC_X86_REG_EBX) != expected_position_pointer:
                raise RuntimeError("candidate pulse position table addressing differs")
            table_entry = position_code + (32 if group_index & 1 else 0)
            positions = PULSE_POSITIONS[table_entry * 4:table_entry * 4 + 4]
            if struct.unpack(
                "<4h", uc.mem_read(uc.reg_read(UC_X86_REG_EBX), 8)
            ) != positions:
                raise RuntimeError("candidate pulse positions differ from owned table")
            sign_bits = struct.unpack("<4h", uc.mem_read(esp + 0x38, 8))
            if sign_bits != candidate_sign_bits(sign_code):
                raise RuntimeError("candidate pulse sign bits differ from owned model")
            group = CandidatePulseGroup(positions, sign_bits, amplitude)
            pending_fixed["groups"].append({
                "group_index": group_index,
                "subframe": subframe,
                "position_code": position_code,
                "sign_code": sign_code,
                "amplitude_code": amplitude_code,
                "amplitude_index": amplitude_index,
                "pulse_group": group,
            })
        elif address == FIXED_GROUP_END and pending_fixed is not None:
            values = struct.unpack(
                "<80h", uc.mem_read(pending_fixed["buffer_pointer"], 160)
            )
            expected = accumulate_candidate_pulses(tuple(
                item["pulse_group"] for item in pending_fixed["groups"]
            ))[-1]
            if values != expected:
                raise RuntimeError("candidate fixed pulses differ from owned model")
            pending_fixed["group_snapshots"].append([
                [index, value] for index, value in enumerate(values) if value
            ])
        elif address == FIXED_END and pending_fixed is not None:
            values = struct.unpack(
                "<80h", uc.mem_read(pending_fixed["buffer_pointer"], 160)
            )
            if len(pending_fixed["groups"]) != pending_fixed["group_count"]:
                raise RuntimeError("candidate fixed-pulse group count differs")
            prior_index = (
                fixed_stages[-1]["groups"][0]["amplitude_index"]
                if fixed_stages and pending_fixed["groups"] and
                pending_fixed["groups"][0]["subframe"] == 1 else None
            )
            expected_indices = candidate_amplitude_indices(
                tuple(item["amplitude_code"] for item in pending_fixed["groups"]),
                prior_index,
            )
            if expected_indices != tuple(
                item["amplitude_index"] for item in pending_fixed["groups"]
            ):
                raise RuntimeError(
                    "candidate amplitude index recurrence differs: "
                    f"prior={prior_index} prior_indices="
                    f"{tuple(item['amplitude_index'] for item in fixed_stages[-1]['groups']) if fixed_stages else ()} "
                    f"codes={tuple(item['amplitude_code'] for item in pending_fixed['groups'])} "
                    f"expected={expected_indices} actual={tuple(item['amplitude_index'] for item in pending_fixed['groups'])}"
                )
            expected = accumulate_candidate_pulses(tuple(
                item["pulse_group"] for item in pending_fixed["groups"]
            ))
            if values != (expected[-1] if expected else (0,) * 80):
                raise RuntimeError("candidate fixed-pulse buffer differs")
            subframe = pending_fixed["groups"][0]["subframe"] if pending_fixed["groups"] else 0
            frame_groups, anchor = groups_from_candidate_frame(
                parsed_fields, subframe, PULSE_POSITIONS, PULSE_AMPLITUDES,
                prior_index,
            )
            if frame_groups != tuple(
                item["pulse_group"] for item in pending_fixed["groups"]
            ) or (frame_groups and anchor != pending_fixed["groups"][0]["amplitude_index"]):
                raise RuntimeError("compressed frame fixed pulses differ from owned model")
            pending_mix["fixed"] = expected[-1] if expected else (0,) * 80
            fixed_stages.append({
                "group_count": pending_fixed["group_count"],
                "groups": [{
                    "group_index": item["group_index"],
                    "subframe": item["subframe"],
                    "position_code": item["position_code"],
                    "sign_code": item["sign_code"],
                    "amplitude_code": item["amplitude_code"],
                    "amplitude_index": item["amplitude_index"],
                    "positions": list(item["pulse_group"].positions),
                    "sign_bits": list(item["pulse_group"].sign_bits),
                    "amplitude": item["pulse_group"].amplitude,
                } for item in pending_fixed["groups"]],
                "group_snapshots": pending_fixed["group_snapshots"],
                "nonzero_pulses": [
                    [index, value] for index, value in enumerate(values) if value
                ],
                "matches_independent_model": True,
                "matches_compressed_field_model": True,
            })
            pending_fixed = None
        elif address == MIX_END and pending_mix is not None:
            actual = struct.unpack(
                "<80h", uc.mem_read(pending_mix["buffer_pointer"], 160)
            )
            expected = mix_candidate_excitation(
                pending_mix["adaptive"], pending_mix["fixed"],
                pending_mix["gain"], pending_mix["delay"],
            )
            if actual != expected:
                raise RuntimeError("candidate excitation mix differs from owned model")
            owned_intermediate = expected
            if history is not None:
                history.append_subframe(expected)
            mix_stages.append({
                "delay": pending_mix["delay"],
                "pitch_gain_code": pending_mix["gain_code"],
                "pitch_gain": pending_mix["gain"],
                "intermediate_sha256": hashlib.sha256(
                    struct.pack("<80h", *actual)
                ).hexdigest(),
                "matches_independent_model": True,
            })
            pending_mix = None
        elif address == BIT_READER:
            if pending is not None:
                raise RuntimeError("nested bit-reader entry")
            ret, output, bits, source, byte_pointer, bit_pointer = struct.unpack(
                "<6I", uc.mem_read(uc.reg_read(UC_X86_REG_ESP), 24)
            )
            byte_index = struct.unpack("<H", uc.mem_read(byte_pointer, 2))[0]
            bit_offset = struct.unpack("<H", uc.mem_read(bit_pointer, 2))[0]
            if bits < 1 or bits > 16 or bit_offset > 7:
                raise ValueError("unexpected candidate bit-reader width or offset")
            source_bytes = bytes(uc.mem_read(source, byte_index + 4))
            pending = {
                "return": ret, "output": output, "bits": bits,
                "byte_index_before": byte_index,
                "bit_offset_before": bit_offset,
                "byte_pointer": byte_pointer, "bit_pointer": bit_pointer,
                "expected": msb_bits(source_bytes, byte_index * 8 + bit_offset,
                                     bits),
            }
        elif address in BIT_READER_RETURNS and pending is not None:
            actual = struct.unpack("<H", uc.mem_read(pending["output"], 2))[0]
            entry = {
                "index": len(fields),
                "destination_from_context": pending["output"] - context,
                "bits": pending["bits"],
                "byte_index_before": pending["byte_index_before"],
                "bit_offset_before": pending["bit_offset_before"],
                "byte_index_after": struct.unpack(
                    "<H", uc.mem_read(pending["byte_pointer"], 2))[0],
                "bit_offset_after": struct.unpack(
                    "<H", uc.mem_read(pending["bit_pointer"], 2))[0],
                "value": actual,
                "matches_msb_reader": actual == pending["expected"],
            }
            fields.append(entry)
            pending = None

    hook = decoder.uc.hook_add(
        UC_HOOK_CODE, observe, begin=LSF_STEP,
        end=max(BIT_READER_RETURNS),
    )
    try:
        samples, pcm = decoder.decode(frame, context)
    finally:
        decoder.uc.hook_del(hook)
    if (pending is not None or pending_lsf is not None or
            pending_interpolation is not None or pending_dot is not None or
            pending_synthesis is not None or pending_pitch is not None or
            pending_adaptive is not None or pending_fixed is not None or
            pending_mix is not None or pending_lsf_prediction is not None or
            pending_lpc is not None or
            not fields or not codebook_stages or not lsf_predictor_stages or
            not lsf_subframe_stages or active_spectra is None or
            not lpc_stages or
            not lsf_stages or not interpolation_stages or
            not synthesis_stages or not pitch_stages or not adaptive_stages or
            not fixed_stages or not mix_stages):
        raise RuntimeError(
            "candidate trace is incomplete: "
            f"pending={bool(pending)}/{bool(pending_lsf)}/"
            f"{bool(pending_interpolation)}/{bool(pending_dot)}/"
            f"{bool(pending_synthesis)}/{bool(pending_pitch)}/"
            f"{bool(pending_adaptive)}/{bool(pending_fixed)}/"
            f"{bool(pending_mix)} fields={len(fields)} "
            f"prepare={len(lsf_stages)} interpolate={len(interpolation_stages)} "
            f"dot={len(dot_results)} synthesis={len(synthesis_stages)} "
            f"pitch={len(pitch_stages)} adaptive={len(adaptive_stages)} "
            f"fixed={len(fixed_stages)} mix={len(mix_stages)}"
        )
    if any(not item["matches_msb_reader"] for item in fields):
        raise RuntimeError("candidate bit-reader differs from MSB-first model")
    if len(fields) != len(parsed_fields):
        raise RuntimeError("candidate parser field count differs from owned parser")
    for observed, parsed in zip(fields, parsed_fields):
        if (observed["index"], observed["bits"],
            observed["destination_from_context"], observed["value"],
            observed["byte_index_before"] * 8 + observed["bit_offset_before"]
        ) != (parsed.index, parsed.bits, parsed.destination_from_context,
              parsed.value, parsed.start_bit):
            raise RuntimeError(f"candidate field {parsed.index} differs from owned parser")
    stage_pcm = b"".join(
        struct.pack(f"<{len(stage['output'])}h", *stage["output"])
        for stage in synthesis_stages
    )
    if history is not None:
        history.finish_frame()
    if active_spectra is not None:
        active_spectra.finish_frame()
        if struct.unpack("<10h", decoder.uc.mem_read(context + 0x438, 20)) != (
            active_spectra.previous
        ):
            raise RuntimeError("candidate saved prior LSF differs from owned state")
    return {
        "compressed_sha256": hashlib.sha256(frame).hexdigest(),
        "sample_count": samples,
        "pcm_sha256": hashlib.sha256(pcm).hexdigest(),
        "bit_count": sum(item["bits"] for item in fields),
        "layout_matches_independent_parser": True,
        "fields": fields,
        "candidate_codebook_stages": codebook_stages,
        "candidate_lsf_predictor_stages": lsf_predictor_stages,
        "lsf_state_from_zero_verified": lsf_predictor is not None,
        "candidate_lsf_subframe_stages": lsf_subframe_stages,
        "lsf_subframes_from_zero_verified": lsf_subframes is not None,
        "candidate_lpc_stages": lpc_stages,
        "candidate_preparation_stages": lsf_stages,
        "candidate_interpolation_stages": interpolation_stages,
        "candidate_dot_samples": {
            "count": len(dot_results),
            "first_eight": dot_results[:8],
            "signed32_sha256": hashlib.sha256(struct.pack(
                f"<{len(dot_results)}i", *dot_results,
            )).hexdigest(),
            "all_match_independent_model": True,
        },
        "candidate_synthesis_stages": [
            {key: value for key, value in stage.items() if key != "output"}
            for stage in synthesis_stages
        ],
        "synthesis_matches_returned_pcm": stage_pcm == pcm,
        "candidate_pitch_stages": pitch_stages,
        "candidate_adaptive_stages": adaptive_stages,
        "candidate_fixed_stages": fixed_stages,
        "candidate_mix_stages": mix_stages,
        "excitation_history_from_zero_verified": history is not None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dll", type=Path, required=True)
    parser.add_argument("--npe", type=Path, required=True)
    parser.add_argument("--section", type=int, required=True)
    parser.add_argument("--frame-index", type=int, default=0)
    parser.add_argument("--frame-count", type=int, default=1)
    parser.add_argument("--verify-owned-history", action="store_true",
                        help="start at frame zero and feed independently modeled mixed excitation into history")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.frame_index < 0 or args.frame_count < 1 or args.output.exists():
        parser.error("frame range must be positive and output must be new")
    if args.verify_owned_history and args.frame_index != 0:
        parser.error("owned excitation history verification must start at frame zero")
    npe = args.npe.read_bytes()
    section_offset, section_size = _parse_sections(npe)[args.section]
    section = npe[section_offset:section_offset + section_size]
    if section[:2] != b"\x20\x0d":
        parser.error("section is not format 13")
    declared = int.from_bytes(section[2:4], "big")
    if (section_size != ((4 + declared * 21 + 1) & ~1) or
            args.frame_index + args.frame_count > declared):
        parser.error("section length or frame range does not match the header")
    encoded = candidate_bytes(section[4:4 + declared * 21], "swap16", 0)
    dll = args.dll.read_bytes()
    decoder = IsolatedDecoder(dll)
    context, frame_bits = decoder.init(5)
    if frame_bits != 168:
        raise ValueError("candidate mode 5 frame size changed")
    for index in range(args.frame_index):
        start = index * 21
        decoder.decode(encoded[start:start + 21], context)
    history = CandidateExcitationHistory() if args.verify_owned_history else None
    lsf_predictor = CandidateLsfPredictor() if args.verify_owned_history else None
    lsf_subframes = CandidateLsfSubframes() if args.verify_owned_history else None
    frames = []
    for index in range(args.frame_index, args.frame_index + args.frame_count):
        start = index * 21
        traced = trace_frame(
            decoder, context, encoded[start:start + 21], history,
            lsf_predictor, lsf_subframes,
        )
        traced["frame_index"] = index
        frames.append(traced)
    result = frames[0] if args.frame_count == 1 else {
        "frames": frames,
        "frame_count": args.frame_count,
    }
    result.update({
        "schema": "np560-mobivoice-bitfields-v1",
        "candidate_not_mask_rom_truth": True,
        "dll_sha256": hashlib.sha256(dll).hexdigest(),
        "npe_sha256": hashlib.sha256(npe).hexdigest(),
        "section": args.section,
        "section_sha256": hashlib.sha256(section).hexdigest(),
        "frame_index": args.frame_index,
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "frame_count": len(frames),
        "field_count": sum(len(frame["fields"]) for frame in frames),
        "changed_preparation_steps": sum(
            stage["input"] != stage["output"]
            for frame in frames
            for stage in frame["candidate_preparation_stages"]
        ),
        "nonzero_preparation_statuses": sum(
            stage["status"] != 0
            for frame in frames
            for stage in frame["candidate_preparation_stages"]
        ),
    }))


if __name__ == "__main__":
    main()
