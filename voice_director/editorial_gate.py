"""Deterministic validation and byte-exact release for narration review bundles."""

import csv
import hashlib
import json
import os
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from . import __version__
from .errors import HumanReviewRequired, OutputExistsError, ValidationError, VoiceDirectorError


FILES = (
    "source-evidence.txt",
    "source-map.csv",
    "draft.txt",
    "candidate.txt",
    "harness-review.json",
    "independent-review.json",
)
VERDICTS = (
    "extraction_coverage",
    "source_item_coverage",
    "factual_attribution_integrity",
    "spoken_delivery",
    "clean_copy_readiness",
    "unresolved_uncertainty",
)
STATUS = {"PASS", "NEEDS_REVISION", "INSUFFICIENT_EVIDENCE"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _json(data, filename):
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object,
                          parse_constant=lambda value: (_ for _ in ()).throw(
                              ValidationError(f"invalid JSON constant in {filename}: {value}")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"invalid UTF-8 JSON in {filename}: {exc}") from exc


def _keys(obj, required, label):
    if not isinstance(obj, dict) or set(obj) != set(required):
        raise ValidationError(f"{label} must contain exactly these keys: {', '.join(required)}")


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} must be a non-empty string")


def _string_list(value, label, allow_empty=False):
    if not isinstance(value, list) or (not allow_empty and not value):
        raise ValidationError(f"{label} must be {'a possibly empty' if allow_empty else 'a non-empty'} list")
    for item in value:
        _text(item, label + " item")
    if len(value) != len(set(value)):
        raise ValidationError(f"{label} must not contain duplicate IDs")


def _validate_map(data, filename):
    try:
        text = data.decode("utf-8-sig")
        rows = list(csv.DictReader(text.splitlines()))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ValidationError(f"{filename} is invalid UTF-8 CSV: {exc}") from exc
    required = ("source_item_id", "disposition", "candidate_reference")
    if not rows or not set(required).issubset(rows[0]):
        raise ValidationError(f"{filename} needs source_item_id, disposition, and candidate_reference columns with at least one row")
    item_ids = set()
    for index, row in enumerate(rows, 1):
        if any(not (row.get(key) or "").strip() for key in required):
            raise ValidationError(f"{filename} row {index} has an empty required field")
        if row["source_item_id"] in item_ids:
            raise ValidationError(f"{filename} row {index} duplicates source_item_id {row['source_item_id']}")
        item_ids.add(row["source_item_id"])


def _read_bundle(bundle):
    root = Path(bundle).resolve(strict=True)
    if not root.is_dir():
        raise ValidationError("bundle must be a directory")
    raw = {}
    for name in FILES:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValidationError(f"missing or unsafe bundle file: {name}")
        try:
            raw[name] = path.read_bytes()
        except OSError as exc:
            raise VoiceDirectorError(f"cannot read {path}: {exc}") from exc
    for name in ("source-evidence.txt", "draft.txt", "candidate.txt"):
        try:
            if not raw[name].decode("utf-8").strip():
                raise ValidationError(f"{name} must not be empty")
        except UnicodeDecodeError as exc:
            raise ValidationError(f"{name} is not valid UTF-8") from exc
    _validate_map(raw["source-map.csv"], "source-map.csv")
    maps = {_sha(raw["source-map.csv"]): raw["source-map.csv"]}
    history = root / "source-maps"
    if history.exists() or history.is_symlink():
        if history.is_symlink() or not history.is_dir():
            raise ValidationError("source-maps must be a real directory")
        for path in history.iterdir():
            if path.is_symlink() or not path.is_file() or not re.fullmatch(r"[0-9a-f]{64}\.csv", path.name):
                raise ValidationError("source-maps may contain only regular files named <sha256>.csv")
            data = path.read_bytes()
            if _sha(data) != path.stem:
                raise ValidationError(f"source map snapshot filename hash mismatch: {path.name}")
            _validate_map(data, "source-maps/" + path.name)
            maps[path.stem] = data
    return root, raw, set(maps)


