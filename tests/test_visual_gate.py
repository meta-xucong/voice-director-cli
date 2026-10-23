"""Tests for the mandatory user-facing visual selection and sample gate."""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from voice_director.errors import HumanReviewRequired, ValidationError
from voice_director.visual_gate import validate_visual_gate


ROOT = Path(__file__).resolve().parents[1]


def manifest(directory):
    options = []
    for index in range(1, 4):
        filename = f"option-{index}.png"
        content = b"\x89PNG\r\n\x1a\n" + f"visual option {index}".encode()
        (directory / filename).write_bytes(content)
        options.append({"id": str(index), "title": f"Direction {index}", "image_file": filename,
                        "sha256": hashlib.sha256(content).hexdigest()})
    return {"schema_version": 1, "options": options, "selected_option_id": None}


def fake_mp4(label=b"sample"):
    return b"\x00\x00\x00\x18ftypmp42" + label


class VisualGateTests(unittest.TestCase):
    def test_exactly_three_options_must_be_shown_and_wait_for_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = manifest(root)
            with self.assertRaises(HumanReviewRequired) as raised:
                validate_visual_gate(payload, root)
        self.assertEqual(raised.exception.report["gate"], "select_visual_direction")
        self.assertEqual(len(raised.exception.report["options"]), 3)
        self.assertIn("wait for the user's explicit selection", raised.exception.report["instruction"])

    def test_option_count_and_asset_hash_are_enforced(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = manifest(root)
            with self.assertRaisesRegex(ValidationError, "exactly three"):
                validate_visual_gate({**payload, "options": payload["options"][:2]}, root)
            (root / "option-2.png").write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "SHA-256 does not match"):
                validate_visual_gate(payload, root)

    def test_unknown_selection_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = manifest(root)
            payload["selected_option_id"] = "4"
            with self.assertRaisesRegex(ValidationError, "match one of"):
                validate_visual_gate(payload, root)

    def test_options_must_be_distinct_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = manifest(root)
            payload["options"][1]["image_file"] = payload["options"][0]["image_file"]
            payload["options"][1]["sha256"] = payload["options"][0]["sha256"]
            with self.assertRaisesRegex(ValidationError, "distinct image files and content hashes"):
                validate_visual_gate(payload, root)

    def test_option_must_be_a_real_image_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = manifest(root)
            (root / "option-2.png").write_bytes(b"not a png")
            payload["options"][1]["sha256"] = hashlib.sha256(b"not a png").hexdigest()
            with self.assertRaisesRegex(ValidationError, "matching file signature"):
                validate_visual_gate(payload, root)

    def test_selection_allows_only_short_sample_before_full_render(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = manifest(root)
            payload["selected_option_id"] = "3"
            report = validate_visual_gate(payload, root)
        self.assertEqual(report["status"], "STYLE_SELECTED")
        self.assertIn("full-lesson rendering remains blocked", report["instruction"])

    def test_pending_design_sample_requires_user_approval(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = manifest(root)
            payload["selected_option_id"] = "3"
            data = fake_mp4()
            (root / "design-sample.mp4").write_bytes(data)
            payload["design_sample"] = {"video_file": "design-sample.mp4", "sha256": hashlib.sha256(data).hexdigest(),
                                        "based_on_option_id": "3",
                                        "decision_status": "pending"}
            with self.assertRaises(HumanReviewRequired) as raised:
                validate_visual_gate(payload, root)
        self.assertEqual(raised.exception.report["gate"], "approve_design_sample")
        self.assertIn("do not render the full lesson", raised.exception.report["instruction"])

    def test_sample_must_reference_the_selected_visual_direction(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = manifest(root)
            payload["selected_option_id"] = "3"
            data = fake_mp4()
            (root / "design-sample.mp4").write_bytes(data)
            payload["design_sample"] = {"video_file": "design-sample.mp4", "sha256": hashlib.sha256(data).hexdigest(),
                                        "based_on_option_id": "2", "decision_status": "approved"}
            with self.assertRaisesRegex(ValidationError, "must match selected_option_id"):
                validate_visual_gate(payload, root)

    def test_revision_request_keeps_full_render_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = manifest(root)
            payload["selected_option_id"] = "3"
            data = fake_mp4()
            (root / "design-sample.mp4").write_bytes(data)
            payload["design_sample"] = {"video_file": "design-sample.mp4", "sha256": hashlib.sha256(data).hexdigest(),
                                        "based_on_option_id": "3",
                                        "decision_status": "revision_requested", "feedback": "The labels feel crowded."}
            with self.assertRaises(HumanReviewRequired) as raised:
                validate_visual_gate(payload, root)
        self.assertEqual(raised.exception.report["gate"], "revise_design_sample")
        self.assertEqual(raised.exception.report["feedback"], "The labels feel crowded.")

    def test_approved_png_cannot_masquerade_as_design_video(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = manifest(root)
            payload["selected_option_id"] = "3"
            data = (root / "option-3.png").read_bytes()
            payload["design_sample"] = {"video_file": "option-3.png", "sha256": hashlib.sha256(data).hexdigest(),
                                        "based_on_option_id": "3", "decision_status": "approved"}
            with self.assertRaisesRegex(ValidationError, "MP4-family video"):
                validate_visual_gate(payload, root)

    def test_approved_hash_bound_sample_opens_full_render_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = manifest(root)
            payload["selected_option_id"] = "3"
            data = fake_mp4()
            (root / "design-sample.mp4").write_bytes(data)
            payload["design_sample"] = {"video_file": "design-sample.mp4", "sha256": hashlib.sha256(data).hexdigest(),
                                        "based_on_option_id": "3",
                                        "decision_status": "approved"}
            report = validate_visual_gate(payload, root)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["gate"], "full_lesson_render_allowed")

    def test_cli_prints_style_choice_packet_with_exit_code_three(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = manifest(root)
            path = root / "visual-gate.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = subprocess.run([sys.executable, "-m", "voice_director", "visual-gate", "--manifest", str(path)],
                                    cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 3)
        report = json.loads(result.stdout)
        self.assertEqual(report["gate"], "select_visual_direction")
        self.assertEqual(len(report["options"]), 3)


if __name__ == "__main__":
    unittest.main()
