"""Owned stateful decoder for the reviewed candidate's mode-5 frames.

It decodes one normalized 21-byte compressed frame to 160 signed PCM words,
using independently modeled lookup, predictor, excitation and synthesis
stages.  Compatibility with the archived candidate is testable; identity
with the unavailable NP560 mask ROM is not established by this module.
"""

from __future__ import annotations

try:
    from .np560_mobivoice_adaptive import generate_candidate_adaptive
    from .np560_mobivoice_codebooks import candidate_codebook_vector
    from .np560_mobivoice_fields import parse_mode5_frame
    from .np560_mobivoice_fixed import (
        accumulate_candidate_pulses, groups_from_candidate_frame,
    )
    from .np560_mobivoice_history import CandidateExcitationHistory
    from .np560_mobivoice_lsf import normalize_candidate_words
    from .np560_mobivoice_lsf_predict import CandidateLsfPredictor
    from .np560_mobivoice_lsf_subframes import CandidateLsfSubframes
    from .np560_mobivoice_lpc import candidate_lpc_from_lsf
    from .np560_mobivoice_mix import mix_candidate_excitation
    from .np560_mobivoice_pitch import pitch_calls_from_candidate_frame
    from .np560_mobivoice_synthesis import synthesize_candidate_block
    from .np560_mobivoice_tables import (
        PITCH_GAINS, PULSE_AMPLITUDES, PULSE_POSITIONS,
        interpolation_phase_taps,
    )
except ImportError:  # Direct scripts/ execution.
    from np560_mobivoice_adaptive import generate_candidate_adaptive
    from np560_mobivoice_codebooks import candidate_codebook_vector
    from np560_mobivoice_fields import parse_mode5_frame
    from np560_mobivoice_fixed import (
        accumulate_candidate_pulses, groups_from_candidate_frame,
    )
    from np560_mobivoice_history import CandidateExcitationHistory
    from np560_mobivoice_lsf import normalize_candidate_words
    from np560_mobivoice_lsf_predict import CandidateLsfPredictor
    from np560_mobivoice_lsf_subframes import CandidateLsfSubframes
    from np560_mobivoice_lpc import candidate_lpc_from_lsf
    from np560_mobivoice_mix import mix_candidate_excitation
    from np560_mobivoice_pitch import pitch_calls_from_candidate_frame
    from np560_mobivoice_synthesis import synthesize_candidate_block
    from np560_mobivoice_tables import (
        PITCH_GAINS, PULSE_AMPLITUDES, PULSE_POSITIONS,
        interpolation_phase_taps,
    )


class CandidateMode5Decoder:
    def __init__(self) -> None:
        self.lsf_predictor = CandidateLsfPredictor()
        self.lsf_subframes = CandidateLsfSubframes()
        self.excitation = CandidateExcitationHistory()
        self.pcm_history = (0,) * 10

    def decode_frame(self, frame: bytes) -> tuple[int, ...]:
        """Decode one normalized compressed frame, committing state on success."""
        fields = parse_mode5_frame(frame)
        values = {field.destination_from_context: field.value for field in fields}
        predictor = CandidateLsfPredictor(self.lsf_predictor.state)
        spectra = CandidateLsfSubframes(self.lsf_subframes.previous)
        excitation = CandidateExcitationHistory()
        excitation.prior_frame = self.excitation.prior_frame
        pcm_history = self.pcm_history

        vector = candidate_codebook_vector(fields)
        normalized, _status = normalize_candidate_words(predictor.step(vector))
        spectra.begin_frame(normalized)
        pitches = pitch_calls_from_candidate_frame(fields)
        samples: list[int] = []
        anchor = None
        for subframe, pitch in enumerate(pitches):
            coefficients = candidate_lpc_from_lsf(spectra.subframe(subframe))
            needed = pitch.delay + (14 if pitch.fraction else 0)
            adaptive = generate_candidate_adaptive(
                excitation.tail(needed), pitch.delay, pitch.fraction,
                interpolation_phase_taps(pitch.fraction)
                if pitch.fraction else None,
            )
            groups, anchor = groups_from_candidate_frame(
                fields, subframe, PULSE_POSITIONS, PULSE_AMPLITUDES, anchor,
            )
            fixed = accumulate_candidate_pulses(groups)[-1]
            gain_code = values[0x46C + subframe * 2]
            if not 0 <= gain_code < len(PITCH_GAINS):
                raise ValueError("candidate pitch gain code exceeds table")
            mixed = mix_candidate_excitation(
                adaptive, fixed, PITCH_GAINS[gain_code], pitch.delay,
            )
            output = synthesize_candidate_block(
                mixed, pcm_history, coefficients[1:],
            )
            pcm_history = output[-10:]
            excitation.append_subframe(mixed)
            samples.extend(output)

        spectra.finish_frame()
        excitation.finish_frame()
        if len(samples) != 160:
            raise RuntimeError("candidate mode-5 frame did not produce 160 samples")
        self.lsf_predictor = predictor
        self.lsf_subframes = spectra
        self.excitation = excitation
        self.pcm_history = pcm_history
        return tuple(samples)