def _validate_harness(data, hashes, map_hashes):
    doc = _json(data, "harness-review.json")
    _keys(doc, ("schema_version", "harness_id", "source_sha256", "map_sha256", "rounds"), "harness-review.json")
    if doc["schema_version"] != 1:
        raise ValidationError("unsupported harness-review schema_version")
    _text(doc["harness_id"], "harness_id")
    if doc["source_sha256"] != hashes["source"] or doc["map_sha256"] != hashes["map"]:
        raise ValidationError("harness review is stale for source evidence or source map")
    rounds = doc["rounds"]
    if not isinstance(rounds, list) or not rounds:
        raise ValidationError("harness-review.json must contain at least one round")
    known_rounds = set()
    prior_output = None
    addressed_reviews = set()
    for index, item in enumerate(rounds):
        label = f"harness round {index + 1}"
        _keys(item, ("round_id", "trigger", "source_sha256", "map_sha256", "input_sha256", "output_sha256", "assessment", "edits", "addressed_finding_ids", "resolved_finding_ids", "no_change_reason", "self_evaluation"), label)
        _text(item["round_id"], label + " round_id")
        if item["round_id"] in known_rounds:
            raise ValidationError("duplicate harness round_id")
        known_rounds.add(item["round_id"])
        if item["source_sha256"] != hashes["source"]:
            raise ValidationError(label + " is bound to a different source evidence file")
        if item["map_sha256"] not in map_hashes:
            raise ValidationError(label + " references a source-map hash without a retained map artifact")
        trigger = item["trigger"]
        if not isinstance(trigger, dict) or trigger.get("type") not in {"initial", "harness", "independent"}:
            raise ValidationError(label + " has invalid trigger")
        expected_trigger_keys = {"type", "review_id"} if trigger.get("type") == "independent" else {"type"}
        if set(trigger) != expected_trigger_keys:
            raise ValidationError(label + " trigger has unexpected or missing keys")
        if index == 0 and trigger["type"] != "initial":
            raise ValidationError("first harness round must have initial trigger")
        if index and trigger["type"] == "initial":
            raise ValidationError("only first harness round may have initial trigger")
        if trigger["type"] == "independent":
            _text(trigger.get("review_id"), label + " trigger review_id")
            addressed_reviews.add(trigger["review_id"])
        if item["input_sha256"] != (hashes["draft"] if index == 0 else prior_output):
            raise ValidationError(label + " input hash does not continue the draft/revision chain")
        if not isinstance(item["output_sha256"], str) or not SHA256_RE.fullmatch(item["output_sha256"]):
            raise ValidationError(label + " output_sha256 must be a SHA-256 hex digest")
        addressed = item["addressed_finding_ids"]
        resolved = item["resolved_finding_ids"]
        _string_list(addressed, label + " addressed_finding_ids", allow_empty=True)
        _string_list(resolved, label + " resolved_finding_ids", allow_empty=True)
        if not set(resolved).issubset(set(addressed)):
            raise ValidationError(label + " can resolve only finding IDs it addressed")
        assessment = item["assessment"]
        _keys(assessment, ("strengths", "issues"), label + " assessment")
        _string_list(assessment["strengths"], label + " strengths")
        issues = assessment["issues"]
        if not isinstance(issues, list):
            raise ValidationError(label + " issues must be a list")
        issue_ids = set()
        for issue in issues:
            _keys(issue, ("id", "description"), label + " issue")
            _text(issue["id"], label + " issue id")
            _text(issue["description"], label + " issue description")
            issue_ids.add(issue["id"])
        edits = item["edits"]
        if not isinstance(edits, list):
            raise ValidationError(label + " edits must be a list")
        edit_ids = set()
        for edit in edits:
            _keys(edit, ("finding_id", "change", "reason"), label + " edit")
            for key in ("finding_id", "change", "reason"):
                _text(edit[key], label + " edit " + key)
            edit_ids.add(edit["finding_id"])
        if edits:
            if item["no_change_reason"] is not None:
                raise ValidationError(label + " no_change_reason must be null when edits are recorded")
        else:
            _text(item["no_change_reason"], label + " no_change_reason")
            if item["output_sha256"] != item["input_sha256"]:
                raise ValidationError(label + " output must match input when no edits are recorded")
            if addressed and (not index or item["map_sha256"] == rounds[index - 1]["map_sha256"]):
                raise ValidationError(label + " evidence-only finding response must refresh the source map")
        if edits and item["output_sha256"] == item["input_sha256"]:
            raise ValidationError(label + " changed wording edits must produce changed candidate bytes")
        if not set(addressed).issubset(edit_ids) and (edits or trigger["type"] != "independent"):
            raise ValidationError(label + " must record an edit for every addressed finding unless it is an evidence-only independent-review repair")
        evaluation = item["self_evaluation"]
        _keys(evaluation, ("status", "dimensions", "findings"), label + " self_evaluation")
        if evaluation["status"] not in {"PASS", "NEEDS_REVISION"}:
            raise ValidationError(label + " self_evaluation status must be PASS or NEEDS_REVISION")
        if not isinstance(evaluation["dimensions"], dict) or not evaluation["dimensions"]:
            raise ValidationError(label + " self_evaluation dimensions must be a non-empty object")
        for key, value in evaluation["dimensions"].items():
            _text(key, label + " dimension")
            _text(value, label + " dimension evidence")
        findings = evaluation["findings"]
        if not isinstance(findings, list):
            raise ValidationError(label + " self-evaluation findings must be a list")
        for finding in findings:
            _keys(finding, ("id", "description"), label + " self-evaluation finding")
            _text(finding["id"], label + " finding id")
            _text(finding["description"], label + " finding description")
        if evaluation["status"] == "PASS" and (findings or not issue_ids.issubset(set(resolved))):
            raise ValidationError(label + " PASS requires all current findings to be resolved")
        if index:
            prior = rounds[index - 1]
            if edits and item["map_sha256"] == prior["map_sha256"]:
                raise ValidationError(label + " wording edits must refresh the source map")
            prior_eval = prior["self_evaluation"]
            if prior_eval["status"] == "NEEDS_REVISION":
                prior_pending = {f["id"] for f in prior_eval["findings"]}
                prior_pending |= {f["id"] for f in prior["assessment"]["issues"]} - set(prior["resolved_finding_ids"])
                if trigger["type"] != "harness":
                    raise ValidationError(label + " must continue the main-harness loop while self-evaluation needs revision")
                if not prior_pending.issubset(set(addressed)):
                    raise ValidationError(label + " must address every open prior finding")
                continuing = {f["id"] for f in findings}
                continuing |= {f["id"] for f in assessment["issues"]} - set(resolved)
                if not prior_pending.issubset(set(resolved) | continuing):
                    raise ValidationError(label + " must resolve or carry forward each prior finding")
        if evaluation["status"] == "NEEDS_REVISION" and not findings and not issue_ids:
            raise ValidationError(label + " NEEDS_REVISION must identify finding IDs")
        prior_output = item["output_sha256"]
    if rounds[-1]["output_sha256"] != hashes["candidate"]:
        raise ValidationError("last harness output does not match candidate.txt")
    if rounds[-1]["map_sha256"] != hashes["map"]:
        raise ValidationError("last harness round does not match source-map.csv")
    if rounds[-1]["self_evaluation"]["status"] != "PASS":
        raise ValidationError("final harness self-evaluation must PASS")
    if rounds[-1]["self_evaluation"]["findings"]:
        raise ValidationError("final harness self-evaluation must have no open findings")
    return doc["harness_id"], addressed_reviews


