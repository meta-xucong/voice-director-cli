"""Verify private render-quality evidence for courseware samples and final videos."""

import hashlib
import json
import math
import os
import re
import stat
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from .errors import HumanReviewRequired, ValidationError
from .schema import read_json, read_script
from .visual_asset_review import load_and_validate_visual_asset_review
from .voice_screen import validate_voice_screen_map


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CRITERIA = {
    "selected_direction_consistency", "visual_hierarchy", "spacing_alignment", "typography", "color_consistency",
    "clean_edges", "screenshot_readability", "caption_legibility", "crop_safety",
    "authenticity", "motion_quality", "pacing",
}
_FRAME_ROLES = {"entry", "settled", "exit", "motion_sample", "motion_extremum"}
_EFFECTS = {"none", "fade", "push_zoom", "pan", "focus_highlight", "wipe", "other"}
_FRAME_EXTRACTION_TIMEOUT_SECONDS = 3600
_MAX_FFMPEG_ERROR_BYTES = 65536


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


def _number(value, label, *, minimum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValidationError(f"{label} must be a finite number")
    if minimum is not None and value < minimum:
        raise ValidationError(f"{label} must be at least {minimum}")
    return float(value)


def _sha(value, label):
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValidationError(f"{label} must be a lowercase SHA-256 value")


def _relative_file(root, raw_path, expected_sha, label):
    _text(raw_path, f"{label}.file")
    path = Path(raw_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValidationError(f"{label}.file must stay inside the private run directory")
    resolved = (root / path).resolve()
    base = root.resolve()
    if base not in resolved.parents:
        raise ValidationError(f"{label}.file escapes the private run directory")
    try:
        data = resolved.read_bytes()
    except OSError as exc:
        raise ValidationError(f"{label}.file cannot be read: {exc}") from exc
    _sha(expected_sha, f"{label}.sha256")
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected_sha:
        raise ValidationError(f"{label}.sha256 does not match the file")
    return path.as_posix(), resolved, data


def _image_dimensions(path, data, label):
    suffix = path.suffix.lower()
    if suffix == ".png":
        if (len(data) < 33 or data[:8] != b"\x89PNG\r\n\x1a\n"
                or data[12:16] != b"IHDR" or data[8:12] != b"\x00\x00\x00\r"):
            raise ValidationError(f"{label} must be a PNG with a valid IHDR dimensions header")
        width = int.from_bytes(data[16:20], "big")
        height = int.from_bytes(data[20:24], "big")
    elif suffix in {".jpg", ".jpeg"}:
        width, height = _jpeg_dimensions(data, label)
    elif suffix == ".webp":
        width, height = _webp_dimensions(data, label)
    else:
        raise ValidationError(f"{label} must be PNG, JPEG, or WebP")
    if width <= 0 or height <= 0:
        raise ValidationError(f"{label} has invalid image dimensions")
    return width, height


def _webp_dimensions(data, label):
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ValidationError(f"{label} must be a valid WebP image")
    chunk = data[12:16]
    if chunk == b"VP8X":
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
    elif chunk == b"VP8L":
        if len(data) < 25 or data[20] != 0x2F:
            raise ValidationError(f"{label} WebP does not contain a readable lossless frame-size marker")
        width = 1 + data[21] + ((data[22] & 0x3F) << 8)
        height = 1 + ((data[22] >> 6) & 0x03) + (data[23] << 2) + ((data[24] & 0x0F) << 10)
    elif chunk == b"VP8 ":
        if data[23:26] != b"\x9d\x01\x2a":
            raise ValidationError(f"{label} WebP does not contain a readable lossy frame-size marker")
        width = int.from_bytes(data[26:28], "little") & 0x3FFF
        height = int.from_bytes(data[28:30], "little") & 0x3FFF
    else:
        raise ValidationError(f"{label} WebP uses an unsupported image chunk")
    return width, height


def _jpeg_dimensions(data, label):
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        raise ValidationError(f"{label} must be a valid JPEG image")
    index = 2
    sof = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while index + 4 <= len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        while index < len(data) and data[index] == 0xFF:
            index += 1
        if index >= len(data):
            break
        marker = data[index]
        index += 1
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7 or marker == 0x01:
            continue
        if index + 2 > len(data):
            break
        segment_length = int.from_bytes(data[index:index + 2], "big")
        if segment_length < 2 or index + segment_length > len(data):
            break
        if marker in sof:
            if segment_length < 7:
                break
            return (int.from_bytes(data[index + 5:index + 7], "big"),
                    int.from_bytes(data[index + 3:index + 5], "big"))
        index += segment_length
    raise ValidationError(f"{label} JPEG does not contain a readable frame-size marker")


def _probe_video(video_path, ffprobe_path=None):
    executable = ffprobe_path or shutil.which("ffprobe") or shutil.which("ffprobe.exe")
    if not executable:
        raise ValidationError("ffprobe is required for video-quality review; install FFmpeg or pass --ffprobe")
    command = [str(executable), "-v", "error", "-select_streams", "v:0", "-show_streams",
               "-show_format", "-of", "json", str(video_path)]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValidationError(f"ffprobe could not inspect the rendered video: {exc}") from exc
    if result.returncode != 0:
        raise ValidationError("ffprobe failed: " + (result.stderr or "unknown error").strip())
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValidationError("ffprobe returned invalid JSON") from exc
    return payload


def _ffmpeg_executable(ffmpeg_path):
    executable = ffmpeg_path or shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if not executable:
        raise ValidationError("ffmpeg is required to match evidence frames to the rendered video; install FFmpeg or pass --ffmpeg")
    return str(executable)


def _run_ffmpeg(command, label):
    try:
        result = subprocess.run(command, capture_output=True, check=False, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValidationError(f"ffmpeg could not verify {label}: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ValidationError(f"ffmpeg could not verify {label}: {detail or 'unknown error'}")
    return result.stdout


def _video_frame_indices(beats, fps):
    all_refs, by_beat = [], {}
    for beat in beats:
        if not isinstance(beat, dict) or not isinstance(beat.get("frames"), list):
            raise ValidationError("each quality beat must contain a frames array")
        beat_id = beat.get("beat_id")
        _text(beat_id, "beat_id")
        ids, times, roles = set(), {}, {}
        beat_indices = set()
        for frame in beat["frames"]:
            if not isinstance(frame, dict):
                raise ValidationError(f"beat {beat_id} frame evidence must be an object")
            frame_id = frame.get("id")
            _text(frame_id, f"beat {beat_id} frame id")
            if frame_id in ids:
                raise ValidationError(f"beat {beat_id} frame evidence ids must be unique")
            ids.add(frame_id)
            timestamp = _number(frame.get("timestamp_seconds"), f"beat {beat_id} frame timestamp", minimum=0)
            if timestamp in times.values():
                raise ValidationError(f"beat {beat_id} frame evidence timestamps must be unique")
            times[frame_id] = timestamp
            role = frame.get("role")
            if not isinstance(role, str) or not role:
                raise ValidationError(f"beat {beat_id} frame role must be a non-empty string")
            roles.setdefault(role, []).append(timestamp)
            frame_index = int(math.floor(timestamp * fps + 0.5))
            if abs(timestamp - frame_index / fps) > 0.500001 / fps:
                raise ValidationError(f"beat {beat_id} frame timestamp does not identify an output video frame")
            if frame_index in beat_indices:
                raise ValidationError(f"beat {beat_id} frame timestamps resolve to duplicate video frames")
            beat_indices.add(frame_index)
            all_refs.append((beat_id, frame_id, timestamp, frame_index))
        for role in ("entry", "settled", "exit"):
            if len(roles.get(role, [])) != 1:
                raise ValidationError(f"beat {beat_id} must have exactly one {role} frame")
        if not roles["entry"][0] < roles["settled"][0] < roles["exit"][0]:
            raise ValidationError(f"beat {beat_id} entry, settled, and exit frame times must be strictly increasing")
    return all_refs


def _extract_video_rgb(video_path, frame_refs, video_meta, ffmpeg_path, consume):
    indices = sorted({item[3] for item in frame_refs})
    if not indices:
        raise ValidationError("quality evidence contains no video frames to verify")
    frame_size = video_meta["width"] * video_meta["height"] * 3
    expression = "+".join(f"eq(n\\,{index})" for index in indices)
    script_path = None
    process = None
    stderr_reader = None
    timeout_timer = None
    timed_out = threading.Event()
    stderr_capture = bytearray()
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".ffscript", encoding="utf-8", delete=False) as script:
            script.write(f"[0:v:0]select='{expression}'[quality_frames]\n")
            script_path = Path(script.name)
        command = [_ffmpeg_executable(ffmpeg_path), "-v", "error", "-i", str(video_path),
                   "-filter_complex_script", str(script_path), "-map", "[quality_frames]",
                   "-vsync", "0", "-an", "-sn", "-dn", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError as exc:
            raise ValidationError(f"ffmpeg could not extract the selected video frames: {exc}") from exc

        def drain_stderr():
            while True:
                chunk = process.stderr.read(4096)
                if not chunk:
                    return
                remaining = _MAX_FFMPEG_ERROR_BYTES - len(stderr_capture)
                if remaining > 0:
                    stderr_capture.extend(chunk[:remaining])

        def stop_after_timeout():
            timed_out.set()
            try:
                process.kill()
            except OSError:
                pass

        stderr_reader = threading.Thread(target=drain_stderr, name="ffmpeg-stderr-drain", daemon=True)
        stderr_reader.start()
        timeout_timer = threading.Timer(_FRAME_EXTRACTION_TIMEOUT_SECONDS, stop_after_timeout)
        timeout_timer.daemon = True
        timeout_timer.start()
        truncated = False
        for index in indices:
            frame = process.stdout.read(frame_size)
            if timed_out.is_set():
                raise ValidationError("ffmpeg timed out while extracting the selected video frames")
            if len(frame) != frame_size:
                truncated = True
                break
            consume(index, frame)
        extra = process.stdout.read(1) if not truncated else b""
        if timed_out.is_set():
            raise ValidationError("ffmpeg timed out while extracting the selected video frames")
        return_code = process.wait()
        if timeout_timer is not None:
            timeout_timer.cancel()
        if stderr_reader is not None:
            stderr_reader.join(timeout=5)
        if return_code != 0:
            detail = stderr_capture.decode("utf-8", errors="replace").strip()
            raise ValidationError(f"ffmpeg could not extract the selected video frames: {detail or 'unknown error'}")
        if truncated or extra:
            raise ValidationError("ffmpeg did not return exactly one RGB frame for every requested video timestamp")
    finally:
        if timeout_timer is not None:
            timeout_timer.cancel()
        if process is not None:
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stdout.close()
            process.stderr.close()
        if stderr_reader is not None:
            stderr_reader.join(timeout=5)
        if script_path is not None:
            script_path.unlink(missing_ok=True)


def _verify_video_frame_pixels(video_path, frame_refs, beats, root, video_meta, ffmpeg_path):
    by_index = {}
    beat_by_id = {beat["beat_id"]: beat for beat in beats}
    for beat_id, frame_id, _, frame_index in frame_refs:
        beat = beat_by_id[beat_id]
        frame = next((item for item in beat["frames"] if item.get("id") == frame_id), None)
        if frame is None:
            raise ValidationError(f"frame evidence {beat_id}/{frame_id} is missing")
        by_index.setdefault(frame_index, []).append((beat_id, frame))

    def compare(frame_index, video_rgb):
        for beat_id, frame in by_index[frame_index]:
            label = f"beat {beat_id} frame {frame['id']}"
            _, path, data = _relative_file(root, frame.get("file"), frame.get("sha256"), label)
            width, height = _image_dimensions(path, data, label)
            if (width, height) != (video_meta["width"], video_meta["height"]):
                raise ValidationError(f"{label} must match the rendered video resolution")
            evidence_rgb = _decode_image_rgb(path, width, height, ffmpeg_path)
            if evidence_rgb != video_rgb:
                raise ValidationError(f"{label} pixels do not match the specified frame from the reviewed video")

    _extract_video_rgb(video_path, frame_refs, video_meta, ffmpeg_path, compare)


def _decode_image_rgb(path, width, height, ffmpeg_path):
    command = [_ffmpeg_executable(ffmpeg_path), "-v", "error", "-i", str(path), "-frames:v", "1",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
    raw = _run_ffmpeg(command, f"frame evidence image {path.name}")
    expected_size = width * height * 3
    if len(raw) != expected_size:
        raise ValidationError(f"frame evidence image {path.name} did not decode to the expected RGB dimensions")
    return raw


def _ratio(value, label):
    _text(value, label)
    try:
        numerator, denominator = value.split("/", 1)
        numerator, denominator = float(numerator), float(denominator)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValidationError(f"{label} must be a positive rational frame rate") from exc
    if not math.isfinite(numerator) or not math.isfinite(denominator) or numerator <= 0 or denominator <= 0:
        raise ValidationError(f"{label} must be a positive rational frame rate")
    return numerator / denominator


def _probe_metadata(probe, stage):
    if not isinstance(probe, dict) or not isinstance(probe.get("streams"), list):
        raise ValidationError("ffprobe output must contain a streams array")
    videos = [stream for stream in probe["streams"] if isinstance(stream, dict) and stream.get("codec_type") == "video"]
    if len(videos) != 1:
        raise ValidationError("the rendered file must contain exactly one selected video stream")
    stream = videos[0]
    width, height = stream.get("width"), stream.get("height")
    if any(isinstance(x, bool) or not isinstance(x, int) for x in (width, height)):
        raise ValidationError("ffprobe must report integer video width and height")
    if width < 1920 or height < 1080:
        raise ValidationError("render resolution must be at least 1920x1080")
    if abs(width / height - 16 / 9) > 0.005:
        raise ValidationError("render aspect ratio must be 16:9 (within 0.005)")
    avg_fps = _ratio(stream.get("avg_frame_rate", stream.get("r_frame_rate")), "average video frame rate")
    nominal_fps = _ratio(stream.get("r_frame_rate", stream.get("avg_frame_rate")), "nominal video frame rate")
    if abs(avg_fps - nominal_fps) > 0.01:
        raise ValidationError("render must use a constant frame rate; FFprobe average and nominal rates differ")
    fps = avg_fps
    if fps < 30:
        raise ValidationError("render frame rate must be at least 30 fps")
    if stream.get("field_order") != "progressive":
        raise ValidationError("render must use progressive scan; ffprobe field_order must be progressive")
    duration = stream.get("duration") or probe.get("format", {}).get("duration")
    try:
        duration = float(duration)
    except (TypeError, ValueError) as exc:
        raise ValidationError("ffprobe must report a finite positive video duration") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise ValidationError("ffprobe must report a finite positive video duration")
    try:
        start_time = float(stream.get("start_time", 0) or 0)
    except (TypeError, ValueError) as exc:
        raise ValidationError("ffprobe must report a finite video start time") from exc
    if not math.isfinite(start_time) or abs(start_time) > 0.500001 / fps:
        raise ValidationError("render video must start at timestamp zero for exact evidence-frame matching")
    if stage == "design_sample" and not 20 <= duration <= 60:
        raise ValidationError("design sample duration must be 20–60 seconds")
    return {"width": width, "height": height, "fps": round(fps, 6), "field_order": "progressive",
            "duration_seconds": duration, "start_time_seconds": start_time, "codec_name": stream.get("codec_name")}


def _project_inventory(root, path_value, sha_value, project_root):
    path_text, path, _ = _relative_file(root, path_value, sha_value, "project_inventory")
    try:
        payload, _ = read_json(path)
    except ValidationError as exc:
        raise ValidationError(f"project_inventory is invalid: {exc}") from exc
    _object(payload, "project_inventory", {"schema_version", "files"})
    if payload["schema_version"] != 1 or not isinstance(payload["files"], list) or not payload["files"]:
        raise ValidationError("project_inventory requires schema_version 1 and a non-empty files array")
    project_root = Path(project_root).resolve()
    if not project_root.is_dir():
        raise ValidationError("--project-root must be an existing directory")
    seen = set()
    files = []
    for index, item in enumerate(payload["files"], 1):
        label = f"project_inventory.files[{index}]"
        _object(item, label, {"path", "sha256", "role"})
        _text(item["path"], f"{label}.path")
        _text(item["role"], f"{label}.role")
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValidationError(f"{label}.path must stay under --project-root")
        resolved = (project_root / relative).resolve()
        if project_root not in resolved.parents:
            raise ValidationError(f"{label}.path escapes --project-root")
        _sha(item["sha256"], f"{label}.sha256")
        try:
            actual = hashlib.sha256(resolved.read_bytes()).hexdigest()
        except OSError as exc:
            raise ValidationError(f"{label}.path cannot be read: {exc}") from exc
        if actual != item["sha256"]:
            raise ValidationError(f"{label}.sha256 does not match the project file")
        key = relative.as_posix().casefold()
        if key in seen:
            raise ValidationError("project_inventory contains a duplicate path")
        seen.add(key)
        files.append({"path": relative.as_posix(), "sha256": actual, "role": item["role"]})
    actual_paths = set()
    for parent, directories, filenames in os.walk(project_root, topdown=True, followlinks=False):
        parent_path = Path(parent)
        for name in directories:
            directory = parent_path / name
            if directory.is_symlink():
                raise ValidationError(f"project inventory root contains a symbolic-link directory: {directory.relative_to(project_root)}")
        for name in filenames:
            path = parent_path / name
            if path.is_symlink():
                raise ValidationError(f"project inventory root contains a symbolic-link file: {path.relative_to(project_root)}")
            try:
                mode = path.stat(follow_symlinks=False).st_mode
            except OSError as exc:
                raise ValidationError(f"project inventory entry cannot be inspected: {path.relative_to(project_root)}: {exc}") from exc
            if not stat.S_ISREG(mode):
                raise ValidationError(f"project inventory root may contain only regular files: {path.relative_to(project_root)}")
            actual_paths.add(path.relative_to(project_root).as_posix().casefold())
    omitted = actual_paths - seen
    missing = seen - actual_paths
    if omitted or missing:
        details = []
        if omitted:
            details.append("unlisted project files: " + ", ".join(sorted(omitted)[:8]))
        if missing:
            details.append("listed files absent from project: " + ", ".join(sorted(missing)[:8]))
        raise ValidationError("project_inventory must exactly match the project directory (" + "; ".join(details) + ")")
    return {"file": path_text, "sha256": sha_value, "file_count": len(files),
            "content_sha256": hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}


def _rect(value, label, frame_width, frame_height):
    _object(value, label, {"x", "y", "width", "height"})
    x = _number(value["x"], f"{label}.x", minimum=0)
    y = _number(value["y"], f"{label}.y", minimum=0)
    width = _number(value["width"], f"{label}.width", minimum=0)
    height = _number(value["height"], f"{label}.height", minimum=0)
    if width <= 0 or height <= 0 or x + width > frame_width or y + height > frame_height:
        raise ValidationError(f"{label} must be a non-empty rectangle inside the rendered frame")
    return x, y, width, height


def _points(value, label, count, width, height):
    if not isinstance(value, list) or len(value) != count:
        raise ValidationError(f"{label} must contain exactly {count} points")
    points = []
    for index, point in enumerate(value, 1):
        _object(point, f"{label}[{index}]", {"x", "y"})
        x = _number(point["x"], f"{label}[{index}].x", minimum=0)
        y = _number(point["y"], f"{label}[{index}].y", minimum=0)
        if x > width or y > height:
            raise ValidationError(f"{label}[{index}] is outside the rendered frame")
        points.append((x, y))
    return points


def _angle_delta(a, b):
    delta = abs(a - b) % 180
    return min(delta, 180 - delta)


def _edge_angles(points, closed):
    pairs = list(zip(points, points[1:]))
    if closed:
        pairs.append((points[-1], points[0]))
    result = []
    for (x1, y1), (x2, y2) in pairs:
        result.append(math.degrees(math.atan2(y2 - y1, x2 - x1)))
    return result


def _review_criterion(value, label):
    _object(value, label, {"status", "evidence"})
    _text(value["evidence"], f"{label}.evidence")
    if value["status"] not in {"pass", "fail", "not_applicable"}:
        raise ValidationError(f"{label}.status must be pass, fail, or not_applicable")
    if value["status"] == "not_applicable" and len(value["evidence"].strip()) < 12:
        raise ValidationError(f"{label} must explain why it is not applicable")
    return value["status"]


def _load_inputs(root, inputs):
    required = {"narration_file", "narration_sha256", "voice_screen_map_file", "voice_screen_map_sha256",
                "visual_asset_review_file", "visual_asset_review_sha256", "visual_direction_id",
                "visual_direction_file", "visual_direction_sha256", "visual_gate_file", "visual_gate_sha256"}
    _object(inputs, "inputs", required)
    narration_name, narration_path, narration_bytes = _relative_file(root, inputs["narration_file"], inputs["narration_sha256"], "inputs.narration")
    map_name, map_path, map_bytes = _relative_file(root, inputs["voice_screen_map_file"], inputs["voice_screen_map_sha256"], "inputs.voice_screen_map")
    asset_name, asset_path, asset_bytes = _relative_file(root, inputs["visual_asset_review_file"], inputs["visual_asset_review_sha256"], "inputs.visual_asset_review")
    _text(inputs["visual_direction_id"], "inputs.visual_direction_id")
    direction_name, _, direction_bytes = _relative_file(root, inputs["visual_direction_file"], inputs["visual_direction_sha256"], "inputs.visual_direction")
    try:
        voice_map, _ = read_json(map_path)
        asset_manifest, _ = read_json(asset_path)
    except ValidationError as exc:
        raise ValidationError(f"workflow input is invalid: {exc}") from exc
    map_report = validate_voice_screen_map(voice_map)
    if map_report["status"] != "PASS":
        raise ValidationError("voice/screen map must pass before visual-quality review")
    asset_report = load_and_validate_visual_asset_review(asset_path, narration_path, map_path)
    if asset_report["status"] != "PASS":
        raise ValidationError("Internet asset review must pass before visual-quality review")
    return {"narration_file": narration_name, "narration_sha256": hashlib.sha256(narration_bytes).hexdigest(),
            "voice_screen_map_file": map_name, "voice_screen_map_sha256": hashlib.sha256(map_bytes).hexdigest(),
            "visual_asset_review_file": asset_name, "visual_asset_review_sha256": hashlib.sha256(asset_bytes).hexdigest(),
            "visual_direction_id": inputs["visual_direction_id"], "visual_direction_file": direction_name,
            "visual_direction_sha256": hashlib.sha256(direction_bytes).hexdigest(),
            "voice_map": voice_map, "asset_manifest": asset_manifest, "asset_report": asset_report}


def _beat_selected_candidate(asset_manifest, beat_id):
    review = asset_manifest["harness_review"]["beats"]
    match = next((item for item in review if item["beat_id"] == beat_id), None)
    return None if match is None else match["selected_candidate_id"]


def _validate_screenshot_placement(placement, root, frame_width, frame_height, asset_manifest, beat_id):
    label = f"beats[{beat_id}].screenshot_placement"
    _object(placement, label, {"mode", "candidate_id", "source_file", "source_sha256", "source_crop", "display_rect", "max_zoom_factor"})
    if placement["mode"] not in {"full_screen", "focused_crop"}:
        raise ValidationError(f"{label}.mode must be full_screen or focused_crop")
    selected_id = _beat_selected_candidate(asset_manifest, beat_id)
    if placement["candidate_id"] != selected_id:
        raise ValidationError(f"{label}.candidate_id must match the reviewed asset selected for this beat")
    candidate = next((item for item in asset_manifest["candidates"] if item["id"] == selected_id), None)
    if candidate is None or candidate["kind"] != "real_ui" or candidate["authentic"] is not True:
        raise ValidationError(f"{label} requires an authentic, reviewed real_ui screenshot")
    if placement["source_sha256"] != candidate["sha256"]:
        raise ValidationError(f"{label}.source_sha256 must match the selected candidate")
    source_name, source_path, source_bytes = _relative_file(root, placement["source_file"], placement["source_sha256"], label)
    source_width, source_height = _image_dimensions(source_path, source_bytes, label + ".source_file")
    if (source_width, source_height) != (candidate["width"], candidate["height"]):
        raise ValidationError(f"{label} source header dimensions must match the reviewed candidate dimensions")
    crop_x, crop_y, crop_w, crop_h = _rect(placement["source_crop"], label + ".source_crop", source_width, source_height)
    display_x, display_y, display_w, display_h = _rect(placement["display_rect"], label + ".display_rect", frame_width, frame_height)
    zoom = _number(placement["max_zoom_factor"], label + ".max_zoom_factor", minimum=1)
    if crop_w + 1e-6 < display_w * zoom or crop_h + 1e-6 < display_h * zoom:
        raise ValidationError(f"{label} upscales source pixels at maximum planned zoom")
    scale_x, scale_y = crop_w / display_w, crop_h / display_h
    if abs(scale_x / scale_y - 1) > 0.01:
        raise ValidationError(f"{label} stretches the screenshot aspect ratio by more than 1%")
    if placement["mode"] == "full_screen":
        if display_x > frame_width * 0.02 or display_y > frame_height * 0.02 or display_x + display_w < frame_width * 0.98 or display_y + display_h < frame_height * 0.98:
            raise ValidationError(f"{label} full_screen mode must fill at least 96% of the frame")
    return {"candidate_id": selected_id, "source_file": source_name, "source_width": source_width,
            "source_height": source_height, "source_crop": [crop_x, crop_y, crop_w, crop_h],
            "display_rect": [display_x, display_y, display_w, display_h], "max_zoom_factor": zoom}


def _validate_annotations(annotations, frame_ids, frame_roles, frame_width, frame_height):
    if not isinstance(annotations, list):
        raise ValidationError("annotations must be an array")
    results, failures = [], []
    seen = set()
    scale = 1080 / frame_height
    for index, annotation in enumerate(annotations, 1):
        label = f"annotations[{index}]"
        _object(annotation, label, {"id", "kind", "samples"})
        _text(annotation["id"], f"{label}.id")
        if annotation["id"] in seen:
            raise ValidationError("annotation ids must be unique within each beat")
        seen.add(annotation["id"])
        kind = annotation["kind"]
        point_count = {"box": 4, "underline": 2, "arrow": 2}.get(kind)
        if point_count is None:
            raise ValidationError(f"{label}.kind must be box, underline, or arrow")
        if not isinstance(annotation["samples"], list) or not annotation["samples"]:
            raise ValidationError(f"{label}.samples must be non-empty")
        sampled = set()
        max_error = 0.0
        max_angle = 0.0
        for sample_index, sample in enumerate(annotation["samples"], 1):
            sample_label = f"{label}.samples[{sample_index}]"
            _object(sample, sample_label, {"frame_id", "target_points_px", "overlay_points_px", "target_bounds_px"})
            frame_id = sample["frame_id"]
            if frame_id not in frame_ids or frame_id in sampled:
                raise ValidationError(f"{sample_label}.frame_id must reference a unique evidence frame")
            sampled.add(frame_id)
            expected = _points(sample["target_points_px"], sample_label + ".target_points_px", point_count, frame_width, frame_height)
            actual = _points(sample["overlay_points_px"], sample_label + ".overlay_points_px", point_count, frame_width, frame_height)
            errors = [math.dist(exp, got) * scale for exp, got in zip(expected, actual)]
            max_error = max(max_error, *errors)
            expected_angles = _edge_angles(expected, kind == "box")
            actual_angles = _edge_angles(actual, kind == "box")
            max_angle = max(max_angle, *(_angle_delta(a, b) for a, b in zip(expected_angles, actual_angles)))
            if kind == "arrow":
                bounds = _rect(sample["target_bounds_px"], sample_label + ".target_bounds_px", frame_width, frame_height)
                tip_x, tip_y = actual[-1]
                x, y, width, height = bounds
                if not (x <= tip_x <= x + width and y <= tip_y <= y + height):
                    failures.append({"annotation_id": annotation["id"], "frame_id": frame_id, "criterion": "arrow_tip_target", "observed": [tip_x, tip_y]})
            elif sample["target_bounds_px"] is not None:
                raise ValidationError(f"{sample_label}.target_bounds_px must be null unless kind is arrow")
        required_roles = {"entry", "settled", "exit"}
        if not required_roles.issubset({frame_roles[item] for item in sampled}):
            raise ValidationError(f"{label} must be calibrated at entry, settled, and exit evidence frames")
        motion_frames = {frame_id for frame_id, role in frame_roles.items()
                         if role in {"motion_sample", "motion_extremum"}}
        if not motion_frames.issubset(sampled):
            raise ValidationError(f"{label} must be calibrated on every sampled animation/transition/extremum frame")
        if max_error > 4.0 or max_angle > 0.1:
            failures.append({"annotation_id": annotation["id"], "criterion": "annotation_calibration",
                             "max_error_at_1080p_px": round(max_error, 3), "max_rotation_error_degrees": round(max_angle, 4)})
        results.append({"id": annotation["id"], "kind": kind, "max_error_at_1080p_px": round(max_error, 3),
                        "max_rotation_error_degrees": round(max_angle, 4), "frames_checked": len(sampled)})
    return results, failures


def _validate_beat(beat, index, map_beat, root, video_meta, asset_manifest):
    label = f"beats[{index}]"
    required = {"beat_id", "frames", "screenshot_placement", "annotations", "motion", "text_px", "criteria"}
    _object(beat, label, required)
    beat_id = beat["beat_id"]
    if beat_id != map_beat["id"]:
        raise ValidationError(f"{label}.beat_id must match voice-screen map order")
    frames = beat["frames"]
    if not isinstance(frames, list) or not frames:
        raise ValidationError(f"{label}.frames must be non-empty")
    frame_ids, frame_roles, frame_times = set(), {}, {}
    for frame_index, frame in enumerate(frames, 1):
        frame_label = f"{label}.frames[{frame_index}]"
        _object(frame, frame_label, {"id", "role", "timestamp_seconds", "file", "sha256"})
        _text(frame["id"], f"{frame_label}.id")
        if frame["id"] in frame_ids:
            raise ValidationError("frame evidence ids must be unique within each beat")
        if frame["role"] not in _FRAME_ROLES:
            raise ValidationError(f"{frame_label}.role is invalid")
        timestamp = _number(frame["timestamp_seconds"], f"{frame_label}.timestamp_seconds", minimum=0)
        if timestamp > video_meta["duration_seconds"]:
            raise ValidationError(f"{frame_label}.timestamp_seconds exceeds video duration")
        name, path, data = _relative_file(root, frame["file"], frame["sha256"], frame_label)
        width, height = _image_dimensions(path, data, frame_label + ".file")
        if (width, height) != (video_meta["width"], video_meta["height"]):
            raise ValidationError(f"{frame_label}.file must match the rendered video resolution")
        frame_ids.add(frame["id"])
        frame_roles[frame["id"]] = frame["role"]
        frame_times[frame["id"]] = timestamp
    if not {"entry", "settled", "exit"}.issubset(set(frame_roles.values())):
        raise ValidationError(f"{label} needs entry, settled, and exit full-resolution frame evidence")

    placement = None
    if beat["screenshot_placement"] is not None:
        placement = _validate_screenshot_placement(beat["screenshot_placement"], root, video_meta["width"], video_meta["height"], asset_manifest, beat_id)
    else:
        selected = _beat_selected_candidate(asset_manifest, beat_id)
        selected_candidate = next((item for item in asset_manifest["candidates"] if item["id"] == selected), None)
        if selected_candidate and selected_candidate["kind"] == "real_ui":
            raise ValidationError(f"{label}.screenshot_placement is required for a real UI screenshot")

    annotation_reports, failures = _validate_annotations(beat["annotations"], frame_ids, frame_roles, video_meta["width"], video_meta["height"])
    motion = beat["motion"]
    _object(motion, label + ".motion", {"effects", "purpose", "transition_duration_seconds", "transition_exception_reason", "intervals", "static_hold_drift_px_at_1080p", "static_hold_rotation_degrees", "jitter_free", "flicker_free", "text_stable_during_hold", "readability_preserved", "evidence"})
    effects = motion["effects"]
    if not isinstance(effects, list) or not effects or any(item not in _EFFECTS for item in effects):
        raise ValidationError(f"{label}.motion.effects must be a non-empty array of known effects")
    if len(set(effects)) != len(effects):
        raise ValidationError(f"{label}.motion.effects must not contain duplicates")
    _text(motion["purpose"], label + ".motion.purpose")
    transition_duration = _number(motion["transition_duration_seconds"], label + ".motion.transition_duration_seconds", minimum=0)
    exception_reason = motion["transition_exception_reason"]
    if not isinstance(exception_reason, str):
        raise ValidationError(f"{label}.motion.transition_exception_reason must be text")
    if not 0.25 <= transition_duration <= 0.60 and len(exception_reason.strip()) < 12:
        raise ValidationError(f"{label}.motion.transition_exception_reason is required outside the default 0.25–0.60 seconds")
    _text(motion["evidence"], label + ".motion.evidence")
    intervals = motion["intervals"]
    if not isinstance(intervals, list):
        raise ValidationError(f"{label}.motion.intervals must be an array")
    for interval_index, interval in enumerate(intervals, 1):
        interval_label = f"{label}.motion.intervals[{interval_index}]"
        _object(interval, interval_label, {"start_seconds", "end_seconds"})
        start = _number(interval["start_seconds"], interval_label + ".start_seconds", minimum=0)
        end = _number(interval["end_seconds"], interval_label + ".end_seconds", minimum=0)
        if end <= start or end > video_meta["duration_seconds"]:
            raise ValidationError(f"{interval_label} must be a positive interval inside the video")
        samples = sorted(frame_times[frame_id] for frame_id, role in frame_roles.items()
                         if role in {"motion_sample", "motion_extremum"} and start <= frame_times[frame_id] <= end)
        if not samples or samples[0] - start > 0.5 or end - samples[-1] > 0.5 or any(b - a > 0.5 for a, b in zip(samples, samples[1:])):
            raise ValidationError(f"{interval_label} needs frame evidence at gaps no greater than 0.5 seconds")
        if any(effect in {"push_zoom", "pan"} for effect in effects):
            extrema = [frame_id for frame_id, role in frame_roles.items()
                       if role == "motion_extremum" and start <= frame_times[frame_id] <= end]
            if len(extrema) < 2:
                raise ValidationError(f"{interval_label} requires at least two motion_extremum frames for zoom/pan endpoints")
    if any(effect != "none" for effect in effects) and not intervals:
        raise ValidationError(f"{label}.motion requires sampled intervals for every animation/transition")
    scale = video_meta["height"] / 1080
    drift = _number(motion["static_hold_drift_px_at_1080p"], label + ".motion.static_hold_drift_px_at_1080p", minimum=0)
    rotation = _number(motion["static_hold_rotation_degrees"], label + ".motion.static_hold_rotation_degrees", minimum=0)
    for field in ("jitter_free", "flicker_free", "text_stable_during_hold", "readability_preserved"):
        if not isinstance(motion[field], bool):
            raise ValidationError(f"{label}.motion.{field} must be boolean")
        if not motion[field]:
            failures.append({"beat_id": beat_id, "criterion": field, "evidence": motion["evidence"]})
    if drift > 0.5 or rotation > 0.05:
        failures.append({"beat_id": beat_id, "criterion": "static_hold_stability",
                         "drift_px_at_1080p": drift, "rotation_degrees": rotation})

    text_px = beat["text_px"]
    _object(text_px, label + ".text_px", {"title", "body", "caption", "technical"})
    if map_beat.get("technical_display") is True and text_px["technical"] is None:
        raise ValidationError(f"{label}.text_px.technical must be measured for a technical-display beat")
    minima = {"title": 48, "body": 32, "caption": 36, "technical": 24}
    for kind, size in text_px.items():
        if size is not None and _number(size, f"{label}.text_px.{kind}", minimum=0) < minima[kind] * scale:
            failures.append({"beat_id": beat_id, "criterion": "minimum_text_size", "kind": kind, "observed_px": size,
                             "minimum_px": round(minima[kind] * scale, 2)})
    if not any(size is not None for size in text_px.values()):
        raise ValidationError(f"{label}.text_px must measure at least one visible text class")

    criteria = beat["criteria"]
    _object(criteria, label + ".criteria", _CRITERIA)
    criterion_status = {name: _review_criterion(value, f"{label}.criteria.{name}") for name, value in criteria.items()}
    failures.extend({"beat_id": beat_id, "criterion": name, "evidence": criteria[name]["evidence"]}
                    for name, status in criterion_status.items() if status == "fail")
    return {"beat_id": beat_id, "frame_count": len(frames), "annotation_checks": annotation_reports,
            "screenshot_placement": placement, "criteria": criterion_status, "failures": failures}, failures


def validate_visual_quality_review(payload, base_dir, project_root, *, ffprobe_path=None, ffmpeg_path=None, probe=None):
    """Validate render evidence, geometry, playback probe, and human review claims.

    Deterministic checks verify hashes, paths, measurements, and evidence coverage.
    Passing does not prove the visual review's semantic or aesthetic judgment.
    """
    keys = {"schema_version", "stage", "video", "inputs", "project_inventory", "beats", "review"}
    _object(payload, "visual-quality-review", keys)
    if payload["schema_version"] != 1:
        raise ValidationError("visual-quality-review schema_version must be 1")
    stage = payload["stage"]
    if stage not in {"design_sample", "final_video"}:
        raise ValidationError("stage must be design_sample or final_video")
    root = Path(base_dir).resolve()
    _object(payload["video"], "video", {"file", "sha256"})
    video_name, video_path, video_data = _relative_file(root, payload["video"]["file"], payload["video"]["sha256"], "video")
    if video_path.suffix.lower() not in {".mp4", ".m4v", ".mov"} or len(video_data) < 12 or video_data[4:8] != b"ftyp":
        raise ValidationError("video.file must be an MP4-family file with a valid ftyp signature")
    input_report = _load_inputs(root, payload["inputs"])
    gate_file, gate_sha = payload["inputs"]["visual_gate_file"], payload["inputs"]["visual_gate_sha256"]
    if stage == "design_sample":
        if gate_file is not None or gate_sha is not None:
            raise ValidationError("design_sample quality review must not refer to a later visual gate")
    else:
        _text(gate_file, "inputs.visual_gate_file")
        _sha(gate_sha, "inputs.visual_gate_sha256")

    _object(payload["project_inventory"], "project_inventory_reference", {"file", "sha256"})
    inventory = _project_inventory(root, payload["project_inventory"]["file"], payload["project_inventory"]["sha256"], project_root)
    actual_probe = probe if probe is not None else _probe_video(video_path, ffprobe_path)
    video_meta = _probe_metadata(actual_probe, stage)
    map_beats = input_report["voice_map"]["beats"]
    beats = payload["beats"]
    if not isinstance(beats, list) or not beats:
        raise ValidationError("visual-quality review beats must be a non-empty array")
    map_by_id = {item["id"]: item for item in map_beats}
    beat_ids = [item.get("beat_id") if isinstance(item, dict) else None for item in beats]
    if len(set(beat_ids)) != len(beat_ids) or any(item not in map_by_id for item in beat_ids):
        raise ValidationError("visual-quality review beat ids must be unique ids from the voice/screen map")
    ordered_ids = [item["id"] for item in map_beats if item["id"] in set(beat_ids)]
    if beat_ids != ordered_ids:
        raise ValidationError("visual-quality review beats must follow voice/screen map order")
    if stage == "final_video" and beat_ids != [item["id"] for item in map_beats]:
        raise ValidationError("final_video review must cover every voice/screen beat exactly once")
    if stage == "design_sample" and len(beats) < 3:
        raise ValidationError("design sample quality review must cover at least three representative beats")
    frame_refs = _video_frame_indices(beats, video_meta["fps"])
    _verify_video_frame_pixels(video_path, frame_refs, beats, root, video_meta, ffmpeg_path)
    beat_reports, all_failures = [], []
    for index, beat in enumerate(beats, 1):
        map_beat = map_by_id[beat["beat_id"]]
        report, failures = _validate_beat(beat, index, map_beat, root, video_meta,
                                          input_report["asset_manifest"])
        beat_reports.append(report)
        all_failures.extend(failures)
        if stage == "final_video":
            start = sum(float(item["duration_seconds"]) for item in map_beats[:index - 1])
            end = start + float(map_beat["duration_seconds"])
            timestamps = [float(frame["timestamp_seconds"]) for frame in beat["frames"]]
            if min(timestamps) < start - 0.5 or max(timestamps) > end + 0.5:
                raise ValidationError(f"beats[{index}] frame evidence must fall within its mapped scene timing (±0.5 seconds)")

    review = payload["review"]
    _object(review, "review", {"harness_id", "reviewed_at", "decision", "self_evaluation", "watched_video_at_1x", "sample_coverage", "findings"})
    _text(review["harness_id"], "review.harness_id")
    _text(review["reviewed_at"], "review.reviewed_at")
    if review["decision"] not in {"pass", "needs_revision"}:
        raise ValidationError("review.decision must be pass or needs_revision")
    _object(review["self_evaluation"], "review.self_evaluation", {"status", "dimensions", "open_findings"})
    if review["self_evaluation"]["status"] not in {"PASS", "FAIL"}:
        raise ValidationError("review.self_evaluation.status must be PASS or FAIL")
    if not isinstance(review["self_evaluation"]["dimensions"], dict) or not review["self_evaluation"]["dimensions"]:
        raise ValidationError("review.self_evaluation.dimensions must be a non-empty object")
    open_findings = review["self_evaluation"]["open_findings"]
    if not isinstance(open_findings, list) or any(not isinstance(item, str) or not item.strip() for item in open_findings):
        raise ValidationError("review.self_evaluation.open_findings must be an array of non-empty strings")
    if not isinstance(review["watched_video_at_1x"], bool):
        raise ValidationError("review.watched_video_at_1x must be boolean")
    if not review["watched_video_at_1x"]:
        all_failures.append({"criterion": "full_video_playback_review", "evidence": "The complete video has not been watched at 1× speed."})
    sample_coverage = review["sample_coverage"]
    if stage == "design_sample":
        categories = {"real_ui", "technical_display", "annotations", "motion", "captions"}
        _object(sample_coverage, "review.sample_coverage", categories)
        for category, item in sample_coverage.items():
            status = _review_criterion(item, f"review.sample_coverage.{category}")
            if status == "fail":
                all_failures.append({"criterion": "sample_coverage." + category, "evidence": item["evidence"]})
        all_map_ids = [item["id"] for item in map_beats]
        source_selected_ids = {_beat_selected_candidate(input_report["asset_manifest"], beat_id) for beat_id in all_map_ids}
        source_candidates = [item for item in input_report["asset_manifest"]["candidates"] if item["id"] in source_selected_ids]
        source_has_real_ui = any(item["kind"] == "real_ui" and item["authentic"] is True for item in source_candidates)
        sample_selected_ids = {_beat_selected_candidate(input_report["asset_manifest"], item["beat_id"]) for item in beats}
        sample_candidates = [item for item in input_report["asset_manifest"]["candidates"] if item["id"] in sample_selected_ids]
        has_real_ui = any(item["kind"] == "real_ui" and item["authentic"] is True for item in sample_candidates)
        source_has_technical = any(item.get("technical_display") is True for item in map_beats)
        has_technical = any(map_by_id[item["beat_id"]].get("technical_display") is True for item in beats)
        source_has_annotations = source_has_real_ui and any(str(item.get("focus", "")).strip() for item in map_beats)
        has_annotations = any(item["annotations"] for item in beats)
        source_has_motion = any(str(item.get("transition", {}).get("motion", "static")).casefold() not in {"static", "none"}
                                for item in map_beats)
        has_motion = any(any(effect != "none" for effect in item["motion"]["effects"]) for item in beats)
        source_has_captions = any(item.get("voice_mode") in {"summary", "verbatim"} for item in map_beats)
        has_captions = any(item["text_px"]["caption"] is not None for item in beats)
        if source_has_real_ui and not has_real_ui:
            all_failures.append({"criterion": "representative_sample.real_ui", "evidence": "The complete lesson uses genuine product UI; at least one real UI beat must appear in the sample."})
        if source_has_technical and not has_technical:
            all_failures.append({"criterion": "representative_sample.technical_display", "evidence": "The voice/screen map contains technical-display content; at least one such beat must appear in the sample."})
        if source_has_annotations and not has_annotations:
            all_failures.append({"criterion": "representative_sample.annotations", "evidence": "The real UI lesson needs annotations; at least one calibrated annotation must appear in the sample."})
        if source_has_captions and not has_captions:
            all_failures.append({"criterion": "representative_sample.captions", "evidence": "The spoken lesson needs captions; at least one caption must appear in the sample."})
        available = {"real_ui": source_has_real_ui or has_real_ui,
                     "technical_display": source_has_technical or has_technical,
                     "annotations": source_has_annotations or has_annotations,
                     "motion": source_has_motion or has_motion,
                     "captions": source_has_captions or has_captions}
        for category, exists in available.items():
            status = sample_coverage[category]["status"]
            if exists and status != "pass":
                all_failures.append({"criterion": "representative_sample." + category,
                                     "evidence": "The source workflow contains this teaching element; the sample must demonstrate it."})
            if not exists and status != "not_applicable":
                all_failures.append({"criterion": "representative_sample." + category,
                                     "evidence": "The source workflow has no such element; mark not_applicable with a reason."})
    elif sample_coverage is not None:
        raise ValidationError("final_video review sample_coverage must be null")
    findings = review["findings"]
    if not isinstance(findings, list) or any(not isinstance(item, dict) for item in findings):
        raise ValidationError("review.findings must be an array of finding objects")
    all_failures.extend(findings)
    if review["decision"] != "pass" or review["self_evaluation"]["status"] != "PASS" or open_findings or all_failures:
        details = {"schema_version": 1, "status": "AWAITING_HUMAN", "gate": "visual_quality_review",
                   "stage": stage, "video_file": video_name, "video_sha256": payload["video"]["sha256"],
                   "probe": video_meta, "issues": all_failures or [{"criterion": "harness_self_evaluation", "evidence": "Review is not PASS or has open findings."}],
                   "instruction": "Show the concrete issue evidence, revise the affected render, and submit a new hash-bound quality review. Do not approve the design sample or deliver the final video while this packet is pending."}
        raise HumanReviewRequired(details)

    report = {"schema_version": 1, "status": "PASS", "stage": stage, "gate": "design_sample_quality_passed" if stage == "design_sample" else "video_delivery_allowed",
              "video_file": video_name, "video_sha256": payload["video"]["sha256"], "probe": video_meta,
              "project_inventory": inventory, "inputs": {key: input_report[key] for key in ("narration_file", "narration_sha256", "voice_screen_map_file", "voice_screen_map_sha256", "visual_asset_review_file", "visual_asset_review_sha256", "visual_direction_id", "visual_direction_file", "visual_direction_sha256")},
              "beats": beat_reports, "reviewed_by": review["harness_id"]}
    if stage == "final_video":
        gate_name, gate_path, gate_bytes = _relative_file(root, gate_file, gate_sha, "inputs.visual_gate")
        gate_payload, _ = read_json(gate_path)
        from .visual_gate import validate_visual_gate
        gate_report = validate_visual_gate(gate_payload, root, project_root=project_root,
                                           ffprobe_path=ffprobe_path, ffmpeg_path=ffmpeg_path)
        if gate_report["status"] != "PASS":
            raise ValidationError("final_video review requires the approved design-sample visual gate")
        if gate_payload["asset_review"]["manifest_sha256"] != payload["inputs"]["visual_asset_review_sha256"]:
            raise ValidationError("final render asset review must match the approved design sample")
        for key in ("narration_file", "narration_sha256", "voice_screen_map_file", "voice_screen_map_sha256"):
            if input_report[key] != gate_payload["asset_review"][key]:
                raise ValidationError(f"final render {key} must match the approved design sample")
        selected_option = next(item for item in gate_payload["options"] if item["id"] == gate_report["selected_option_id"])
        if (input_report["visual_direction_id"] != selected_option["id"]
                or input_report["visual_direction_file"] != selected_option["image_file"]
                or input_report["visual_direction_sha256"] != selected_option["sha256"]):
            raise ValidationError("final render visual direction must match the option explicitly selected and approved in the sample gate")
        sample_quality_path = root / gate_payload["design_sample"]["quality_review_file"]
        sample_quality, _ = read_json(sample_quality_path)
        if sample_quality["project_inventory"]["sha256"] != payload["project_inventory"]["sha256"]:
            raise ValidationError("final render must use the same HyperFrames project inventory as the approved design sample")
        report["visual_gate_file"] = gate_name
        report["visual_gate_sha256"] = hashlib.sha256(gate_bytes).hexdigest()
        report["selected_option_id"] = gate_report["selected_option_id"]
    return report


def load_and_validate_visual_quality_review(manifest_path, *, project_root, ffprobe_path=None, ffmpeg_path=None):
    manifest_path = Path(manifest_path).resolve()
    try:
        manifest, _ = read_json(manifest_path)
    except ValidationError as exc:
        raise ValidationError(f"visual-quality-review is invalid: {exc}") from exc
    return validate_visual_quality_review(manifest, manifest_path.parent, project_root,
                                          ffprobe_path=ffprobe_path, ffmpeg_path=ffmpeg_path)
