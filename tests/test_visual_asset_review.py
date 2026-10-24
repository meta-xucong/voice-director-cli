"""Tests for the Internet visual search and harness suitability gate."""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from voice_director.errors import HumanReviewRequired, ValidationError
from voice_director.visual_asset_review import validate_visual_asset_review


ROOT = Path(__file__).resolve().parents[1]
GOOD_PNG = b"\x89PNG\r\n\x1a\n" + b"fixture-pixels"


def beat_map():
    return {"schema_version": 1, "beats": [{
        "id": "B01", "duration_seconds": 8, "screen_text": "Codex desktop interface", "focus": "main panel",
        "transition": {"entry": "fade", "exit": "fade", "motion": "static"},
        "voice_mode": "summary", "narration": "先看界面里最关键的工作区。", "spoken_purpose": "Orient the learner.",
        "technical_display": False, "required_screen_terms": [], "screen_only_terms": [],
        "assets": [{"kind": "real_ui", "source": "Codex desktop screenshot", "authentic": True}],
    }]}


def fixture(root, *, with_candidate=True, query_count=1):
    narration = b"Start by looking at the workspace.\n"
    map_payload = beat_map()
    map_bytes = (json.dumps(map_payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    (root / "narration.txt").write_bytes(narration)
    (root / "voice-screen-map.json").write_bytes(map_bytes)
    search_queries = ["Codex desktop workspace screenshot", "site:openai.com Codex desktop interface", "Codex app workspace UI"]
    searches = [{"id": f"S{index + 1}", "query": search_queries[index], "query_type": ["exact", "official", "alternative"][index],
                 "engine": "image search", "searched_at": f"2026-10-24T10:0{index}:00+08:00", "beat_ids": ["B01"],
                 "candidate_ids": ["C01"] if with_candidate and index == 0 else []}
                for index in range(query_count)]
    candidates = []
    assessments = []
    if with_candidate:
        (root / "codex.png").write_bytes(GOOD_PNG)
        candidates = [{"id": "C01", "beat_ids": ["B01"], "title": "Codex desktop app", "origin": "internet", "source_url": "https://example.com/codex.png",
                       "source_description": "Official product page screenshot", "kind": "real_ui", "file": "codex.png",
                       "sha256": hashlib.sha256(GOOD_PNG).hexdigest(), "width": 1920, "height": 1080,
                       "rights_status": "official_terms", "rights_evidence": "Page links to official reuse terms.", "authentic": True}]
        criteria = {key: {"status": "pass", "evidence": f"Inspected image: {key} is suitable."}
                    for key in ("teaching_relevance", "visual_match", "legibility", "authenticity", "rights_and_provenance")}
        assessments = [{"candidate_id": "C01", "criteria": criteria}]
    review = {"harness_id": "main-harness", "reviewed_at": "2026-10-24T10:10:00+08:00",
              "narration_sha256": hashlib.sha256(narration).hexdigest(),
              "voice_screen_map_sha256": hashlib.sha256(map_bytes).hexdigest(),
              "summary": "The selected screenshot directly supports the beat.", "strengths": ["Exact desktop UI match."],
              "limitations": [], "overall_decision": "ready",
              "self_evaluation": {"status": "PASS", "dimensions": {"coverage": "All beats reviewed."}, "open_findings": []},
              "beats": [{"beat_id": "B01", "visual_need": "A readable genuine Codex desktop screenshot.", "requires_real_ui": True,
                         "search_ids": [item["id"] for item in searches], "candidate_assessments": assessments,
                         "decision": "use_candidate" if with_candidate else "ask_user_for_image",
                         "selected_candidate_id": "C01" if with_candidate else None,
                         "evidence": "The candidate shows the exact desktop workspace.", "learner_impact": "The image orients learners to the workspace.",
                         "image_request": None, "human_question": None, "human_recommendation": None}]}
    if not with_candidate:
        review["overall_decision"] = "needs_user_images"
        review["beats"][0].update({"evidence": "Three focused searches found no genuine, readable screenshot of this workspace.",
                                   "learner_impact": "Without a genuine screenshot, learners cannot identify the interface discussed.",
                                   "image_request": {"subject": "Codex desktop workspace", "must_show": ["full left navigation", "main workspace panel"],
                                                     "minimum_resolution": "1920x1080", "preferred_format": "PNG"}})
    return {"schema_version": 1, "narration_sha256": hashlib.sha256(narration).hexdigest(),
            "voice_screen_map_sha256": hashlib.sha256(map_bytes).hexdigest(), "searches": searches,
            "candidates": candidates, "harness_review": review}, narration, map_payload


class VisualAssetReviewTests(unittest.TestCase):
    def run_valid(self, root, payload, narration, voice_map):
        return validate_visual_asset_review(payload, root, hashlib.sha256(narration).hexdigest(),
                                            hashlib.sha256((json.dumps(voice_map, ensure_ascii=False, separators=(",", ":")) + "\n").encode()).hexdigest(),
                                            voice_map)

    def test_complete_search_and_harness_review_allows_visual_directions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload, narration, voice_map = fixture(root)
            report = self.run_valid(root, payload, narration, voice_map)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["selected_assets"], [{"beat_id": "B01", "candidate_id": "C01"}])

    def test_no_suitable_match_after_three_searches_displays_specific_image_request(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload, narration, voice_map = fixture(root, with_candidate=False, query_count=3)
            with self.assertRaises(HumanReviewRequired) as raised:
                self.run_valid(root, payload, narration, voice_map)
        packet = raised.exception.report
        self.assertEqual(packet["status"], "AWAITING_HUMAN")
        self.assertEqual(packet["items"][0]["image_request"]["subject"], "Codex desktop workspace")
        self.assertIn("learner_impact", packet["items"][0])

    def test_user_image_request_requires_three_distinct_queries(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload, narration, voice_map = fixture(root, with_candidate=False, query_count=1)
            with self.assertRaisesRegex(ValidationError, "at least three distinct"):
                self.run_valid(root, payload, narration, voice_map)

    def test_every_inspected_search_candidate_must_be_assessed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload, narration, voice_map = fixture(root)
            payload["harness_review"]["beats"][0]["candidate_assessments"] = []
            with self.assertRaisesRegex(ValidationError, "assess every inspected search candidate"):
                self.run_valid(root, payload, narration, voice_map)

    def test_harness_must_review_every_search_mapped_to_a_beat(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload, narration, voice_map = fixture(root, query_count=3)
            payload["harness_review"]["beats"][0]["search_ids"] = ["S1", "S2"]
            with self.assertRaisesRegex(ValidationError, "include every search recorded"):
                self.run_valid(root, payload, narration, voice_map)

    def test_user_provided_candidate_cannot_be_declared_as_search_result(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload, narration, voice_map = fixture(root)
            payload["candidates"][0]["origin"] = "user"
            payload["candidates"][0]["source_url"] = None
            payload["candidates"][0]["rights_status"] = "user_provided"
            with self.assertRaisesRegex(ValidationError, "cannot record user-provided candidate.*as an Internet result"):
                self.run_valid(root, payload, narration, voice_map)

    def test_search_and_candidate_beat_metadata_must_agree(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload, narration, voice_map = fixture(root)
            second = dict(voice_map["beats"][0])
            second["id"] = "B02"
            voice_map["beats"].append(second)
            map_hash = hashlib.sha256((json.dumps(voice_map, ensure_ascii=False, separators=(",", ":")) + "\n").encode()).hexdigest()
            payload["voice_screen_map_sha256"] = map_hash
            payload["harness_review"]["voice_screen_map_sha256"] = map_hash
            payload["searches"][0]["beat_ids"] = ["B01", "B02"]
            payload["candidates"][0]["beat_ids"] = ["B02"]
            with self.assertRaisesRegex(ValidationError, "does not cover all beats for search"):
                self.run_valid(root, payload, narration, voice_map)

    def test_candidate_with_unknown_rights_cannot_be_selected_as_adequate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload, narration, voice_map = fixture(root)
            payload["candidates"][0]["rights_status"] = "unknown"
            payload["harness_review"]["beats"][0]["candidate_assessments"][0]["criteria"]["rights_and_provenance"] = {
                "status": "partial", "evidence": "Reuse terms were not found."}
            with self.assertRaisesRegex(ValidationError, "passes every applicable criterion"):
                self.run_valid(root, payload, narration, voice_map)

    def test_real_ui_requirement_rejects_illustration_as_selected_screenshot(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload, narration, voice_map = fixture(root)
            payload["candidates"][0]["kind"] = "official_illustration"
            payload["candidates"][0]["authentic"] = None
            payload["harness_review"]["beats"][0]["candidate_assessments"][0]["criteria"]["authenticity"] = {
                "status": "fail", "evidence": "This is a product illustration, not an application screenshot."}
            with self.assertRaisesRegex(ValidationError, "passes every applicable criterion"):
                self.run_valid(root, payload, narration, voice_map)

    def test_user_provided_image_can_close_the_gap_after_review(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload, narration, voice_map = fixture(root, with_candidate=False, query_count=3)
            (root / "user-codex.png").write_bytes(GOOD_PNG)
            candidate = {"id": "U01", "beat_ids": ["B01"], "title": "User-provided Codex screenshot", "origin": "user",
                         "source_url": None, "source_description": "Provided by the user for this beat.", "kind": "real_ui",
                         "file": "user-codex.png", "sha256": hashlib.sha256(GOOD_PNG).hexdigest(), "width": 1920, "height": 1080,
                         "rights_status": "user_provided", "rights_evidence": "User supplied this image for the courseware.", "authentic": True}
            payload["candidates"].append(candidate)
            review = payload["harness_review"]["beats"][0]
            criteria = {key: {"status": "pass", "evidence": f"Inspected user image: {key} passes."}
                        for key in ("teaching_relevance", "visual_match", "legibility", "authenticity", "rights_and_provenance")}
            review.update({"candidate_assessments": [{"candidate_id": "U01", "criteria": criteria}],
                           "decision": "use_candidate", "selected_candidate_id": "U01", "image_request": None,
                           "evidence": "The supplied screenshot clearly shows the requested desktop workspace.",
                           "learner_impact": "Learners can now follow the interface explanation."})
            payload["harness_review"]["overall_decision"] = "ready"
            report = self.run_valid(root, payload, narration, voice_map)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["selected_assets"][0]["candidate_id"], "U01")

    def test_rights_uncertainty_is_a_human_decision_not_an_image_gap(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload, narration, voice_map = fixture(root)
            payload["candidates"][0]["rights_status"] = "unknown"
            review = payload["harness_review"]["beats"][0]
            review["candidate_assessments"][0]["criteria"]["rights_and_provenance"] = {
                "status": "partial", "evidence": "The source has no visible reuse terms."}
            review.update({"decision": "needs_human_decision", "selected_candidate_id": None,
                           "human_question": "May this image be used if we credit its source?",
                           "human_recommendation": "Confirm permission or choose a user-provided screenshot.",
                           "image_request": None, "evidence": "No reuse terms were located on the source page."})
            payload["harness_review"]["overall_decision"] = "needs_human_decision"
            with self.assertRaises(HumanReviewRequired) as raised:
                self.run_valid(root, payload, narration, voice_map)
        self.assertEqual(raised.exception.report["decision"], "needs_human_decision")
        self.assertIn("May this image be used", raised.exception.report["items"][0]["question"])

    def test_stale_narration_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload, narration, voice_map = fixture(root)
            payload["narration_sha256"] = "0" * 64
            with self.assertRaisesRegex(ValidationError, "does not match the supplied narration"):
                self.run_valid(root, payload, narration, voice_map)

    def test_request_packet_uses_cli_awaiting_human_exit_code(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload, narration, voice_map = fixture(root, with_candidate=False, query_count=3)
            (root / "visual-asset-review.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            (root / "voice-screen-map.json").write_bytes((json.dumps(voice_map, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
            result = subprocess.run([sys.executable, "-m", "voice_director", "review-visual-assets", "--manifest",
                                     str(root / "visual-asset-review.json"), "--narration", str(root / "narration.txt"),
                                     "--map", str(root / "voice-screen-map.json")], cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        packet = json.loads(result.stdout)
        self.assertEqual(packet["gate"], "visual_asset_review")
        self.assertEqual(packet["items"][0]["image_request"]["preferred_format"], "PNG")


if __name__ == "__main__":
    unittest.main()