def _validate_independent(data, hashes, map_hashes, harness_id, addressed_reviews, rounds):
    doc = _json(data, "independent-review.json")
    _keys(doc, ("schema_version", "reviewer_id", "source_sha256", "map_sha256", "reviews"), "independent-review.json")
    if doc["schema_version"] not in {1, 2}:
        raise ValidationError("unsupported independent-review schema_version")
    _text(doc["reviewer_id"], "reviewer_id")
    if doc["reviewer_id"] == harness_id:
        raise ValidationError("independent reviewer must differ from harness identity")
    if doc["source_sha256"] != hashes["source"] or doc["map_sha256"] != hashes["map"]:
        raise ValidationError("independent review is stale for source evidence or source map")
    reviews = doc["reviews"]
    if not isinstance(reviews, list) or not reviews:
        raise ValidationError("independent-review.json must contain at least one review")
    ids = set()
    output_hashes = {item["output_sha256"] for item in rounds}
    trigger_to_round = {
        item["trigger"].get("review_id"): index
        for index, item in enumerate(rounds)
        if item["trigger"].get("type") == "independent"
    }
    if len(trigger_to_round) != sum(1 for item in rounds if item["trigger"]["type"] == "independent"):
        raise ValidationError("duplicate independent-review trigger in harness rounds")
    pending_external = set()
    failed_review_ids = set()
    last_review = None
    last_uncertainties = []
    for index, review in enumerate(reviews):
        label = f"independent review {index + 1}"
        review_keys = ("review_id", "source_sha256", "map_sha256", "candidate_sha256", "verdicts", "evidence", "findings", "resolves_finding_ids")
        has_typed_uncertainties = "uncertainties" in review
        if doc["schema_version"] == 1 and has_typed_uncertainties:
            raise ValidationError(label + " schema-v1 review cannot contain uncertainty fields")
        if doc["schema_version"] == 2 and has_typed_uncertainties:
            review_keys = (*review_keys, "uncertainties")
        _keys(review, review_keys, label)
        _text(review["review_id"], label + " review_id")
        if review["review_id"] in ids:
            raise ValidationError("duplicate independent review_id")
        ids.add(review["review_id"])
        if review["source_sha256"] != hashes["source"]:
            raise ValidationError(label + " source evidence hash is stale")
        if review["candidate_sha256"] not in output_hashes:
            raise ValidationError(label + " candidate hash does not match a harness output")
        matching_rounds = [r for r in rounds if r["output_sha256"] == review["candidate_sha256"] and r["map_sha256"] == review["map_sha256"]]
        if review["map_sha256"] not in map_hashes or not matching_rounds:
            raise ValidationError(label + " source-map hash does not match the reviewed candidate")
        verdicts = review["verdicts"]
        _keys(verdicts, VERDICTS, label + " verdicts")
        evidence = review["evidence"]
        _keys(evidence, VERDICTS, label + " evidence")
        for key in VERDICTS:
            if verdicts[key] not in STATUS:
                raise ValidationError(label + " has invalid verdict for " + key)
            _text(evidence[key], label + " evidence for " + key)
        findings = review["findings"]
        if not isinstance(findings, list):
            raise ValidationError(label + " findings must be a list")
        for finding in findings:
            _keys(finding, ("id", "description"), label + " finding")
            _text(finding["id"], label + " finding id")
            _text(finding["description"], label + " finding description")
        uncertainties = review.get("uncertainties", [])
        if not isinstance(uncertainties, list):
            raise ValidationError(label + " uncertainties must be a list")
        uncertainty_ids = set()
        assigned_findings = set()
        covered_dimensions = set()
        for uncertainty in uncertainties:
            _keys(uncertainty, ("id", "finding_ids", "dimensions", "source_reference", "candidate_reference", "observed_evidence", "question", "impact", "recommendation"), label + " uncertainty")
            _text(uncertainty["id"], label + " uncertainty id")
            if uncertainty["id"] in uncertainty_ids:
                raise ValidationError(label + " has duplicate uncertainty IDs")
            uncertainty_ids.add(uncertainty["id"])
            _string_list(uncertainty["finding_ids"], label + " uncertainty finding_ids")
            finding_ids = set(uncertainty["finding_ids"])
            known_finding_ids = {finding["id"] for finding in findings}
            if not finding_ids.issubset(known_finding_ids):
                raise ValidationError(label + " uncertainty references an unknown finding")
            if assigned_findings.intersection(finding_ids):
                raise ValidationError(label + " finding may belong to only one uncertainty")
            assigned_findings.update(finding_ids)
            _string_list(uncertainty["dimensions"], label + " uncertainty dimensions")
            for dimension in uncertainty["dimensions"]:
                if dimension not in VERDICTS or verdicts[dimension] != "INSUFFICIENT_EVIDENCE":
                    raise ValidationError(label + " uncertainty dimensions must identify INSUFFICIENT_EVIDENCE verdicts")
                covered_dimensions.add(dimension)
            for field in ("source_reference", "candidate_reference", "observed_evidence", "question", "impact", "recommendation"):
                _text(uncertainty[field], label + " uncertainty " + field)
        insufficient_dimensions = {key for key, value in verdicts.items() if value == "INSUFFICIENT_EVIDENCE"}
        if has_typed_uncertainties and covered_dimensions != insufficient_dimensions:
            raise ValidationError(label + " must describe every INSUFFICIENT_EVIDENCE verdict as a typed uncertainty")
        if uncertainties and assigned_findings != {finding["id"] for finding in findings}:
            raise ValidationError(label + " every finding must be associated with exactly one typed uncertainty")
        resolves = review["resolves_finding_ids"]
        _string_list(resolves, label + " resolves_finding_ids", allow_empty=True)
        failing_ids = {f["id"] for f in findings}
        if failing_ids.intersection(resolves):
            raise ValidationError(label + " cannot report and resolve the same finding")
        failing = any(v != "PASS" for v in verdicts.values())
        if failing and not findings:
            raise ValidationError(label + " non-passing review must identify findings")
        if not failing and findings:
            raise ValidationError(label + " passing review must have no open findings")
        if not set(resolves).issubset(pending_external):
            raise ValidationError(label + " resolves a finding that was not previously open")
        pending_external.difference_update(resolves)
        final_human_review = (
            index == len(reviews) - 1
            and doc["schema_version"] == 2
            and has_typed_uncertainties
            and bool(uncertainties)
            and all(value in {"PASS", "INSUFFICIENT_EVIDENCE"} for value in verdicts.values())
            and verdicts["spoken_delivery"] == "PASS"
            and verdicts["clean_copy_readiness"] == "PASS"
            and bool(assigned_findings)
        )
        if failing and not final_human_review:
            failed_review_ids.add(review["review_id"])
            if index == len(reviews) - 1:
                raise ValidationError("final independent review is non-passing")
            round_index = trigger_to_round.get(review["review_id"])
            if round_index is None or review["review_id"] not in addressed_reviews:
                raise ValidationError("a non-passing independent review has no following harness revision round")
            if round_index <= max(i for i, r in enumerate(rounds) if r["output_sha256"] == review["candidate_sha256"] and r["map_sha256"] == review["map_sha256"]):
                raise ValidationError("harness revision must follow the independent review of that candidate and map")
            if rounds[round_index]["input_sha256"] != review["candidate_sha256"]:
                raise ValidationError("harness revision after independent review does not use the reviewed candidate")
            if not set(f["id"] for f in findings).issubset(set(rounds[round_index]["addressed_finding_ids"])):
                raise ValidationError("harness revision does not address all independent-review findings")
            next_review = reviews[index + 1]
            if next_review["candidate_sha256"] == review["candidate_sha256"] and next_review["map_sha256"] == review["map_sha256"]:
                raise ValidationError("a non-passing independent review must be followed by changed candidate bytes or a refreshed source map")
            next_rounds = [i for i, r in enumerate(rounds) if r["output_sha256"] == next_review["candidate_sha256"] and r["map_sha256"] == next_review["map_sha256"]]
            if not next_rounds or max(next_rounds) < round_index:
                raise ValidationError("fresh independent review must follow the harness repair round")
            pending_external.update(failing_ids)
        if final_human_review:
            last_uncertainties = uncertainties
        last_review = review
    if set(trigger_to_round) != failed_review_ids:
        raise ValidationError("only a non-passing independent review may trigger a harness round")
    last_nonpass = {key for key, value in last_review["verdicts"].items() if value != "PASS"}
    if last_nonpass and not (last_uncertainties and all(last_review["verdicts"][key] == "INSUFFICIENT_EVIDENCE" for key in last_nonpass)):
        raise ValidationError("final independent review requires PASS on all six verdicts")
    if last_review["candidate_sha256"] != hashes["candidate"]:
        raise ValidationError("final independent review must match candidate.txt")
    if last_review["map_sha256"] != hashes["map"]:
        raise ValidationError("final independent review must match source-map.csv")
    if (last_review["findings"] and not last_uncertainties) or pending_external:
        raise ValidationError("final independent review leaves findings unresolved")
    return last_review["review_id"], len(reviews), last_review, last_uncertainties


