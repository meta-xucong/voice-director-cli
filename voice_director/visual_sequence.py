"""Structural validation for harness-authored, cross-beat visual sequences."""

import math

from .errors import ValidationError


_STAGES = ("context_a", "detail_a", "context_b", "detail_b", "synthesis")
_MOVEMENTS = {"source_linked_zoom", "mask_reveal", "matched_push", "slide_align"}
_EASINGS = {"ease_in_out"}
_CONTEXT_BACKGROUNDS = {"blurred_source", "removed_or_replaced"}
_MAX_PIXEL_DIMENSION = 1_000_000


def _object(value, label):
    if not isinstance(value, dict):
        raise ValidationError(f"{label} must be an object")
    return value


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} must be a non-empty string")
    return value


def _number(value, label, *, minimum=0, maximum=None):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or (isinstance(value, float) and not math.isfinite(value)) or value < minimum):
        raise ValidationError(f"{label} must be a finite number >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValidationError(f"{label} must be <= {maximum}")
    return value


def _pixel_number(value, label, *, minimum=0, maximum=None):
    value = _number(value, label, minimum=minimum, maximum=maximum)
    if not isinstance(value, int) and not value.is_integer():
        raise ValidationError(f"{label} must align to an integer pixel")
    return value


def validate_visual_sequences(payload):
    """Validate a visual-sequence declaration without asserting semantic quality.

    The harness authors the sequence after interpreting the narration and reviewing
    assets. This function only verifies declared structure, evidence links and geometry.
    """
    sequences = payload.get("visual_sequences", [])
    if not isinstance(sequences, list):
        raise ValidationError("visual_sequences must be an array")

    beats = payload.get("beats", [])
    by_id = {beat["id"]: (index, beat) for index, beat in enumerate(beats)}
    seen_ids = set()
    reports = []
    for sequence_index, sequence in enumerate(sequences, 1):
        prefix = f"visual_sequences[{sequence_index}]"
        sequence = _object(sequence, prefix)
        sequence_id = _text(sequence.get("id"), f"{prefix}.id")
        if sequence_id in seen_ids:
            raise ValidationError(f"duplicate visual sequence id: {sequence_id}")
        seen_ids.add(sequence_id)
        if sequence.get("pattern") != "contrast_reveal":
            raise ValidationError(f"{prefix}.pattern must be contrast_reveal")
        _text(sequence.get("trigger"), f"{prefix}.trigger")
        _text(sequence.get("takeaway"), f"{prefix}.takeaway")

        stage_beats = _object(sequence.get("stage_beats"), f"{prefix}.stage_beats")
        if set(stage_beats) != set(_STAGES):
            raise ValidationError(f"{prefix}.stage_beats must declare exactly {_STAGES}")
        stage_ids = [_text(stage_beats[stage], f"{prefix}.stage_beats.{stage}") for stage in _STAGES]
        unknown = [beat_id for beat_id in stage_ids if beat_id not in by_id]
        if unknown:
            raise ValidationError(f"{prefix} references unknown beat {unknown[0]}")
        indices = [by_id[beat_id][0] for beat_id in stage_ids]
        if indices != sorted(indices) or len(set(indices)) != len(_STAGES):
            raise ValidationError(f"{prefix}.stage_beats must reference five distinct beats in teaching order")
        for stage in _STAGES:
            beat_id = _text(stage_beats[stage], f"{prefix}.stage_beats.{stage}")
            _, beat = by_id[beat_id]
            marker = _object(beat.get("visual_sequence"), f"beats[{beat_id}].visual_sequence")
            if marker.get("id") != sequence_id or marker.get("stage") != stage:
                raise ValidationError(f"beat {beat_id} is not marked as {sequence_id}/{stage}")
            expected_participant = ("a" if stage.endswith("_a") else "b" if stage.endswith("_b") else None)
            if expected_participant and marker.get("participant_id") != expected_participant:
                raise ValidationError(f"beat {beat_id} must name participant {expected_participant}")
            _number(beat.get("duration_seconds"), f"beat {beat_id}.duration_seconds", minimum=1.5, maximum=12)
        participants = sequence.get("participants")
        if not isinstance(participants, list) or len(participants) != 2:
            raise ValidationError(f"{prefix}.participants must contain exactly two participants")
        participant_ids = set()
        for participant_index, participant in enumerate(participants, 1):
            pfx = f"{prefix}.participants[{participant_index}]"
            participant = _object(participant, pfx)
            participant_id = _text(participant.get("id"), f"{pfx}.id")
            if participant_id in participant_ids:
                raise ValidationError(f"{prefix} participant ids must be distinct")
            participant_ids.add(participant_id)
            _text(participant.get("label"), f"{pfx}.label")
            if participant.get("authentic") is not True:
                raise ValidationError(f"{pfx} must be marked authentic")
            source = _text(participant.get("asset_source"), f"{pfx}.asset_source")
            _text(participant.get("focus"), f"{pfx}.focus")
            context_stage, detail_stage = (("context_a", "detail_a") if participant_index == 1
                                            else ("context_b", "detail_b"))
            for stage in (context_stage, detail_stage):
                stage_id = stage_beats[stage]
                stage_beat = by_id[stage_id][1]
                matches = [asset for asset in stage_beat.get("assets", [])
                           if asset.get("kind") == "real_ui" and asset.get("source") == source
                           and asset.get("authentic") is True]
                if not matches:
                    raise ValidationError(f"{pfx}.asset_source must match an authentic real_ui asset in {stage}")

            regions = participant.get("source_pixel_regions")
            if not isinstance(regions, list) or not regions:
                raise ValidationError(f"{pfx}.source_pixel_regions must be a non-empty array")
            region_ids = set()
            for region_index, region in enumerate(regions, 1):
                rfx = f"{pfx}.source_pixel_regions[{region_index}]"
                region = _object(region, rfx)
                rm���h��춻�q�^tcourseware narration/screen contract."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from voice_director.errors import HumanReviewRequired, ValidationError
from voice_director.voice_screen import validate_voice_screen_map


ROOT = Path(__file__).resolve().parents[1]


def beat(**overrides):
    result = {
        "id": "B01",
        "duration_seconds": 8,
        "screen_text": 'wire_api = "responses"',
        "focus": "wire_api row",
        "transition": {"entry": "fade", "exit": "fade", "motion": "slow push-in"},
        "voice_mode": "summary",
        "narration": "协议必须与服务端兼容，先配置再做小任务验证。",
        "spoken_purpose": "Explain compatibility and verification, not the syntax.",
        "technical_display": True,
        "required_screen_terms": ['wire_api = "responses"'],
        "screen_only_terms": ["wire_api = \"responses\""],
        "assets": [{"kind": "real_ui", "source": "official Codex screenshot", "authentic": True}],
    }
    result.update(overrides)
    return result


def contrast_map():
    stages = ["context_a", "detail_a", "context_b", "detail_b", "synthesis"]
    def region(region_id, purpose, x, y, width, height, display_width, display_height):
        return {"id": region_id, "purpose": purpose, "crop": {
            "coordinate_space": "source_pixels", "x": x, "y": y, "width": width, "height": height,
            "source_width": 1920, "source_height": 1140,
            "display_width": display_width, "display_height": display_height}}
    participants = [
        {"id": "codex", "label": "Codex", "asset_source": "user Codex capture", "authentic": True,
         "focus": "Codex project selector", "source_pixel_regions": [
             region("identity", "Product identity", 64, 48, 260, 150, 250, 144),
             region("task", "Code task context", 390, 70, 900, 140, 880, 137)]},
        {"id": "work", "label": "ChatGPT Work", "asset_source": "user Work capture", "authentic": True,
         "focus": "ChatGPT selector and Work composer", "source_pixel_regions": [
             region("identity", "Product identity", 64, 48, 260, 150, 250, 144),
             region("work", "ChatGPT Work composer", 490, 990, 900, 140, 880, 137)]},
    ]
    beats = []
    for index, stage in enumerate(stages, 1):
        participant_id = "codex" if stage.endswith("_a") else "work" if stage.endswith("_b") else None
        assets = []
        if stage != "synthesis":
            participant = participants[0 if participant_id == "codex" else 1]
            assets = [{"kind": "real_ui", "source": participant["asset_source"], "authentic": True}]
        else:
            assets = [{"kind": "real_ui", "source": participant["asset_source"], "authentic": True}
                      for participant in participants]
        beats.append(beat(id=f"B{index:02d}", duration_seconds=4, technical_display=False,
                          required_screen_terms=[], screen_only_terms=[], assets=assets,
                          visual_sequence={"id": "chatgpt-codex", "stage": stage,
                                           **({"participant_id": "a" if participant_id == "codex" else "b"}
                                              if participant_id else {})}))
    payload = {"schema_version": 1, "beats": beats, "visual_sequences": [{
        "id": "chatgpt-codex", "pattern": "contrast_reveal",
        "trigger": "旁白明确比较 Codex 与 ChatGPT Work。", "takeaway": "Codex 聚焦项目工作；桌面 ChatGPT 对应网页版 Work。",
        "stage_beats": dict(zip(stages, [f"B{index:02d}" for index in range(1, 6)])),
        "participants": participants,
        "motion": {"movement": "source_linked_zoom", "easing": "ease_in_out",
                   "pixel_alignment": "integer_pixel_grid", "context_background": "blurred_source",
                   "context_hold_seconds": 2, "reframe_seconds": 0.6, "context_blur_px": 8,
                   "detail_hold_seconds": 2.5, "synthesis_hold_seconds": 3},
    }]}
    return payload


class VoiceScreenContractTests(unittest.TestCase):
    def test_summary_keeps_exact_config_on_screen_and_passes(self):
        report = validate_voice_screen_map({"schema_version": 1, "beats": [beat()]})
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["beat_count"], 1)

    def test_summary_cannot_read_config_assignment_aloud(self):
        payload = {"schema_version": 1, "beats": [beat(narration='wire_api = "responses"')]} 
        with self.assertRaisesRegex(ValidationError, "assignment syntax"):
            validate_voice_screen_map(payload)

    def test_required_exact_config_fields_must_appear_on_screen(self):
        payload = {"schema_version": 1, "beats": [beat(screen_text="only a heading")]} 
        with self.assertRaisesRegex(ValidationError, "missing required exact text"):
            validate_voice_screen_map(payload)

    def test_screen_only_terms_cannot_be_repeated_in_summary(self):
        payload = {"schema_version": 1, "beats": [beat(narration="先设置 wire_api = \"responses\" 再测试。")]} 
        with self.assertRaisesRegex(ValidationError, "screen-only term"):
            validate_voice_screen_map(payload)

    def test_live_credentials_are_rejected(self):
        payload = {"schema_version": 1, "beats": [beat(screen_text='wire_api = "responses"\nOPENAI_API_KEY=sk-proj-abcdefghijklmnop1234')]} 
        with self.assertRaisesRegex(ValidationError, "credential"):
            validate_voice_screen_map(payload)

    def test_pending_visual_uncertainty_surfaces_human_review_packet(self):
        uncertainty = {"question": "Is this screenshot desktop or mobile?", "evidence": "The crop omits the window frame.",
                       "impact": "Learners may mistake the interface type.", "recommendation": "Label as mobile or replace it.",
                       "decision_status": "pending"}
        with self.assertRaises(HumanReviewRequired) as raised:
            validate_voice_screen_map({"schema_version": 1, "beats": [beat(uncertainty=uncertainty)]})
        self.assertEqual(raised.exception.report["status"], "AWAITING_HUMAN")
        self.assertEqual(raised.exception.report["pending_uncertainties"][0]["question"], uncertainty["question"])

    def test_long_hold_requires_reason(self):
        with self.assertRaisesRegex(ValidationError, "duration_reason"):
            validate_voice_screen_map({"schema_version": 1, "beats": [beat(duration_seconds=13)]})

    def test_contrast_reveal_checks_stages_sources_and_reports_sequence(self):
        report = validate_voice_screen_map(contrast_map())
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["visual_sequences"][0]["beat_ids"], ["B01", "B02", "B03", "B04", "B05"])
        self.assertEqual(report["visual_sequences"][0]["region_ids"], [["identity", "task"], ["identity", "work"]])
        self.assertEqual(report["visual_sequences"][0]["pixel_alignment"], "integer_pixel_grid")
        self.assertEqual(report["visual_sequences"][0]["context_background"], "blurred_source")
        self.assertEqual(report["visual_sequences"][0]["context_blur_px"], 8)

    def test_contrast_reveal_rejects_reordered_beats(self):
        payload = contrast_map()
        payload["visual_sequences"][0]["stage_beats"]["detail_a"] = "B04"
        with self.assertRaisesRegex(ValidationError, "teaching order"):
            validate_voice_screen_map(payload)

    def test_contrast_reveal_requires_authentic_source_in_context_and_detail(self):
        payload = contrast_map()
        payload["beats"][1]["assets"][0]["authentic"] = False
        with self.assertRaisesRegex(ValidationError, "real_ui assets must be explicitly marked authentic"):
            validate_voice_screen_map(payload)

    def test_contrast_reveal_rejects_out_of_bounds_and_upscaled_crops(self):
        payload = contrast_map()
        payload["visual_sequences"][0]["participants"][0]["source_pixel_regions"][0]["crop"]["x"] = 1700
        with self.assertRaisesRegex(ValidationError, "extends beyond"):
            validate_voice_screen_map(payload)
        payload = contrast_map()
        payload["visual_sequences"][0]["participants"][0]["source_pixel_regions"][0]["crop"]["display_width"] = 300
        with self.assertRaisesRegex(ValidationError, "would be upscaled"):
            validate_voice_screen_map(payload)

    def test_contrast_reveal_rejects_non_finite_geometry(self):
        for invalid in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(invalid=invalid):
                payload = contrast_map()
                payload["visual_sequences"][0]["participants"][0]["source_pixel_regions"][0]["crop"]["x"] = invalid
                with self.assertRaisesRegex(ValidationError, "finite number"):
                    validate_voice_screen_map(payload)

    def test_contrast_reveal_rejects_extremely_large_integer_coordinates_cleanly(self):
        payload = contrast_map()
        payload["visual_sequences"][0]["participants"][0]["source_pixel_regions"][0]["crop"]["x"] = 10 ** 10000
        with self.assertRaisesRegex(ValidationError, "<= 1000000"):
            validate_voice_screen_map(payload)
        payload = contrast_map()
        crop = payload["visual_sequences"][0]["participants"][0]["source_pixel_regions"][0]["crop"]
        crop.update({"width": 10 ** 1000, "height": 1, "source_width": 2 * 10 ** 1000,
                     "source_height": 2, "display_width": 1, "display_height": 1})
        with self.assertRaisesRegex(ValidationError, "<= 1000000"):
            validate_voice_screen_map(payload)

    def test_contrast_reveal_holds_fit_inside_their_beats(self):
        payload = contrast_map()
        payload["visual_sequences"][0]["motion"]["synthesis_hold_seconds"] = 4
        payload["beats"][4]["duration_seconds"] = 3.5
        with self.assertRaisesRegex(ValidationError, "exceeds the synthesis beat duration"):
            validate_voice_screen_map(payload)

    def test_contrast_reveal_rejects_unhashable_enum_values_cleanly(self):
        payload = contrast_map()
        payload["visual_sequences"][0]["motion"]["movement"] = []
        with self.assertRaisesRegex(ValidationError, "motion.movement must be a non-empty string"):
            validate_voice_screen_map(payload)
        payload = contrast_map()
        payload["visual_sequences"][0]["uncertainty"] = {
            "question": "Question?", "evidence": "Evidence.", "impact": "Impact.",
            "recommendation": "Recommendation.", "decision_status": []}
        with self.assertRaisesRegex(ValidationError, "decision_status must be a non-empty string"):
            validate_voice_screen_map(payload)

    def test_contrast_reveal_context_blur_is_bounded(self):
        for invalid in (-0.1, 16.1):
            with self.subTest(invalid=invalid):
                payload = contrast_map()
                payload["visual_sequences"][0]["motion"]["context_blur_px"] = invalid
                with self.assertRaisesRegex(ValidationError, "context_blur_px"):
                    validate_voice_screen_map(payload)

    def test_contrast_reveal_requires_explicit_background_treatment_and_blur(self):
        payload = contrast_map()
        del payload["visual_sequences"][0]["motion"]["context_blur_px"]
        with self.assertRaisesRegex(ValidationError, "context_blur_px"):
            validate_voice_screen_map(payload)
        payload = contrast_map()
        payload["visual_sequences"][0]["motion"].update({"context_background": "blurred_source", "context_blur_px": 0})
        with self.assertRaisesRegex(ValidationError, "must be > 0"):
            validate_voice_screen_map(payload)
        payload = contrast_map()
        payload["visual_sequences"][0]["motion"].update({"context_background": "removed_or_replaced", "context_blur_px": 8})
        with self.assertRaisesRegex(ValidationError, "must be 0"):
            validate_voice_screen_map(payload)

    def test_contrast_reveal_requires_smooth_pixel_aligned_motion(self):
        payload = contrast_map()
        payload["visual_sequences"][0]["motion"]["easing"] = "linear"
        with self.assertRaisesRegex(ValidationError, "motion.easing"):
            validate_voice_screen_map(payload)
        payload = contrast_map()
        payload["visual_sequences"][0]["motion"]["pixel_alignment"] = "subpixel"
        with self.assertRaisesRegex(ValidationError, "integer_pixel_grid"):
            validate_voice_screen_map(payload)

    def test_contrast_reveal_rejects_fractional_crop_geometry(self):
        for field in ("x", "y", "width", "height", "display_width", "display_height"):
            with self.subTest(field=field):
                payload = contrast_map()
                payload["visual_sequences"][0]["participants"][0]["source_pixel_regions"][0]["crop"][field] += 0.5
                with self.assertRaisesRegex(ValidationError, "integer pixel"):
                    validate_voice_screen_map(payload)

    def test_contrast_reveal_pending_uncertainty_surfaces_in_human_packet(self):
        payload = contrast_map()
        payload["visual_sequences"][0]["uncertainty"] = {
            "question": "Does the crop show the same ChatGPT Work surface?",
            "evidence": "The selector is visible but the web mapping is not shown in this image.",
            "impact": "Learners could confuse brand identity with interface type.",
            "recommendation": "Add the Work composer label or ask the user for a clearer capture.",
            "decision_status": "pending"}
        with self.assertRaises(HumanReviewRequired) as raised:
            validate_voice_screen_map(payload)
        self.assertEqual(raised.exception.report["status"], "AWAITING_HUMAN")
        self.assertEqual(raised.exception.report["pending_uncertainties"][0]["sequence_id"], "chatgpt-codex")

    def test_cli_exposes_uncertainty_packet_with_awaiting_exit_code(self):
        payload = {"schema_version": 1, "beats": [beat(uncertainty={
            "question": "Use this visual?", "evidence": "Source attribution is partial.", "impact": "Could mislead a learner.",
            "recommendation": "Confirm it or replace the asset.", "decision_status": "pending"})]}
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "voice-screen-map.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = subprocess.run([sys.executable, "-m", "voice_director", "validate-voice-screen", "--map", str(path)],
                                    cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 3)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "AWAITING_HUMAN")
        self.assertEqual(report["pending_uncertainties"][0]["question"], "Use this visual?")


if __name__ == "__main__":
    unittest.main()
