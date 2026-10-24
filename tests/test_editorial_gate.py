"""Offline tests for the hash-bound narration release gate."""

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from voice_director.cli import main
from voice_director.errors import OutputExistsError, ValidationError


VERDICTS = (
    "extraction_coverage", "source_item_coverage", "factual_attribution_integrity",
    "spoken_delivery", "clean_copy_readiness", "unresolved_uncertainty",
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def review(review_id, candidate_hash, status="PASS", finding_id=None):
    verdicts = {key: "PASS" for key in VERDICTS}
    if status != "PASS":
        verdicts["spoken_delivery"] = status
    return {
        "review_id": review_id,
        "source_sha256": "SOURCE_PLACEHOLDER",
        "map_sha256": "MAP_PLACEHOLDER",
        "candidate_sha256": candidate_hash,
        "verdicts": verdicts,
        "evidence": {key: "Checked against complete source evidence and map." for key in VERDICTS},
        "findings": ([{"id": finding_id, "description": "A specific listener-facing issue remains."}] if finding_id else []),
        "resolves_finding_ids": [],
    }


class EditorialGateTests(unittest.TestCase):
    def _bundle(self, root, mode="valid"):
        root.mkdir()
        source = "source evidence\n".encode()
        original_map = b"source_item_id,disposition,candidate_reference\nS1,retained,P1\n"
        source_map = b"source_item_id,disposition,candidate_reference\nS1,retained,P1-P2\n"
        draft = b"Draft narration.\n"
        intermediate = b"First revision.\n"
        final = b"Final narration with revised cadence.\r\n"
        for name, data in (("source-evidence.txt", source), ("source-map.csv", source_map),
                           ("draft.txt", draft), ("candidate.txt", final)):
            (root / name).write_bytes(data)
        source_hash, old_map_hash, map_hash = digest(source), digest(original_map), digest(source_map)
        history = root / "source-maps"
        history.mkdir()
        (history / (old_map_hash + ".csv")).write_bytes(original_map)
        rounds = [
            {
                "round_id": "H1", "trigger": {"type": "initial"},
                "source_sha256": source_hash, "map_sha256": old_map_hash,
                "input_sha256": digest(draft), "output_sha256": digest(intermediate),
                "assessment": {"strengths": ["Clear core explanation."], "issues": [{"id": "L1", "description": "Opening sentence is dense."}]},
                "edits": [{"finding_id": "L1", "change": "Shorten the opening clause.", "reason": "Reduces its initial density."}],
                "addressed_finding_ids": ["L1"], "resolved_finding_ids": [], "no_change_reason": None,
                "self_evaluation": {"status": "NEEDS_REVISION", "dimensions": {"spoken_delivery": "Opening is still dense."}, "findings": [{"id": "L1", "description": "Split the opening thought."}]},
            },
            {
                "round_id": "H2", "trigger": {"type": "harness"},
                "source_sha256": source_hash, "map_sha256": map_hash,
                "input_sha256": digest(intermediate), "output_sha256": digest(final),
                "assessment": {"strengths": ["Clearer spoken cadence."], "issues": []},
                "edits": [{"finding_id": "L1", "change": "Split the first sentence.", "reason": "Gives listeners a pause."}],
                "addressed_finding_ids": ["L1"], "resolved_finding_ids": ["L1"], "no_change_reason": None,
                "self_evaluation": {"status": "PASS", "dimensions": {"spoken_delivery": "Natural pacing and clear transitions."}, "findings": []},
            },
        ]
        independent_reviews = [review("R1", digest(final))]
        if mode == "map_history":
            independent_reviews = [review("R0", digest(intermediate)), review("R1", digest(final))]
            independent_reviews[0]["map_sha256"] = old_map_hash
        elif mode == "independent_evidence_revision":
            mid_map = source_map
            new_map = b"source_item_id,disposition,candidate_reference\nS1,retained,P1-P3\n"
            mid_map_hash, new_map_hash = digest(mid_map), digest(new_map)
            (history / (mid_map_hash + ".csv")).write_bytes(mid_map)
            (root / "source-map.csv").write_bytes(new_map)
            rounds[1]["map_sha256"] = mid_map_hash
            rounds.append({
                "round_id": "H3", "trigger": {"type": "independent", "review_id": "IR1"},
                "source_sha256": source_hash, "map_sha256": new_map_hash,
                "input_sha256": digest(final), "output_sha256": digest(final),
                "assessment": {"strengths": ["Narration remains accurate."], "issues": []},
                "edits": [], "addressed_finding_ids": ["R1F"], "resolved_finding_ids": [],
                "no_change_reason": "The finding concerned the source map; narration was already accurate.",
                "self_evaluation": {"status": "PASS", "dimensions": {"spoken_delivery": "No wording change was needed."}, "findings": []},
            })
            independent_reviews = [review("IR1", digest(final), "NEEDS_REVISION", "R1F"), review("IR2", digest(final))]
            independent_reviews[0]["map_sha256"] = mid_map_hash
            independent_reviews[1]["map_sha256"] = new_map_hash
            independent_reviews[1]["resolves_finding_ids"] = ["R1F"]
        if mode == "independent_revision":
            pre_review = b"Candidate before external review.\n"
            changed = b"Final narration after independent finding.\n"
            final_map = b"source_item_id,disposition,candidate_reference\nS1,retained,P1-P3\n"
            final_map_hash = digest(final_map)
            (history / (map_hash + ".csv")).write_bytes(source_map)
            (root / "source-map.csv").write_bytes(final_map)
            final = changed
            (root / "candidate.txt").write_bytes(changed)
            rounds[1]["output_sha256"] = digest(pre_review)
            rounds[1]["edits"] = [{"finding_id": "L1", "change": "Split the first sentence.", "reason": "Gives listeners a pause."}]
            rounds[1]["resolved_finding_ids"] = ["L1"]
            rounds[2:] = [{
                "round_id": "H3", "trigger": {"type": "independent", "review_id": "IR1"},
                "input_sha256": digest(pre_review), "output_sha256": digest(changed),
                "assessment": {"strengths": ["Result is stated first."], "issues": []},
                "edits": [{"finding_id": "R1F", "change": "Move the outcome before the tool name.", "reason": "Resolves the reviewer finding."}],
                "addressed_finding_ids": ["R1F"], "resolved_finding_ids": [], "no_change_reason": None,
                "self_evaluation": {"status": "PASS", "dimensions": {"spoken_delivery": "The setup now leads with the result."}, "findings": []},
            }]
            independent_reviews = [review("IR1", digest(pre_review), "NEEDS_REVISION", "R1F"), review("IR2", digest(changed))]
            independent_reviews[0]["map_sha256"] = map_hash
            independent_reviews[-1]["map_sha256"] = final_map_hash
            independent_reviews[-1]["resolves_finding_ids"] = ["R1F"]
            rounds[2]["source_sha256"] = source_hash
            rounds[2]["map_sha256"] = final_map_hash
        if mode == "human_uncertainty":
            independent_reviews[0]["verdicts"]["extraction_coverage"] = "INSUFFICIENT_EVIDENCE"
            independent_reviews[0]["verdicts"]["unresolved_uncertainty"] = "INSUFFICIENT_EVIDENCE"
            independent_reviews[0]["findings"] = [{"id": "U-FIGURE", "description": "A figure contains unreadable source text."}]
            independent_reviews[0]["uncertainties"] = [{
                "id": "U1", "finding_ids": ["U-FIGURE"],
                "dimensions": ["extraction_coverage", "unresolved_uncertainty"],
                "source_reference": "Figure 3, image pixels",
                "candidate_reference": "Paragraph 3",
                "observed_evidence": "The figure caption is visible; embedded text was not read.",
                "question": "Does the figure contain a separate lesson point that should be narrated?",
                "impact": "An untranscribed label may be absent from the script.",
                "recommendation": "Inspect the figure before deciding whether to accept the current copy, revise, or add evidence.",
            }]
        final_map_hash = digest((root / "source-map.csv").read_bytes())
        harness = {"schema_version": 1, "harness_id": "main-harness", "source_sha256": source_hash,
                   "map_sha256": final_map_hash, "rounds": rounds}
        for item in independent_reviews:
            item["source_sha256"] = source_hash
            if item["map_sha256"] == "MAP_PLACEHOLDER":
                item["map_sha256"] = final_map_hash
        independent = {"schema_version": 1, "reviewer_id": "read-only-reviewer", "source_sha256": source_hash,
                       "map_sha256": final_map_hash, "reviews": independent_reviews}
        if mode == "human_uncertainty":
            independent["schema_version"] = 2
        (root / "harness-review.json").write_text(json.dumps(harness), encoding="utf-8")
        (root / "independent-review.json").write_text(json.dumps(independent), encoding="utf-8")
        return final

    def _run(self, bundle, out, decisions=None):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            argv = ["editorial-gate", "--bundle", str(bundle), "--out", str(out)]
            if decisions is not None:
                argv.extend(["--decisions", str(decisions)])
            code = main(argv)
        return code, stdout.getvalue() + stderr.getvalue()

    def _human_decisions(self, bundle, decision="accept_as_is"):
        independent_raw = (bundle / "independent-review.json").read_bytes()
        independent = json.loads(independent_raw)
        final = independent["reviews"][-1]
        source_hash = digest((bundle / "source-evidence.txt").read_bytes())
        map_hash = digest((bundle / "source-map.csv").read_bytes())
        candidate_hash = digest((bundle / "candidate.txt").read_bytes())
        path = bundle.parent / "human-decisions.json"
        path.write_text(json.dumps({
            "schema_version": 1,
            "review_id": final["review_id"],
            "source_sha256": source_hash,
            "map_sha256": map_hash,
            "candidate_sha256": candidate_hash,
            "independent_review_sha256": digest(independent_raw),
            "decisions": [{
                "uncertainty_id": "U1", "decision": decision,
                "user_response": "I reviewed the stated limitation and chose this disposition.",
                "user_response_reference": "User response in review conversation",
                "decided_by": "user", "decided_at": "2026-10-23T18:00:00+08:00",
            }],
        }), encoding="utf-8")
        return path

    def test_releases_exact_candidate_bytes_and_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "bundle"
            candidate = self._bundle(bundle)
            out = root / "release"
            code, stdout = self._run(bundle, out)
            self.assertEqual(code, 0, stdout)
            self.assertEqual((out / "narration.txt").read_bytes(), candidate)
            receipt = json.loads((out / "receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["tool_version"], "1.0.0")
            self.assertEqual(receipt["released_narration_sha256"], digest(candidate))

    def test_uncertainty_is_displayed_and_never_implicitly_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "bundle"
            self._bundle(bundle, "human_uncertainty")
            out = root / "release"
            code, stdout = self._run(bundle, out)
            packet = json.loads(stdout)
            self.assertEqual(code, 3)
            self.assertEqual(packet["status"], "AWAITING_HUMAN")
            self.assertEqual(packet["uncertainties"][0]["question"], "Does the figure contain a separate lesson point that should be narrated?")
            self.assertEqual(packet["human_decisions_template"]["decisions"][0]["decision"], None)
            self.assertFalse(out.exists())

    def test_explicit_human_acceptance_preserves_nonpass_review_verdict(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "bundle"
            candidate = self._bundle(bundle, "human_uncertainty")
            decisions = self._human_decisions(bundle)
            out = root / "release"
            code, stdout = self._run(bundle, out, decisions)
            report = json.loads(stdout)
            self.assertEqual(code, 0, stdout)
            self.assertEqual(report["status"], "RELEASED_WITH_HUMAN_DECISIONS")
            self.assertEqual((out / "narration.txt").read_bytes(), candidate)
            receipt = json.loads((out / "receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["verdicts"]["independent_review"], "INSUFFICIENT_EVIDENCE")
            self.assertEqual(receipt["accepted_uncertainty_ids"], ["U1"])
            self.assertTrue(receipt["human_decisions_sha256"])

    def test_human_revision_or_evidence_choice_still_blocks_release(self):
        for decision in ("request_revision", "provide_evidence"):
            with self.subTest(decision=decision), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                bundle = root / "bundle"
                self._bundle(bundle, "human_uncertainty")
                decisions = self._human_decisions(bundle, decision)
                out = root / "release"
                code, stdout = self._run(bundle, out, decisions)
                self.assertEqual(code, 3)
                self.assertEqual(json.loads(stdout)["status"], "HUMAN_ACTION_REQUIRED")
                self.assertFalse(out.exists())

    def test_human_decision_hashes_are_invalidated_by_review_byte_change(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "bundle"
            self._bundle(bundle, "human_uncertainty")
            decisions = self._human_decisions(bundle)
            with (bundle / "independent-review.json").open("ab") as stream:
                stream.write(b"\n")
            code, stdout = self._run(bundle, root / "release", decisions)
            self.assertEqual(code, 2)
            self.assertIn("stale for the source, map, candidate, or independent review", stdout)
            self.assertFalse((root / "release").exists())

    def test_failed_independent_review_requires_revision_and_fresh_review(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "bundle"
            candidate = self._bundle(bundle, "independent_revision")
            code, stdout = self._run(bundle, root / "release")
            self.assertEqual(code, 0, stdout)
            self.assertEqual((root / "release" / "narration.txt").read_bytes(), candidate)

    def test_reviews_can_bind_retained_source_map_versions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "bundle"
            self._bundle(bundle, "map_history")
            code, stdout = self._run(bundle, root / "release")
            self.assertEqual(code, 0, stdout)

    def test_final_review_must_bind_current_source_map(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "bundle"
            self._bundle(bundle)
            source_map = bundle / "source-map.csv"
            old_map = source_map.read_bytes()
            old_hash = digest(old_map)
            (bundle / "source-maps" / (old_hash + ".csv")).write_bytes(old_map)
            new_map = b"source_item_id,disposition,candidate_reference\nS1,retained,P1-P3\n"
            source_map.write_bytes(new_map)
            new_hash = digest(new_map)

            harness_path = bundle / "harness-review.json"
            harness = json.loads(harness_path.read_text(encoding="utf-8"))
            harness["map_sha256"] = new_hash
            harness["rounds"].append({
                "round_id": "H3", "trigger": {"type": "harness"},
                "source_sha256": digest((bundle / "source-evidence.txt").read_bytes()),
                "map_sha256": new_hash,
                "input_sha256": digest((bundle / "candidate.txt").read_bytes()),
                "output_sha256": digest((bundle / "candidate.txt").read_bytes()),
                "assessment": {"strengths": ["Narration remains aligned."], "issues": []},
                "edits": [], "addressed_finding_ids": [], "resolved_finding_ids": [],
                "no_change_reason": "Only the source map was refreshed; narration remains unchanged.",
                "self_evaluation": {"status": "PASS", "dimensions": {"source_map": "Current source map recorded."}, "findings": []},
            })
            harness_path.write_text(json.dumps(harness), encoding="utf-8")

            review_path = bundle / "independent-review.json"
            independent = json.loads(review_path.read_text(encoding="utf-8"))
            independent["map_sha256"] = new_hash
            independent["reviews"][-1]["map_sha256"] = old_hash
            review_path.write_text(json.dumps(independent), encoding="utf-8")

            out = root / "release"
            code, stdout = self._run(bundle, out)
            self.assertEqual(code, 2)
            self.assertIn("final independent review must match source-map.csv", stdout)
            self.assertFalse(out.exists())

    def test_wording_edit_requires_refreshed_source_map(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "bundle"
            self._bundle(bundle)
            harness_path = bundle / "harness-review.json"
            harness = json.loads(harness_path.read_text(encoding="utf-8"))
            harness["rounds"][1]["map_sha256"] = harness["rounds"][0]["map_sha256"]
            harness_path.write_text(json.dumps(harness), encoding="utf-8")
            code, stdout = self._run(bundle, root / "release")
            self.assertEqual(code, 2)
            self.assertIn("wording edits must refresh the source map", stdout)
            self.assertFalse((root / "release").exists())

    def test_independent_evidence_only_finding_can_revise_map_without_text_change(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "bundle"
            candidate = self._bundle(bundle, "independent_evidence_revision")
            code, stdout = self._run(bundle, root / "release")
            self.assertEqual(code, 0, stdout)
            self.assertEqual((root / "release" / "narration.txt").read_bytes(), candidate)

    def test_stale_candidate_blocks_release(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "bundle"
            self._bundle(bundle)
            (bundle / "candidate.txt").write_bytes(b"Tampered candidate\n")
            code, stdout = self._run(bundle, root / "release")
            self.assertEqual(code, 2)
            self.assertFalse((root / "release").exists())
            self.assertIn("last harness output", stdout)

    def test_same_reviewer_and_harness_identity_blocks_release(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "bundle"
            self._bundle(bundle)
            path = bundle / "independent-review.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["reviewer_id"] = "main-harness"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "must differ"):
                from voice_director.editorial_gate import release
                release(bundle, root / "release")

    def test_unresolved_harness_finding_blocks_release(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "bundle"
            self._bundle(bundle)
            path = bundle / "harness-review.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["rounds"][1]["resolved_finding_ids"] = []
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "resolve or carry forward"):
                from voice_director.editorial_gate import release
                release(bundle, root / "release")

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "bundle"
            self._bundle(bundle)
            (bundle / "harness-review.json").write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "duplicate JSON key"):
                from voice_director.editorial_gate import release
                release(bundle, root / "release")

    def test_existing_output_directory_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "bundle"
            self._bundle(bundle)
            out = root / "release"
            out.mkdir()
            with self.assertRaises(OutputExistsError):
                from voice_director.editorial_gate import release
                release(bundle, out)

    def test_output_inside_bundle_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "bundle"
            self._bundle(bundle)
            with self.assertRaisesRegex(ValidationError, "outside the input bundle"):
                from voice_director.editorial_gate import release
                release(bundle, bundle / "release")

    def test_invalid_utf8_candidate_blocked_without_partial_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "bundle"
            self._bundle(bundle)
            (bundle / "candidate.txt").write_bytes(b"\xff")
            out = root / "release"
            with self.assertRaisesRegex(ValidationError, "valid UTF-8"):
                from voice_director.editorial_gate import release
                release(bundle, out)
            self.assertFalse(out.exists())

    def test_stale_source_and_source_map_are_rejected(self):
        for changed_file in ("source-evidence.txt", "source-map.csv"):
            with self.subTest(changed_file=changed_file), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                bundle = root / "bundle"
                self._bundle(bundle)
                with (bundle / changed_file).open("ab") as stream:
                    stream.write(b"changed")
                with self.assertRaises(ValidationError):
                    from voice_director.editorial_gate import release
                    release(bundle, root / "release")
                self.assertFalse((root / "release").exists())

    def test_final_self_evaluation_must_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "bundle"
            self._bundle(bundle)
            path = bundle / "harness-review.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["rounds"][-1]["self_evaluation"]["status"] = "NEEDS_REVISION"
            data["rounds"][-1]["self_evaluation"]["findings"] = [{"id": "last", "description": "Still needs work."}]
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "final harness self-evaluation"):
                from voice_director.editorial_gate import release
                release(bundle, root / "release")

    def test_each_final_independent_verdict_must_pass(self):
        for verdict in VERDICTS:
            with self.subTest(verdict=verdict), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                bundle = root / "bundle"
                self._bundle(bundle)
                path = bundle / "independent-review.json"
                data = json.loads(path.read_text(encoding="utf-8"))
                data["reviews"][-1]["verdicts"][verdict] = "NEEDS_REVISION"
                data["reviews"][-1]["findings"] = [{"id": "final", "description": "Needs another review."}]
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaisesRegex(ValidationError, "final independent review is non-passing"):
                    from voice_director.editorial_gate import release
                    release(bundle, root / "release")

    def test_missing_bundle_file_blocks_without_partial_release(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "bundle"
            self._bundle(bundle)
            (bundle / "source-map.csv").unlink()
            out = root / "release"
            with self.assertRaisesRegex(ValidationError, "missing or unsafe"):
                from voice_director.editorial_gate import release
                release(bundle, out)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