def _decision_template(hashes, review_id, review_sha256, uncertainties):
    return {
        "schema_version": 1,
        "review_id": review_id,
        "source_sha256": hashes["source"],
        "map_sha256": hashes["map"],
        "candidate_sha256": hashes["candidate"],
        "independent_review_sha256": review_sha256,
        "decisions": [
            {
                "uncertainty_id": item["id"],
                "decision": None,
                "user_response": None,
                "user_response_reference": None,
                "decided_by": None,
                "decided_at": None,
            }
            for item in uncertainties
        ],
    }


def _validate_human_decisions(data, hashes, review_sha256, review_id, uncertainties):
    doc = _json(data, "human-decisions.json")
    _keys(doc, ("schema_version", "review_id", "source_sha256", "map_sha256", "candidate_sha256", "independent_review_sha256", "decisions"), "human-decisions.json")
    if doc["schema_version"] != 1:
        raise ValidationError("unsupported human-decisions schema_version")
    expected_hashes = {
        "source_sha256": hashes["source"], "map_sha256": hashes["map"],
        "candidate_sha256": hashes["candidate"], "independent_review_sha256": review_sha256,
    }
    if doc["review_id"] != review_id or any(doc[key] != value for key, value in expected_hashes.items()):
        raise ValidationError("human decisions are stale for the source, map, candidate, or independent review")
    decisions = doc["decisions"]
    if not isinstance(decisions, list):
        raise ValidationError("human-decisions decisions must be a list")
    by_id = {}
    for index, item in enumerate(decisions):
        label = f"human decision {index + 1}"
        _keys(item, ("uncertainty_id", "decision", "user_response", "user_response_reference", "decided_by", "decided_at"), label)
        for key in ("uncertainty_id", "decision", "user_response", "user_response_reference", "decided_by", "decided_at"):
            _text(item[key], label + " " + key)
        if item["uncertainty_id"] in by_id:
            raise ValidationError("duplicate human decision for uncertainty " + item["uncertainty_id"])
        if item["decision"] not in {"accept_as_is", "request_revision", "provide_evidence"}:
            raise ValidationError(label + " has an unsupported decision")
        try:
            datetime.fromisoformat(item["decided_at"].replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValidationError(label + " decided_at must be ISO-8601") from exc
        by_id[item["uncertainty_id"]] = item
    expected_ids = {item["id"] for item in uncertainties}
    if set(by_id) != expected_ids:
        raise ValidationError("human decisions must cover every current uncertainty exactly once")
    return by_id


def release(bundle, out, decisions=None):
    root, raw, map_hashes = _read_bundle(bundle)
    hashes = {
        "source": _sha(raw["source-evidence.txt"]),
        "map": _sha(raw["source-map.csv"]),
        "draft": _sha(raw["draft.txt"]),
        "candidate": _sha(raw["candidate.txt"]),
    }
    harness_id, addressed_reviews = _validate_harness(raw["harness-review.json"], hashes, map_hashes)
    harness_doc = _json(raw["harness-review.json"], "harness-review.json")
    review_id, review_count, final_review, uncertainties = _validate_independent(raw["independent-review.json"], hashes, map_hashes, harness_id, addressed_reviews, harness_doc["rounds"])
    accepted_uncertainty_ids = []
    decision_bytes = None
    review_sha256 = _sha(raw["independent-review.json"])
    if uncertainties:
        template = _decision_template(hashes, review_id, review_sha256, uncertainties)
        if not decisions:
            raise HumanReviewRequired({
                "status": "AWAITING_HUMAN",
                "candidate_path": str(root / "candidate.txt"),
                "uncertainties": uncertainties,
                "decision_options": [
                    {"value": "accept_as_is", "effect": "Release with a distinct human-decision status; the uncertainty remains disclosed."},
                    {"value": "request_revision", "effect": "Keep release blocked and revise the narration before a fresh independent review."},
                    {"value": "provide_evidence", "effect": "Keep release blocked until source evidence is added and independently reviewed."},
                ],
                "human_decisions_template": template,
                "instructions": "Review each uncertainty. Fill every decision with accept_as_is, request_revision, or provide_evidence; include your response, reference, name, and ISO-8601 time. Re-run editorial-gate with --decisions. No decision is assumed.",
            })
        raw_decision_path = Path(decisions)
        if raw_decision_path.is_symlink():
            raise ValidationError("human decisions must not be a symlink")
        decision_path = raw_decision_path.resolve(strict=True)
        if not decision_path.is_file() or decision_path.is_relative_to(root):
            raise ValidationError("human decisions must be a regular file outside the bundle")
        decision_bytes = decision_path.read_bytes()
        human = _validate_human_decisions(decision_bytes, hashes, review_sha256, review_id, uncertainties)
        rejected = [item["uncertainty_id"] for item in human.values() if item["decision"] != "accept_as_is"]
        if rejected:
            raise HumanReviewRequired({
                "status": "HUMAN_ACTION_REQUIRED",
                "uncertainty_ids": rejected,
                "message": "Revision or source evidence was requested. No narration was released; update the bundle and obtain a fresh independent review.",
            })
        accepted_uncertainty_ids = sorted(human)
    elif decisions:
        raise ValidationError("--decisions was supplied but the final review has no uncertainties")
    target = Path(out).resolve(strict=False)
    try:
        target.relative_to(root)
        raise ValidationError("output directory must be outside the input bundle")
    except ValueError:
        pass
    if target == root or root.is_relative_to(target):
        raise ValidationError("output path aliases the input bundle")
    if target.exists() or target.is_symlink():
        raise OutputExistsError(f"refusing to overwrite existing release directory: {target}")
    if not target.parent.exists() or not target.parent.is_dir():
        raise ValidationError("output parent directory must already exist")
    tmp = Path(tempfile.mkdtemp(prefix=".editorial-gate-", dir=target.parent))
    try:
        (tmp / "narration.txt").write_bytes(raw["candidate.txt"])
        independent_status = "INSUFFICIENT_EVIDENCE" if uncertainties else "PASS"
        receipt = {
            "schema_version": 1,
            "tool": "voice-director-editorial-gate",
            "tool_version": __version__,
            "input_sha256": hashes,
            "released_narration_sha256": hashes["candidate"],
            "harness_id": harness_id,
            "final_review_id": review_id,
            "harness_rounds": len(_json(raw["harness-review.json"], "harness-review.json")["rounds"]),
            "independent_reviews": review_count,
            "release_status": "RELEASED_WITH_HUMAN_DECISIONS" if accepted_uncertainty_ids else "RELEASED",
            "verdicts": {"harness_self_evaluation": "PASS", "independent_review": independent_status},
            "accepted_uncertainty_ids": accepted_uncertainty_ids,
            "human_decisions_sha256": _sha(decision_bytes) if decision_bytes is not None else None,
            "checks": ["bundle structure", "declared role distinction", "hash continuity", "review status linkage", "byte-exact release"],
            "limits": "This receipt does not prove semantic quality, review depth, source completeness, rights, reviewer identity, or model provenance.",
        }
        (tmp / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, target)
    except OSError as exc:
        raise VoiceDirectorError(f"failed to create atomic release at {target}: {exc}") from exc
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
    return {"status": "RELEASED_WITH_HUMAN_DECISIONS" if accepted_uncertainty_ids else "RELEASED", "output": str(target), "narration_sha256": hashes["candidate"], "final_review_id": review_id, "accepted_uncertainty_ids": accepted_uncertainty_ids}
