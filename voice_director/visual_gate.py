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


def _verify_ref(root, payload, label):
    if not isinstance(payload, dict):
        raise ValidationError(f"{label} must be an object")
    relative = payload.get("file")
    expected = payload.get("sha256")
    if not isinstance(relative, str) or not relative.strip() or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValidationError(f"{label}.file must be relative to the private run directory")
    if not isinstance(expected, str) or not _SHA256.fullmatch(expected):
        raise ValidationError(f"{label}.sha256 must be a lowercase SHA-256 value")
    path = (root / relative).resolve()
    if root.resolve() not in path.parents:
        raise ValidationError(f"{label}.file escapes the private run directory")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ValidationError(f"{label}.file cannot be read: {exc}") from exc
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValidationError(f"{label}.sha256 does not match the file")
    return relative.replace("\\", "/"), path, data


def validate_visual_gate(payload, base_dir, *, project_root=None, ffprobe_path=None, ffmpeg_path=None):
    """Validate the linked asset, style, sample-quality, and user-approval gates.

    It does not render media or make semantic/aesthetic judgments. Those remain
    harness and user responsibilities over the actual evidence.
    """
    if not isinstance(payload, dict) or payload.get("schema_version") != 2:
        raise ValidationError("visual gate schema_version must be 2")
    expected_keys = {"schema_version", "asset_review", "options", "selected_option_id", "design_sample"}
    if set(payload) != expected_keys:
        raise ValidationError("visual gate fields must be exactly " + ", ".join(sorted(expected_keys)))
    root = Path(base_dir).resolve()

    asset_ref = payload["asset_review"]
    required_asset_ref = {"manifest_file", "manifest_sha256", "narration_file", "narration_sha256",
                          "voice_screen_map_file", "voice_screen_map_sha256"}
    if not isinstance(asset_ref, dict) or set(asset_ref) != required_asset_ref:
        raise ValidationError("asset_review must bind the reviewed manifest, narration, and voice/screen map")
    manifest_name, asset_path, _ = _verify_ref(root, {"file": asset_ref["manifest_file"], "sha256": asset_ref["manifest_sha256"]}, "asset_review")
    _verify_ref(root, {"file": asset_ref["narration_file"], "sha256": asset_ref["narration_sha256"]}, "asset_review.narration")
    _verify_ref(root, {"file": asset_ref["voice_screen_map_file"], "sha256": asset_ref["voice_screen_map_sha256"]}, "asset_review.voice_screen_map")
    from .visual_asset_review import load_and_validate_visual_asset_review
    asset_report = load_and_validate_visual_asset_review(asset_path,
        root / asset_ref["narration_file"], root / asset_ref["voice_screen_map_file"])
    if asset_report["status"] != "PASS":
        raise ValidationError("Internet visual asset review must pass before visual direction selection")

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
        from .visual_quality import _image_dimensions
        option_width, option_height = _image_dimensions(resolved_path, image_data, prefix + ".image_file")
        if option_width < 1920 or option_height < 1080 or abs(option_width / option_height - 16 / 9) > 0.005:
            raise ValidationError(f"{prefix}.image_file must be at least 1920x1080 and 16:9")
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
    required_sample = {"video_file", "sha256", "based_on_option_id", "quality_review_file", "quality_review_sha256", "decision_status"}
    optional_sample = {"feedback"}
    if not required_sample.issubset(sample) or sample.keys() - (required_sample | optional_sample):
        raise ValidationError("design_sample must bind its video and a completed visual-quality review")
    if sample.get("based_on_option_id") != selected:
        raise ValidationError("design_sample.based_on_option_id must match selected_option_id")
    sample_path, resolved_sample, sample_data = _verify_private_asset(base_dir, sample, "design_sample", "video_file")
    if resolved_sample.suffix.lower() not in {".mp4", ".m4v", ".mov"} or len(sample_data) < 12 or sample_data[4:8] != b"ftyp":
        raise ValidationError("design_sample.video_file must be an MP4-family video with a valid ftyp container signature")
    if not project_root:
        raise ValidationError("--project-root is required to validate the design sample's exact HyperFrames inputs")
    quality_name, quality_path, _ = _verify_ref(root, {"file": sample["quality_review_file"], "sha256": sample["quality_review_sha256"]}, "design_sample.quality_review")
    from .visual_quality import load_and_validate_visual_quality_review
    quality_report = load_and_validate_visual_quality_review(quality_path, project_root=project_root,
                                                              ffprobe_path=ffprobe_path, ffmpeg_path=ffmpeg_path)
    if quality_report["status"] != "PASS" or quality_report["stage"] != "design_sample":
        raise ValidationError("design sample must have a passing design_sample quality report")
    if quality_report["video_sha256"] != sample["sha256"] or quality_report["video_file"] != sample_path:
        raise ValidationError("design-sample quality evidence must bind the exact sample video")
    quality_inputs = quality_report["inputs"]
    if (quality_inputs["visual_asset_review_file"] != manifest_name
            or quality_inputs["visual_asset_review_sha256"] != asset_ref["manifest_sha256"]
            or quality_inputs["narration_file"] != asset_ref["narration_file"]
            or quality_inputs["narration_sha256"] != asset_ref["narration_sha256"]
            or quality_inputs["voice_screen_map_file"] != asset_ref["voice_screen_map_file"]
            or quality_inputs["voice_screen_map_sha256"] != asset_ref["voice_screen_map_sha256"]):
        raise ValidationError("design-sample quality review must use the exact assets, narration, and map approved by this gate")
    selected_option = next(item for item in options if item["id"] == selected)
    if (quality_inputs["visual_direction_id"] != selected_option["id"]
            or quality_inputs["visual_direction_file"] != selected_option["image_file"]
            or quality_inputs["visual_direction_sha256"] != selected_option["sha256"]):
        raise ValidationError("design-sample quality review must bind the option the user selected")
    decision = sample.get("decision_status", "pending")
    if decision == "pending":
        raise HumanReviewRequired({"schema_version": 1, "status": "AWAITING_HUMAN", "gate": "approve_design_sample",
                                   "selected_option_id": selected, "design_sample": sample_path,
                                   "quality_review": quality_name,
                                   "sha256": sample["sha256"],
                                   "question": "Is this short design sample approved for the full lesson render?",
                                   "instruction": "Wait for explicit approval or revision notes; do not render the full lesson yet."})
    if decision == "revision_requested":
        _text(sample.get("feedback"), "design_sample.feedback")
        raise HumanReviewRequired({"schema_version": 1, "status": "AWAITING_HUMAN", "gate": "revise_design_sample",
                                   "selected_option_id": selected, "design_sample": sample_path,
                                   "quality_review": quality_name,
                                   "feedback": sample["feedback"],
                                   "instruction": "Revise the short sample and request approval again before full-lesson rendering."})
    if decision != "approved":
        raise ValidationError("design_sample.decision_status must be pending, approved, or revision_requested")
    return {"schema_version": 1, "status": "PASS", "gate": "full_lesson_render_allowed",
            "selected_option_id": selected, "design_sample": sample_path, "sha256": sample["sha256"],
            "quality_review": quality_name, "quality_review_sha256": sample["quality_review_sha256"],
            "asset_review": manifest_name, "asset_review_sha256": asset_ref["manifest_sha256"]}
