"""Contract tests for sample and final video quality evidence."""

import copy
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from voice_director.cli import main
from voice_director.errors import HumanReviewRequired, ValidationError
from voice_director.visual_quality import _extract_video_rgb, _image_dimensions, validate_visual_quality_review
from tests.visual_quality_fixtures import (VIDEO_PROBE, fake_image_pixels, fake_video_frames,
                                           make_quality_review, make_video, make_visual_gate, sha, write_json)


class VisualQualityTests(unittest.TestCase):
    def setup_review(self, root):
        return make_quality_review(root)

    def validate(self, payload, root, project_root, probe=None):
        with patch("voice_director.visual_quality._extract_video_rgb", side_effect=fake_video_frames), \
                patch("voice_director.visual_quality._decode_image_rgb", side_effect=fake_image_pixels):
            return validate_visual_quality_review(payload, root, project_root, probe=probe or VIDEO_PROBE)

    def test_webp_dimensions_are_read_from_the_real_image_header(self):
        data = (b"RIFF" + (22).to_bytes(4, "little") + b"WEBPVP8X" + (10).to_bytes(4, "little")
                + bytes(4) + (1919).to_bytes(3, "little") + (1079).to_bytes(3, "little"))
        self.assertEqual(_image_dimensions(Path("direction.webp"), data, "direction"), (1920, 1080))

    def test_large_evidence_sets_are_extracted_in_bounded_streaming_batches(self):
        commands, scripts, consumed = [], [], []

        class FrameStream:
            def read(self, size):
                return b"x" * size if size == 12 else b""

            def close(self):
                pass

        class ErrorStream:
            def read(self, _size):
                return b""

            def close(self):
                pass

        class Process:
            stdout = FrameStream()
            stderr = ErrorStream()

            def wait(self, timeout=None):
                return 0

            def poll(self):
                return 0

        def popen(command, **_kwargs):
            commands.append(command)
            script_path = Path(command[command.index("-filter_complex_script") + 1])
            scripts.append((script_path, script_path.read_text(encoding="utf-8")))
            return Process()

        refs = [("B01", f"F{i}", i / 30, i) for i in range(521)]
        with patch("voice_director.visual_quality.subprocess.Popen", side_effect=popen), \
                patch("voice_director.visual_quality._ffmpeg_executable", return_value="ffmpeg"):
            _extract_video_rgb("lesson.mp4", refs, {"width": 2, "height": 2}, None,
                               lambda index, pixels: consumed.append((index, len(pixels))))
        self.assertEqual(len(consumed), 521)
        self.assertTrue(all(size == 12 for _, size in consumed))
        self.assertEqual(len(commands), 1)
        self.assertEqual(scripts[0][1].count("eq("), 521)
        self.assertNotIn(scripts[0][1], commands[0])
        self.assertFalse(scripts[0][0].exists())

    def test_stalled_ffmpeg_pipe_is_killed_by_the_streaming_deadline(self):
        stopped = threading.Event()

        class BlockingStream:
            def read(self, _size):
                stopped.wait(timeout=2)
                return b""

            def close(self):
                pass

        class EmptyErrorStream:
            def read(self, _size):
                return b""

            def close(self):
                pass

        class Process:
            stdout = BlockingStream()
            stderr = EmptyErrorStream()

            def kill(self):
                stopped.set()

            def poll(self):
                return 0 if stopped.is_set() else None

            def wait(self, timeout=None):
                stopped.set()
                return -9

        with patch("voice_director.visual_quality.subprocess.Popen", return_value=Process()), \
                patch("voice_director.visual_quality._ffmpeg_executable", return_value="ffmpeg"), \
                patch("voice_director.visual_quality._FRAME_EXTRACTION_TIMEOUT_SECONDS", 0.01):
            with self.assertRaisesRegex(ValidationError, "timed out while extracting"):
                _extract_video_rgb("lesson.mp4", [("B01", "F1", 0, 0)],
                                   {"width": 2, "height": 2}, None, lambda *_: None)

    def test_complete_sample_quality_packet_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload, _, _, project_root, _, _, _ = self.setup_review(root)
            report = self.validate(payload, root, project_root)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["stage"], "design_sample")
        self.assertEqual(report["probe"]["width"], 1920)
        self.assertEqual(len(report["beats"]), 3)
        self.assertTrue(report["beats"][0]["annotation_checks"])

    def test_resolution_and_progressive_frame_rate_are_enforced(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload, _, _, project_root, _, _, _ = self.setup_review(root)
            probe = copy.deepcopy(VIDEO_PROBE)
            probe["streams"][0]["width"] = 1280
            probe["streams"][0]["height"] = 720
            with self.assertRaisesRegex(ValidationError, "at least 1920x1080"):
                self.validate(payload, root, project_root, probe)
            probe = copy.deepcopy(VIDEO_PROBE)
            probe["streams"][0]["avg_frame_rate"] = "25/1"
            probe["streams"][0]["r_frame_rate"] = "25/1"
            with self.assertRaisesRegex(ValidationError, "at least 30 fps"):
                self.validate(payload, root, project_root, probe)

    def test_variable_frame_rate_and_nonzero_start_time_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload, _, _, project_root, _, _, _ = self.setup_review(root)
            probe = copy.deepcopy(VIDEO_PROBE)
            probe["streams"][0]["r_frame_rate"] = "60/1"
            with self.assertRaisesRegex(ValidationError, "constant frame rate"):
                self.validate(payload, root, project_root, probe)
            probe = copy.deepcopy(VIDEO_PROBE)
            probe["streams"][0]["start_time"] = "1.0"
            with self.assertRaisesRegex(ValidationError, "start at timestamp zero"):
                self.validate(payload, root, project_root, probe)
            probe = copy.deepcopy(VIDEO_PROBE)
            probe["streams"][0]["field_order"] = "tt"
            with self.assertRaisesRegex(ValidationError, "progressive"):
                self.validate(payload, root, project_root, probe)

    def test_sample_must_be_twenty_to_sixty_seconds(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload, _, _, project_root, _, _, _ = self.setup_review(root)
            probe = copy.deepcopy(VIDEO_PROBE)
            probe["streams"][0]["duration"] = "19.9"
            probe["format"]["duration"] = "19.9"
            with self.assertRaisesRegex(ValidationError, "20–60 seconds"):
                self.validate(payload, root, project_root, probe)

    def test_screenshot_source_pixels_cannot_be_upscaled(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload, _, _, project_root, _, _, _ = self.setup_review(root)
            placement = payload["beats"][0]["screenshot_placement"]
            placement["source_crop"]["width"] = 960
            placement["source_crop"]["height"] = 540
            with self.assertRaisesRegex(ValidationError, "upscales source pixels"):
                self.validate(payload, root, project_root)

    def test_screenshot_must_not_be_stretched(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload, _, _, project_root, _, _, _ = self.setup_review(root)
            payload["beats"][0]["screenshot_placement"]["display_rect"]["height"] = 960
            with self.assertRaisesRegex(ValidationError, "stretches the screenshot aspect ratio"):
                self.validate(payload, root, project_root)

    def test_annotation_edges_and_rotation_must_be_calibrated(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload, _, _, project_root, _, _, _ = self.setup_review(root)
            for sample in payload["beats"][0]["annotations"][0]["samples"]:
                sample["overlay_points_px"] = [{"x": point["x"] + 8, "y": point["y"]}
                                                for point in sample["target_points_px"]]
            with self.assertRaises(HumanReviewRequired) as raised:
                self.validate(payload, root, project_root)
        issues = raised.exception.report["issues"]
        self.assertTrue(any(item.get("criterion") == "annotation_calibration" for item in issues))

    def test_all_animation_frames_must_have_annotation_measurements(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload, _, _, project_root, _, _, _ = self.setup_review(root)
            payload["beats"][0]["annotations"][0]["samples"] = [
                sample for sample in payload["beats"][0]["annotations"][0]["samples"]
                if payload["beats"][0]["frames"][[frame["id"] for frame in payload["beats"][0]["frames"]].index(sample["frame_id"])]["role"] != "motion_sample"]
            with self.assertRaisesRegex(ValidationError, "every sampled animation/transition/extremum frame"):
                self.validate(payload, root, project_root)

    def test_frame_evidence_pixels_must_match_the_video_at_its_timestamp(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload, _, _, project_root, _, _, _ = self.setup_review(root)
            with patch("voice_director.visual_quality._extract_video_rgb", side_effect=fake_video_frames), \
                    patch("voice_director.visual_quality._decode_image_rgb", return_value=b"different-rgb-pixels"):
                with self.assertRaisesRegex(ValidationError, "pixels do not match the specified frame"):
                    validate_visual_quality_review(payload, root, project_root, probe=VIDEO_PROBE)

    def test_failed_visual_polish_is_a_human_revision_packet(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload, _, _, project_root, _, _, _ = self.setup_review(root)
            payload["beats"][1]["criteria"]["clean_edges"]["status"] = "fail"
            payload["beats"][1]["criteria"]["clean_edges"]["evidence"] = "Text edges show visible aliasing at normal playback size."
            with self.assertRaises(HumanReviewRequired) as raised:
                self.validate(payload, root, project_root)
        self.assertEqual(raised.exception.report["status"], "AWAITING_HUMAN")
        self.assertTrue(any(item.get("criterion") == "clean_edges" for item in raised.exception.report["issues"]))

    def test_static_drift_and_jitter_fail_the_quality_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload, _, _, project_root, _, _, _ = self.setup_review(root)
            payload["beats"][0]["motion"]["static_hold_drift_px_at_1080p"] = 0.8
            payload["beats"][0]["motion"]["jitter_free"] = False
            with self.assertRaises(HumanReviewRequired) as raised:
                self.validate(payload, root, project_root)
        self.assertTrue(any(item.get("criterion") in {"static_hold_stability", "jitter_free"}
                            for item in raised.exception.report["issues"]))

    def test_zoom_and_pan_need_extremum_frames(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload, _, _, project_root, _, _, _ = self.setup_review(root)
            payload["beats"][0]["motion"]["effects"] = ["push_zoom"]
            with self.assertRaisesRegex(ValidationError, "at least two motion_extremum frames"):
                self.validate(payload, root, project_root)

    def test_final_video_requires_approved_sample_and_matching_project_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sample, sample_path, sample_hash, project_root, _, _, _ = self.setup_review(root)
            gate, gate_path, gate_hash = make_visual_gate(root, sample_path, sample_hash, decision="approved")
            final_video = make_video(root, "final.mp4")
            final, _, _, _, inventory, _, _ = make_quality_review(root, stage="final_video", video=final_video,
                                                                   gate_file=gate_path.name, gate_sha=gate_hash)
            with patch("voice_director.visual_quality._probe_video", return_value=VIDEO_PROBE), \
                    patch("voice_director.visual_quality._extract_video_rgb", side_effect=fake_video_frames), \
                    patch("voice_director.visual_quality._decode_image_rgb", side_effect=fake_image_pixels):
                report = self.validate(final, root, project_root)
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["stage"], "final_video")
            self.assertEqual(report["selected_option_id"], "1")
            changed = copy.deepcopy(final)
            changed["project_inventory"]["sha256"] = "0" * 64
            with self.assertRaisesRegex(ValidationError, "does not match the file"):
                self.validate(changed, root, project_root)

    def test_missing_project_file_hash_blocks_review(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload, _, _, project_root, _, _, _ = self.setup_review(root)
            (project_root / "composition.js").write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "does not match the project file"):
                self.validate(payload, root, project_root)

    def test_unlisted_render_input_blocks_project_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload, _, _, project_root, _, _, _ = self.setup_review(root)
            (project_root / "unlisted-overlay.js").write_text("export const overlay = true;", encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "must exactly match the project directory"):
                self.validate(payload, root, project_root)

    def test_entry_settled_and_exit_must_be_distinct_ordered_video_frames(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload, _, _, project_root, _, _, _ = self.setup_review(root)
            frames = payload["beats"][0]["frames"]
            settled = next(item for item in frames if item["role"] == "settled")
            exit_frame = next(item for item in frames if item["role"] == "exit")
            exit_frame["timestamp_seconds"] = settled["timestamp_seconds"]
            with self.assertRaisesRegex(ValidationError, "timestamps must be unique"):
                self.validate(payload, root, project_root)

    def test_cli_runs_review_and_emits_probe_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload, manifest_path, _, project_root, _, _, _ = self.setup_review(root)
            captured = io.StringIO()
            with patch("voice_director.visual_quality._probe_video", return_value=VIDEO_PROBE), \
                    patch("voice_director.visual_quality._extract_video_rgb", side_effect=fake_video_frames), \
                    patch("voice_director.visual_quality._decode_image_rgb", side_effect=fake_image_pixels), \
                    patch("sys.stdout", captured):
                status = main(["review-visual-quality", "--manifest", str(manifest_path), "--project-root", str(project_root)])
            output = json.loads(captured.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(output["gate"], "design_sample_quality_passed")
        self.assertEqual(output["probe"]["fps"], 30)


if __name__ == "__main__":
    unittest.main()
