"""Validate the private search and harness review for courseware visual assets."""

import hashlib
import re
from datetime import datetime
from pathlib import Path

from .errors import HumanReviewRequired, ValidationError
from .schema import read_json, read_script
from .voice_screen import validate_voice_screen_map


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IMAGE_SIGNATURES = {
    ".png": lambda data: data.startswith(b"\x89PNG\r\n\x1a\n"),
    ".jpg": lambda data: data.startswith(b"\xff\xd8\xff"),
    ".jpeg": lambda data: data.startswith(b"\xff\xd8\xff"),
    ".webp": lambda data: len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP",
}
_RIGHTS = {"user_provided", "licensed", "public_domain", "cc0", "cc_by", "cc_by_sa", "official_terms", "unknown"}
_KINDS = {"real_ui", "official_illustration", "original_graphic", "photo", "other"}
_CRITERIA = {"teaching_relevance", "visual_match", "legibility", "authenticity", "rights_and_provenance"}
_STATUSES = {"pass", "partial", "fail", "not_applicable"}


def _object(value, label, keys):
    if not isinstance(value, dict):
        raise ValidationError(f"{label} must be an object")
    missing = keys - value.keys()
    extra = value.keys() - keys
    if missing or extra:
        parts = []
        if missing:
            parts.append("missing " + ", ".join(sorted(missing)))
        if extra:
            parts.append("unknown " + ", ".join(sorted(extra)))
        raise ValidationError(f"{label}: " + "; ".join(parts))


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} must be a non-empty string")


def _string_list(value, label, *, nonempty=True):
    if not isinstance(value, list) or (nonempty and not value):
        raise ValidationError(f"{label} must be " + ("a non-empty array" if nonempty else "an array"))
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValidationError(f"{label} must contain only non-empty strings")
    if len(set(value)) != len(value):
        raise ValidationError(f"{label} must not contain duplicates")
    return value


def _timestamp(value, label):
    _text(value, label)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValidationError(f"{label} must include a timezone")
    return parsed


def _safe_image(base_dir, candidate):
    relative = candidate["file"]
    if not isinstance(relative, str) or not relative.strip():
        raise ValidationError(f"candidate {candidate['id']}.file must be a relative path in the private run directory")
    path_part = Path(relative)
    if path_part.is_absolute() or ".." in path_part.parts:
        raise ValidationError(f"candidate {candidate['id']}.file must stay inside the private run directory")
    path = (base_dir / path_part).resolve()
    root = base_dir.resolve()
    if root not in path.parents or not path.is_file():
        raise ValidationError(f"candidate {candidate['id']}.file must resolve to a file inside the private run directory")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ValidationError(f"candidate {candidate['id']}.file cannot be read: {exc}") from exc
    signature = _IMAGE_SIGNATURES.get(path.suffix.lower())
    if signature is None or not signature(data):
        raise ValidationError(f"candidate {candidate['id']}.file must be a PNG, JPEG, or WebP with a matching signature")
    if hashlib.sha256(data).hexdigest() != candidate["sha256"]:
        raise ValidationError(f"candidate {candidate['id']}.file SHA-256 does not match")


def _candidate_is_adequate(candidate, assessment, requires_real_ui):
    criteria = assessment["criteria"]
    if any(criteria[key]["status"] not in {"pass", "not_applicable"} for key in _CRITERIA):
        return False
    if criteria["teaching_relevance"]["status"] != "pass" or criteria["visual_match"]["status"] != "pass" or criteria["legibility"]["status"] != "pass":
        return False
    if criteria["rights_and_provenance"]["status"] != "pass" or candidate["rights_status"] == "unknown":
        return False
    if requires_real_ui and (candidate["kind"] != "real_ui" or criteria["authenticity"]["status"] != "pass" or candidate["authentic"] is not True):
        return False
    if not requires_real_ui and criteria["authenticity"]["status"] not in {"pass", "not_applicable"}:
        return False
    return True


