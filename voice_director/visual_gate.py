"""Enforce a user-selected visual direction and design-sample review before full rendering."""

import hashlib
import re
from pathlib import Path

from .errors import HumanReviewRequired, ValidationError


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IMAGE_SIGNATURES = {
    ".png": lambda data: data.startswith(b"\x89PNG\r\n\x1a\n"),
    ".jpg": lambda data: data.startswith(b"\xff\xd8\xff"),
    ".jpeg": lambda data: data.startswith(b"\xff\xd8\xff"),
    ".webp": lambda data: len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP",
}


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} must be a non-empty string")


def _verify_private_asset(base_dir, item, label, field):
    raw_path = item.get(field)
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValidationError(f"{label}.{field} must be a relative path inside the private run directory")
    relative = Path(raw_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValidationError(f"{label}.{field} must be a relative path inside the private run directory")
    expected = item.get("sha256")
    if not isinstance(expected, str) or not _SHA256.fullmatch(expected):
        raise ValidationError(f"{label}.sha256 must be a lowercase SHA-256 value")
    path = (base_dir / relative).resolve()
    root = base_dir.resolve()
    if root not in path.parents:
        raise ValidationError(f"{label}.{field} escapes the private run directory")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ValidationError(f"{label}.{field} cannot be read: {exc}") from exc
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise ValidationError(f"{label}.{field} SHA-256 does not match the manifest")
    return relative.as_posix(), path, data


def validate_visual_gate(payload, base_dir):
    """Validate the three-option selection and selected design-sample approval gate.

    This is a local structural and hash check. It does not generate visuals, judge
    design quality, or render the final lesson.
    """
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValidationError("visual gate schema_version must be 1")
    options = payload.get("options")
    if not isinstance(options, list) or len(options) != 3:
        raise ValidationError("visual gate requires exactly three independently generated options")

    option_ids = set()
    option_paths = set()
    option_hashes = set()
    option_report = []
    for index, option in enumerate(options, 1):
        prefix = f"options[{index}]"
        if not isinstance(option, dict):
            raise ValidationError(f"{prefix} must be an object")
        option_id = option.get("id")
        _text(option_id, f"{prefix}.id")
        if option_id in option_ids:
            raise ValidationError(f"duplicate visual option id: {option_id}")
        option_ids.add(option_id)
        _text(option.get("title"), f"{prefix}.title")
        asset_path, resolved_path, image_data = _verify_private_asset(base_dir, option, prefix, "image_file")
        signature_check = _IMAGE_SIGNATURES.get(resolved_path.suffix.lower())
        if signature_check is None or not signature_check(image_data):
            raise ValidationError(f"{prefix}.image_file must be a PNG, JPEG, or WebP image with a matching file signature")
        resolved_key = str(resolved_path).casefold()
        if resolved_key in option_paths or option["sha256"] in option_hashes:
            raise ValidationError("the three visual options must use distinct image files and content hashes")
        option_paths.add(resolved_key)
        option_hashes.add(option["sha256"])
        option_report.append({"id": option_id, "title": option["title"], "image_file": asset_path,
                              "sha256": option["sha256"]})

    selected = payload.get("selected_option_id")
    if selected is None:
        report = {"schema_version": 1, "status": "AWAITING_HUMAN", "gate": "select_visual_direction",
                  "options": option_report,
                  "question": "Which of the three visual directions should guide the design sample?",
                  "instruction": "Show all three option images in the conversation and wait for the user's explicit selection before rendering the design sample or full lesson."}
        raise HumanReviewRequired(report)
    if selected not in option_ids:
        raise ValidationError("selected_option_id must match one of the three option ids")

    sample = payload.get("design_sample")
    if sample is None:
        return {"schema_version": 1, "status": "STYLE_SELECTED", "gate": "render_design_sample",
                "selected_option_id": selected,
                "instruction": "Render and show a short design sample using this direction; full-lesson rendering remains blocked until the user approves that sample."}
    if not isinstance(sample, dict):
        raise ValidationError("design_sample must be an object")
    if sample.get("based_on_option_id") != selected:
        raise ValidationError("design_sample.based_on_option_id must match selected_option_id")
    sample_path, resolved_sample, sample_data = _verify_private_asset(base_dir, sample, "design_sample", "video_file")
    if resolved_sample.suffix.lower() not in {".mp4", ".m4v", ".mov"} or len(sample_data) < 12 or sample_data[4:8] != b"ftyp":
        raise ValidationError("design_sample.video_file must be an MP4-family video with a valid ftyp container signature")
    decision = sample.get("decision_status", "pending")
    if decision == "pending":
        raise HumanReviewRequired({"schema_version": 1, "status": "AWAITING_HUMAN", "gate": "approve_design_sample",
                                   "selected_option_id": selected, "design_sample": sample_path,
                                   "sha256": sample["sha256"],
                                   "question": "Is this short design sample approved for the full lesson render?",
                                   "instruction": "Wait for explicit approval or revision notes; do not render the full lesson yet."})
    if decision == "revision_requested":
        _text(sample.get("feedback"), "design_sample.feedback")
        raise HumanReviewRequired({"schema_version": 1, "status": "AWAITING_HUMAN", "gate": "revise_design_sample",
                                   "selected_option_id": selected, "design_sample": sample_path,
                                   "feedback": sample["feedback"],
                                   "instruction": "Revise the short sample and request approval again before full-lesson rendering."})
    if decision != "approved":
        raise ValidationError("design_sample.decision_status must be pending, approved, or revision_requested")
    return {"schema_version": 1, "status": "PASS", "gate": "full_lesson_render_allowed",
            "selected_option_id": selected, "design_sample": sample_path, "sha256": sample["sha256"]}
