"""Tests for the offline courseware narration/screen contract."""

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
                   "context_hold_seconds": 2.7, "reframe_seconds": 0.6, "context_blur_px": 8,
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

    def test_contrast_reveal_requires_a_readable_full_context_hold(self):
        payload = contrast_map()
        payload["visual_sequences"][0]["motion"]["context_hold_seconds"] = 2.49
        with self.assertRaisesRegex(ValidationError, "context_hold_seconds"):
            validate_voice_screen_map(payload)

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