def validate_visual_asset_review(payload, base_dir, narration_sha256, voice_screen_map_sha256, voice_screen_map):
    """Check evidence completeness and return PASS or a concrete human-review packet.

    This gate verifies declared evidence and hash continuity. It cannot perform web
    search or establish that the harness's semantic judgments are correct.
    """
    root_keys = {"schema_version", "narration_sha256", "voice_screen_map_sha256", "searches", "candidates", "harness_review"}
    _object(payload, "visual asset review manifest", root_keys)
    if payload["schema_version"] != 1:
        raise ValidationError("visual asset review schema_version must be 1")
    if payload["narration_sha256"] != narration_sha256:
        raise ValidationError("manifest narration_sha256 does not match the supplied narration")
    if payload["voice_screen_map_sha256"] != voice_screen_map_sha256:
        raise ValidationError("manifest voice_screen_map_sha256 does not match the supplied voice-screen map")

    beats = voice_screen_map.get("beats")
    beat_ids = {beat["id"] for beat in beats}
    searches = payload["searches"]
    if not isinstance(searches, list) or not searches:
        raise ValidationError("searches must be a non-empty array; Internet search evidence is required before review")
    search_ids = set()
    search_by_id = {}
    queries_by_beat = {beat_id: [] for beat_id in beat_ids}
    candidates_from_search_by_beat = {beat_id: set() for beat_id in beat_ids}
    for index, search in enumerate(searches, 1):
        label = f"searches[{index}]"
        _object(search, label, {"id", "query", "query_type", "engine", "searched_at", "beat_ids", "candidate_ids"})
        _text(search["id"], f"{label}.id")
        if search["id"] in search_ids:
            raise ValidationError(f"duplicate search id: {search['id']}")
        search_ids.add(search["id"])
        _text(search["query"], f"{label}.query")
        if search["query_type"] not in {"exact", "official", "alternative"}:
            raise ValidationError(f"{label}.query_type must be exact, official, or alternative")
        _text(search["engine"], f"{label}.engine")
        _timestamp(search["searched_at"], f"{label}.searched_at")
        covered_beats = _string_list(search["beat_ids"], f"{label}.beat_ids")
        result_ids = _string_list(search["candidate_ids"], f"{label}.candidate_ids", nonempty=False)
        unknown_beats = set(covered_beats) - beat_ids
        if unknown_beats:
            raise ValidationError(f"{label}.beat_ids references unknown beat(s): {', '.join(sorted(unknown_beats))}")
        search_by_id[search["id"]] = search
        for beat_id in covered_beats:
            queries_by_beat[beat_id].append(search["query"])
            candidates_from_search_by_beat[beat_id].update(result_ids)
    for beat_id, beat_queries in queries_by_beat.items():
        if not beat_queries:
            raise ValidationError(f"beat {beat_id} has no Internet image search evidence")

    candidates = payload["candidates"]
    if not isinstance(candidates, list):
        raise ValidationError("candidates must be an array")
    candidate_by_id = {}
    for index, candidate in enumerate(candidates, 1):
        label = f"candidates[{index}]"
        _object(candidate, label, {"id", "beat_ids", "title", "origin", "source_url", "source_description", "kind", "file", "sha256", "width", "height", "rights_status", "rights_evidence", "authentic"})
        for key in ("id", "title", "source_description", "rights_evidence"):
            _text(candidate[key], f"{label}.{key}")
        candidate_beats = _string_list(candidate["beat_ids"], f"{label}.beat_ids")
        if set(candidate_beats) - beat_ids:
            raise ValidationError(f"{label}.beat_ids references unknown beat(s)")
        if candidate["id"] in candidate_by_id:
            raise ValidationError(f"duplicate candidate id: {candidate['id']}")
        if candidate["origin"] not in {"internet", "user"}:
            raise ValidationError(f"{label}.origin must be internet or user")
        if candidate["origin"] == "internet":
            _text(candidate["source_url"], f"{label}.source_url")
            if not candidate["source_url"].startswith(("https://", "http://")):
                raise ValidationError(f"{label}.source_url must be an HTTP(S) URL")
        elif candidate["source_url"] is not None:
            _text(candidate["source_url"], f"{label}.source_url")
        if candidate["kind"] not in _KINDS:
            raise ValidationError(f"{label}.kind is invalid")
        if candidate["rights_status"] not in _RIGHTS:
            raise ValidationError(f"{label}.rights_status is invalid")
        if candidate["rights_status"] == "unknown" and not candidate["rights_evidence"].strip():
            raise ValidationError(f"{label}.rights_evidence must explain why rights are unknown")
        if candidate["kind"] == "real_ui" and not isinstance(candidate["authentic"], bool):
            raise ValidationError(f"{label}.authentic must be boolean for real_ui candidates")
        if candidate["kind"] != "real_ui" and candidate["authentic"] is not None:
            raise ValidationError(f"{label}.authentic must be null unless kind is real_ui")
        for field in ("width", "height"):
            if isinstance(candidate[field], bool) or not isinstance(candidate[field], int) or candidate[field] <= 0:
                raise ValidationError(f"{label}.{field} must be a positive integer")
        if not isinstance(candidate["sha256"], str) or not _SHA256.fullmatch(candidate["sha256"]):
            raise ValidationError(f"{label}.sha256 must be a lowercase SHA-256 value")
        _safe_image(base_dir, candidate)
        candidate_by_id[candidate["id"]] = candidate

    candidates_from_search_by_beat = {beat_id: set() for beat_id in beat_ids}
    internet_candidate_beats = {candidate_id: set() for candidate_id in candidate_by_id}
    for search in searches:
        unknown_candidates = set(search["candidate_ids"]) - candidate_by_id.keys()
        if unknown_candidates:
            raise ValidationError(f"search {search['id']} references unknown candidate(s): {', '.join(sorted(unknown_candidates))}")
        for candidate_id in search["candidate_ids"]:
            candidate = candidate_by_id[candidate_id]
            if candidate["origin"] != "internet":
                raise ValidationError(f"search {search['id']} cannot record user-provided candidate {candidate_id} as an Internet result")
            search_beats = set(search["beat_ids"])
            if not search_beats.issubset(candidate["beat_ids"]):
                raise ValidationError(f"candidate {candidate_id}.beat_ids does not cover all beats for search {search['id']}")
            internet_candidate_beats[candidate_id].update(search_beats)
            for beat_id in search_beats:
                candidates_from_search_by_beat[beat_id].add(candidate_id)
    for candidate_id, candidate in candidate_by_id.items():
        if candidate["origin"] == "internet" and set(candidate["beat_ids"]) != internet_candidate_beats[candidate_id]:
            raise ValidationError(f"candidate {candidate_id}.beat_ids must match its Internet search coverage")
        if candidate["origin"] == "user" and candidate["rights_status"] != "user_provided":
            raise ValidationError(f"candidate {candidate_id} from a user must use rights_status user_provided")
        if candidate["origin"] == "internet" and candidate["rights_status"] == "user_provided":
            raise ValidationError(f"Internet candidate {candidate_id} cannot use rights_status user_provided")

    review = payload["harness_review"]
    _object(review, "harness_review", {"harness_id", "reviewed_at", "narration_sha256", "voice_screen_map_sha256", "summary", "strengths", "limitations", "overall_decision", "self_evaluation", "beats"})
    _text(review["harness_id"], "harness_review.harness_id")
    reviewed_at = _timestamp(review["reviewed_at"], "harness_review.reviewed_at")
    if review["narration_sha256"] != narration_sha256 or review["voice_screen_map_sha256"] != voice_screen_map_sha256:
        raise ValidationError("harness review hashes do not match the supplied narration and voice-screen map")
    _text(review["summary"], "harness_review.summary")
    _string_list(review["strengths"], "harness_review.strengths")
    _string_list(review["limitations"], "harness_review.limitations", nonempty=False)
    self_eval = review["self_evaluation"]
    _object(self_eval, "harness_review.self_evaluation", {"status", "dimensions", "open_findings"})
    if self_eval["status"] != "PASS" or not isinstance(self_eval["dimensions"], dict) or not self_eval["dimensions"]:
        raise ValidationError("harness self_evaluation must be PASS with non-empty dimensions")
    _string_list(self_eval["open_findings"], "harness_review.self_evaluation.open_findings", nonempty=False)
    if self_eval["open_findings"]:
        raise ValidationError("harness self_evaluation cannot PASS with open findings")
    beat_reviews = review["beats"]
    if not isinstance(beat_reviews, list) or len(beat_reviews) != len(beat_ids):
        raise ValidationError("harness_review.beats must cover every voice-screen beat exactly once")
    review_by_id = {}
    decision_packets = []
    expected_overall = set()
    required_beat_keys = {"beat_id", "visual_need", "requires_real_ui", "search_ids", "candidate_assessments", "decision", "selected_candidate_id", "evidence", "learner_impact", "image_request", "human_question", "human_recommendation"}
    required_request_keys = {"subject", "must_show", "minimum_resolution", "preferred_format"}
    for index, beat_review in enumerate(beat_reviews, 1):
        label = f"harness_review.beats[{index}]"
        _object(beat_review, label, required_beat_keys)
        beat_id = beat_review["beat_id"]
        if beat_id not in beat_ids or beat_id in review_by_id:
            raise ValidationError(f"{label}.beat_id must be a unique id from the voice-screen map")
        review_by_id[beat_id] = beat_review
        _text(beat_review["visual_need"], f"{label}.visual_need")
        if not isinstance(beat_review["requires_real_ui"], bool):
            raise ValidationError(f"{label}.requires_real_ui must be boolean")
        beat_search_ids = _string_list(beat_review["search_ids"], f"{label}.search_ids")
        if set(beat_search_ids) - search_ids:
            raise ValidationError(f"{label}.search_ids references unknown searches")
        expected_search_ids = {search["id"] for search in searches if beat_id in search["beat_ids"]}
        if set(beat_search_ids) != expected_search_ids:
            raise ValidationError(f"{label}.search_ids must include every search recorded for this beat")
        if any(beat_id not in search_by_id[sid]["beat_ids"] for sid in beat_search_ids):
            raise ValidationError(f"{label}.search_ids includes a search not mapped to this beat")
        if reviewed_at < max(_timestamp(search_by_id[sid]["searched_at"], f"search {sid}.searched_at") for sid in beat_search_ids):
            raise ValidationError(f"{label} must be reviewed after its recorded Internet searches")
        assessment_list = beat_review["candidate_assessments"]
        if not isinstance(assessment_list, list):
            raise ValidationError(f"{label}.candidate_assessments must be an array")
        assessment_by_id = {}
        for ai, assessment in enumerate(assessment_list, 1):
            alabel = f"{label}.candidate_assessments[{ai}]"
            _object(assessment, alabel, {"candidate_id", "criteria"})
            cid = assessment["candidate_id"]
            if cid not in candidate_by_id or cid in assessment_by_id:
                raise ValidationError(f"{alabel}.candidate_id must be unique and reference a candidate")
            candidate = candidate_by_id[cid]
            if cid not in candidates_from_search_by_beat[beat_id] and not (candidate["origin"] == "user" and beat_id in candidate["beat_ids"]):
                raise ValidationError(f"{alabel}.candidate_id was not recorded as a result for this beat's searches")
            criteria = assessment["criteria"]
            if not isinstance(criteria, dict) or criteria.keys() != _CRITERIA:
                raise ValidationError(f"{alabel}.criteria must contain exactly {', '.join(sorted(_CRITERIA))}")
            for criterion, evaluation in criteria.items():
                elabel = f"{alabel}.criteria.{criterion}"
                _object(evaluation, elabel, {"status", "evidence"})
                if evaluation["status"] not in _STATUSES:
                    raise ValidationError(f"{elabel}.status is invalid")
                _text(evaluation["evidence"], f"{elabel}.evidence")
                if evaluation["status"] == "not_applicable" and criterion != "authenticity":
                    raise ValidationError(f"{elabel} cannot be not_applicable")
            candidate_kind = candidate_by_id[cid]["kind"]
            authenticity_status = criteria["authenticity"]["status"]
            if candidate_kind == "real_ui" and authenticity_status == "pass" and candidate_by_id[cid]["authentic"] is not True:
                raise ValidationError(f"{alabel} cannot pass authenticity when the candidate is not verified as authentic")
            if candidate_kind != "real_ui" and authenticity_status == "pass":
                raise ValidationError(f"{alabel} cannot pass authenticity for a non-UI asset")
            if authenticity_status == "not_applicable" and (beat_review["requires_real_ui"] or candidate_kind == "real_ui"):
                raise ValidationError(f"{alabel}.criteria.authenticity cannot be not_applicable for a real-UI requirement or candidate")
            if criteria["rights_and_provenance"]["status"] == "pass" and candidate_by_id[cid]["rights_status"] == "unknown":
                raise ValidationError(f"{alabel} cannot pass rights_and_provenance while candidate rights are unknown")
            assessment_by_id[cid] = assessment
        expected_candidate_ids = candidates_from_search_by_beat[beat_id] | {
            cid for cid, candidate in candidate_by_id.items()
            if candidate["origin"] == "user" and beat_id in candidate["beat_ids"]
        }
        if set(assessment_by_id) != expected_candidate_ids:
            missing = sorted(expected_candidate_ids - assessment_by_id.keys())
            raise ValidationError(f"{label} must assess every inspected search candidate; missing: {', '.join(missing) or '(none)'}")

        decision = beat_review["decision"]
        if decision not in {"use_candidate", "ask_user_for_image", "needs_human_decision"}:
            raise ValidationError(f"{label}.decision is invalid")
        _text(beat_review["evidence"], f"{label}.evidence")
        _text(beat_review["learner_impact"], f"{label}.learner_impact")
        selected_id = beat_review["selected_candidate_id"]
        adequate_ids = [cid for cid, assessment in assessment_by_id.items()
                        if _candidate_is_adequate(candidate_by_id[cid], assessment, beat_review["requires_real_ui"])]
        if decision == "use_candidate":
            if selected_id not in adequate_ids:
                raise ValidationError(f"{label} must select a candidate that passes every applicable criterion")
            if beat_review["image_request"] is not None or beat_review["human_question"] is not None or beat_review["human_recommendation"] is not None:
                raise ValidationError(f"{label} cannot include a human request when using an adequate candidate")
        elif decision == "ask_user_for_image":
            if selected_id is not None or adequate_ids:
                raise ValidationError(f"{label} cannot request an image when an adequate candidate is available")
            distinct_queries = {search_by_id[sid]["query"].casefold().strip() for sid in beat_search_ids}
            if len(distinct_queries) < 3:
                raise ValidationError(f"{label} needs at least three distinct Internet search queries before requesting an image")
            request = beat_review["image_request"]
            _object(request, f"{label}.image_request", required_request_keys)
            _text(request["subject"], f"{label}.image_request.subject")
            _string_list(request["must_show"], f"{label}.image_request.must_show")
            _text(request["minimum_resolution"], f"{label}.image_request.minimum_resolution")
            _text(request["preferred_format"], f"{label}.image_request.preferred_format")
            if beat_review["human_question"] is not None or beat_review["human_recommendation"] is not None:
                raise ValidationError(f"{label} image request cannot also be a human-decision question")
            expected_overall.add(decision)
            decision_packets.append({"beat_id": beat_id, "decision": decision, "visual_need": beat_review["visual_need"],
                                     "search_queries": [search_by_id[sid]["query"] for sid in beat_search_ids],
                                     "rejected_candidates": [{"id": cid, "title": candidate_by_id[cid]["title"], "source_url": candidate_by_id[cid]["source_url"],
                                                              "reason": "; ".join(a["criteria"][k]["evidence"] for k in ("teaching_relevance", "visual_match", "legibility", "authenticity", "rights_and_provenance") if a["criteria"][k]["status"] not in {"pass", "not_applicable"})}
                                                             for cid, a in assessment_by_id.items()],
                                     "evidence": beat_review["evidence"], "learner_impact": beat_review["learner_impact"],
                                     "image_request": request})
        else:
            if selected_id is not None or beat_review["image_request"] is not None:
                raise ValidationError(f"{label} human-decision state cannot select a candidate or request an image")
            _text(beat_review["human_question"], f"{label}.human_question")
            _text(beat_review["human_recommendation"], f"{label}.human_recommendation")
            expected_overall.add(decision)
            decision_packets.append({"beat_id": beat_id, "decision": decision, "question": beat_review["human_question"],
                                     "evidence": beat_review["evidence"], "learner_impact": beat_review["learner_impact"],
                                     "recommendation": beat_review["human_recommendation"]})

    if set(review_by_id) != beat_ids:
        raise ValidationError("harness review does not map one-to-one to every voice-screen beat")
    expected_decision = ("mixed_review" if len(expected_overall) > 1 else
                         "needs_user_images" if expected_overall == {"ask_user_for_image"} else
                         "needs_human_decision" if expected_overall == {"needs_human_decision"} else "ready")
    if review["overall_decision"] != expected_decision:
        raise ValidationError(f"harness_review.overall_decision must be {expected_decision}")

    base = {"schema_version": 1, "status": "PASS" if expected_decision == "ready" else "AWAITING_HUMAN",
            "gate": "visual_direction_selection_allowed" if expected_decision == "ready" else "visual_asset_review",
            "narration_sha256": narration_sha256, "voice_screen_map_sha256": voice_screen_map_sha256,
            "review_summary": review["summary"], "scope_note": "Evidence structure and hashes are checked locally. Internet search, source rights, and semantic image fit are attested by the harness and must be verified by inspecting the cited pages and image files."}
    if expected_decision == "ready":
        return {**base, "selected_assets": [{"beat_id": beat_id, "candidate_id": item["selected_candidate_id"]}
                                             for beat_id, item in review_by_id.items()]}
    packet = {**base, "decision": expected_decision, "items": decision_packets,
              "instruction": "Show these exact findings in the conversation and wait for the user's decision or supplied images. Do not proceed to visual-direction selection or rendering while this gate is pending."}
    raise HumanReviewRequired(packet)


def load_and_validate_visual_asset_review(manifest_path, narration_path, map_path):
    manifest_path = Path(manifest_path).resolve()
    narration_path = Path(narration_path).resolve()
    map_path = Path(map_path).resolve()
    try:
        manifest, _ = read_json(manifest_path)
        narration, narration_bytes = read_script(narration_path)
        voice_screen_map, map_bytes = read_json(map_path)
    except OSError as exc:
        raise ValidationError(str(exc)) from exc
    validate_voice_screen_map(voice_screen_map)
    return validate_visual_asset_review(manifest, manifest_path.parent, hashlib.sha256(narration_bytes).hexdigest(),
                                        hashlib.sha256(map_bytes).hexdigest(), voice_screen_map)
