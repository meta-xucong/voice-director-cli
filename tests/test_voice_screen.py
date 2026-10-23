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
