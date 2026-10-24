"""Validate the narration-versus-screen contract used by courseware storyboards."""

import re

from .errors import HumanReviewRequired, ValidationError
from .visual_sequence import validate_visual_sequences


_VOICE_MODES = {"summary", "verbatim", "silent"}
_ASSET_KINDS = {"real_ui", "official_illustration", "original_graphic", "other"}
_SECRET_PATTERNS = (
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"(?i)(?:api[_-]?key|access[_-]?token|secret)\s*[=:]\s*['\"]?(?!YOUR_API_KEY\b|<REDACTED>\b)[A-Za-z0-9_./+=-]{20,}"),
)
_CODE_ASSIGNMENT = re.compile(r"(?m)^\s*[A-Za-z_][A-Za-z0-9_.-]*\s*=\s*['\"][^'\"]+['\"]\s*$")


def _nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} must be a non-empty string")


def _contains_secret(value):
    return any(pattern.search(value) for pattern in _SECRET_PATTERNS)


def validate_voice_screen_map(payload):
    """Check a voice-screen map without calling a provider or rendering media.

    A passing result is a structural/editorial contract check, not a judgment that
    the narration is natural, factually correct, or synchronized to final audio.
    """
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValidationError("voice-screen map schema_version must be 1")
    beats = payload.get("beats")
    if not isinstance(beats, list) or not beats:
        raise ValidationError("beats must be a non-empty array")

    seen = set()
    pending = []
    report_beats = []
    for index, beat in enumerate(beats, 1):
        prefix = f"beats[{index}]"
        if not isinstance(beat, dict):
            raise ValidationError(f"{prefix} must be an object")
        beat_id = beat.get("id")
        _nonempty(beat_id, f"{prefix}.id")
        if beat_id in seen:
            raise ValidationError(f"duplicate beat id: {beat_id}")
        seen.add(beat_id)

        duration = beat.get("duration_seconds")
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration <= 0:
            raise ValidationError(f"{prefix}.duration_seconds must be positive")
        if duration > 12 and not str(beat.get("duration_reason", "")).strip():
            raise ValidationError(f"{prefix} over 12 seconds needs duration_reason")

        _nonempty(beat.get("screen_text"), f"{prefix}.screen_text")
        _nonempty(beat.get("focus"), f"{prefix}.focus")
        transition = beat.get("transition")
        if not isinstance(transition, dict):
            raise ValidationError(f"{prefix}.transition must declare entry, exit, and motion")
        for field in ("entry", "exit", "motion"):
            _nonempty(transition.get(field), f"{prefix}.transition.{field}")

        mode = beat.get("voice_mode")
        if mode not in _VOICE_MODES:
            raise ValidationError(f"{prefix}.voice_mode must be one of {sorted(_VOICE_MODES)}")
        narration = beat.get("narration", "")
        if not isinstance(narration, str):
            raise ValidationError(f"{prefix}.narration must be text")
        if mode == "summary":
            _nonempty(narration, f"{prefix}.narration")
            _nonempty(beat.get("spoken_purpose"), f"{prefix}.spoken_purpose")
        elif mode == "silent" and narration.strip():
            raise ValidationError(f"{prefix} silent beat must have empty narration")
        elif mode == "verbatim":
            _nonempty(narration, f"{prefix}.narration")
            _nonempty(beat.get("verbatim_reason"), f"{prefix}.verbatim_reason")

        technical = beat.get("technical_display", False)
        if not isinstance(technical, bool):
            raise ValidationError(f"{prefix}.technical_display must be boolean")
        required_terms = beat.get("required_screen_terms", [])
        if not isinstance(required_terms, list) or not all(isinstance(item, str) and item for item in required_terms):
            raise ValidationError(f"{prefix}.required_screen_terms must be an array of non-empty strings")
        if technical and not required_terms:
            raise ValidationError(f"{prefix} technical display must enumerate required_screen_terms")
        for term in required_terms:
            if term not in beat["screen_text"]:
                raise ValidationError(f"{prefix}.screen_text is missing required exact text: {term}")
        screen_only_terms = beat.get("screen_only_terms", [])
        if not isinstance(screen_only_terms, list) or not all(isinstance(item, str) and item for item in screen_only_terms):
            raise ValidationError(f"{prefix}.screen_only_terms must be an array of non-empty strings")
        if technical and mode == "summary":
            if _CODE_ASSIGNMENT.search(narration):
                raise ValidationError(f"{prefix} reads code/config assignment syntax aloud; summarize its purpose instead")
            lowered = narration.casefold()
            for term in screen_only_terms:
                if term.casefold() in lowered:
                    raise ValidationError(f"{prefix} narration repeats screen-only term: {term}")

        assets = beat.get("assets", [])
        if not isinstance(assets, list):
            raise ValidationError(f"{prefix}.assets must be an array")
        asset_report = []
        for asset_index, asset in enumerate(assets, 1):
            if not isinstance(asset, dict):
                raise ValidationError(f"{prefix}.assets[{asset_index}] must be an object")
            kind = asset.get("kind")
            if kind not in _ASSET_KINDS:
                raise ValidationError(f"{prefix}.assets[{asset_index}].kind is invalid")
            _nonempty(asset.get("source"), f"{prefix}.assets[{asset_index}].source")
            if kind == "real_ui" and asset.get("authentic") is not True:
                raise ValidationError(f"{prefix} real_ui assets must be explicitly marked authentic")
            asset_report.append({"kind": kind, "source": asset["source"], "authentic": asset.get("authentic")})

        for field in ("screen_text", "narration"):
            if _contains_secret(beat.get(field, "")):
                raise ValidationError(f"{prefix}.{field} appears to contain a credential; replace it with a placeholder")

        uncertainty = beat.get("uncertainty")
        if uncertainty is not None:
            if not isinstance(uncertainty, dict):
                raise ValidationError(f"{prefix}.uncertainty must be an object")
            for field in ("question", "evidence", "impact", "recommendation"):
                _nonempty(uncertainty.get(field), f"{prefix}.uncertainty.{field}")
            if uncertainty.get("decision_status", "pending") == "pending":
                pending.append({"beat_id": beat_id, **uncertainty})
            elif uncertainty.get("decision_status") != "resolved":
                raise ValidationError(f"{prefix}.uncertainty.decision_status must be pending or resolved")

        report_beats.append({"id": beat_id, "duration_seconds": duration, "voice_mode": mode,
                             "technical_display": technical, "focus": beat["focus"], "assets": asset_report})

    sequences = validate_visual_sequences(payload)
    for sequence in sequences:
        uncertainty = sequence.get("uncertainty")
        if uncertainty and uncertainty.get("decision_status", "pending") == "pending":
            pending.append({"sequence_id": sequence["id"], **uncertainty})
    report = {"schema_version": 1, "status": "AWAITING_HUMAN" if pending else "PASS",
              "beat_count": len(beats), "beats": report_beats, "pending_uncertainties": pending,
              "visual_sequences": sequences,
              "scope_note": "Structural contract only; it does not verify semantic accuracy, voice naturalness, rights, or final audio/video sync."}
    if pending:
        raise HumanReviewRequired(report)
    return report
