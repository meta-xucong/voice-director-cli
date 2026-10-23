"""Synthetic evidence builders shared by the visual-gate tests."""

import hashlib
import json
from pathlib import Path


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
VIDEO_PROBE = {"streams": [{"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080,
                            "avg_frame_rate": "30/1", "r_frame_rate": "30/1", "field_order": "progressive",
                            "duration": "24.0"}], "format": {"duration": "24.0"}}


def png(width, height):
    return (PNG_SIGNATURE + (13).to_bytes(4, "big") + b"IHDR" + width.to_bytes(4, "big") + height.to_bytes(4, "big")
            + bytes([8, 2, 0, 0, 0]) + b"\x00\x00\x00\x00" + b"\x00\x00\x00\x00IEND\xaeB`\x82")


def direction_data(index):
    return png(1920, 1080) + f"direction-{index}".encode("ascii")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fake_video_frames(video_path, frame_refs, video_meta, ffmpeg_path, consume, **kwargs):
    for _, _, _, frame_index in frame_refs:
        consume(frame_index, b"identical-rgb-pixels")


def fake_image_pixels(path, width, height, ffmpeg_path=None):
    return b"identical-rgb-pixels"


def write_json(path, value):
    data = (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    path.write_bytes(data)
    return sha(data)


def make_asset_inputs(root):
    from tests.test_visual_asset_review import fixture

    payload, narration, voice_map = fixture(root, query_count=3)
    voice_map["beats"].append(dict(voice_map["beats"][0], id="B02", screen_text="Read the second interface beat."))
    voice_map["beats"].append(dict(voice_map["beats"][0], id="B03", screen_text="Review the final interface beat."))
    map_path = root / "voice-screen-map.json"
    map_hash = write_json(map_path, voice_map)
    payload["voice_screen_map_sha256"] = map_hash
    payload["harness_review"]["voice_screen_map_sha256"] = map_hash
    for item in payload["searches"]:
        item["beat_ids"] = ["B01", "B02", "B03"]
    payload["candidates"][0]["beat_ids"] = ["B01", "B02", "B03"]
    review_beats = payload["harness_review"]["beats"]
    for beat_id in ("B02", "B03"):
        review_beats.append(dict(review_beats[0], beat_id=beat_id))
    source = png(1920, 1080)
    (root / "codex.png").write_bytes(source)
    payload["candidates"][0]["sha256"] = sha(source)
    narration_path = root / "narration.txt"
    asset_path = root / "visual-asset-review.json"
    write_json(asset_path, payload)
    return narration_path, map_path, asset_path, voice_map, payload


def make_project(root):
    project_root = root / "hyperframes-project"
    project_root.mkdir(exist_ok=True)
    code = b"export const example = true;\n"
    (project_root / "composition.js").write_bytes(code)
    inventory = {"schema_version": 1, "files": [{"path": "composition.js", "sha256": sha(code), "role": "composition"}]}
    inventory_hash = write_json(root / "project-inventory.json", inventory)
    return project_root, {"file": "project-inventory.json", "sha256": inventory_hash}


def make_video(root, name="design-sample.mp4"):
    data = b"\x00\x00\x00\x18ftypmp42" + b"synthetic-video"
    path = root / name
    path.write_bytes(data)
    return {"file": path.name, "sha256": sha(data)}


def quality_beat(root, beat, start, *, animated=True, annotation=True):
    frames, frame_ids, frame_roles, frame_times = [], {}, {}, {}
    schedules = [("entry", start), ("settled", start + 4), ("exit", start + 8)]
    if animated:
        schedules += [("motion_sample", start + 0.25), ("motion_sample", start + 0.75), ("motion_sample", start + 1.25)]
    for index, (role, timestamp) in enumerate(schedules, 1):
        frame_id = f"{beat['id']}-F{index}"
        filename = f"{frame_id}.png"
        data = png(1920, 1080) + f"frame-{frame_id}".encode("ascii")
        (root / filename).write_bytes(data)
        frames.append({"id": frame_id, "role": role, "timestamp_seconds": timestamp, "file": filename, "sha256": sha(data)})
        frame_ids[role + str(index)] = frame_id
        frame_roles[frame_id] = role
        frame_times[frame_id] = timestamp
    annotations = []
    if annotation:
        target = [{"x": 100, "y": 100}, {"x": 300, "y": 100}, {"x": 300, "y": 200}, {"x": 100, "y": 200}]
        annotations = [{"id": beat["id"] + "-box", "kind": "box", "samples": [
            {"frame_id": frame["id"], "target_points_px": target, "overlay_points_px": target, "target_bounds_px": None}
            for frame in frames]}]
    motion = {"effects": ["fade"] if animated else ["none"], "purpose": "Orient the learner to this screen." if animated else "Keep the interface stable while the learner reads.",
              "transition_duration_seconds": 0.4, "transition_exception_reason": "", "intervals": [],
              "static_hold_drift_px_at_1080p": 0.2, "static_hold_rotation_degrees": 0.01,
              "jitter_free": True, "flicker_free": True, "text_stable_during_hold": True,
              "readability_preserved": True, "evidence": "Entry, midpoint, exit, and motion frames show stable text and overlays."}
    if animated:
        motion["intervals"] = [{"start_seconds": start + 0.25, "end_seconds": start + 1.25}]
    criteria = {name: {"status": "pass", "evidence": f"Inspected {name} at full output resolution; criterion passes."} for name in (
        "selected_direction_consistency", "visual_hierarchy", "spacing_alignment", "typography", "color_consistency", "clean_edges",
        "screenshot_readability", "caption_legibility", "crop_safety", "authenticity", "motion_quality", "pacing")}
    return {"beat_id": beat["id"], "frames": frames,
            "screenshot_placement": {"mode": "full_screen", "candidate_id": "C01", "source_file": "codex.png",
                                     "source_sha256": sha((root / "codex.png").read_bytes()),
                                     "source_crop": {"x": 0, "y": 0, "width": 1920, "height": 1080},
                                     "display_rect": {"x": 0, "y": 0, "width": 1920, "height": 1080}, "max_zoom_factor": 1},
            "annotations": annotations, "motion": motion,
            "text_px": {"title": 56, "body": 36, "caption": 40, "technical": 26}, "criteria": criteria}


def make_quality_review(root, *, stage="design_sample", video=None, gate_file=None, gate_sha=None):
    narration_path, map_path, asset_path, voice_map, asset_manifest = make_asset_inputs(root)
    project_root, inventory = make_project(root)
    direction_path = root / "option-1.png"
    direction_bytes = direction_data(1)
    direction_path.write_bytes(direction_bytes)
    video = video or make_video(root)
    narration_bytes, map_bytes, asset_bytes = narration_path.read_bytes(), map_path.read_bytes(), asset_path.read_bytes()
    beats = [quality_beat(root, beat, index * 8) for index, beat in enumerate(voice_map["beats"])]
    inputs = {"narration_file": narration_path.name, "narration_sha256": sha(narration_bytes),
              "voice_screen_map_file": map_path.name, "voice_screen_map_sha256": sha(map_bytes),
              "visual_asset_review_file": asset_path.name, "visual_asset_review_sha256": sha(asset_bytes),
              "visual_direction_id": "1", "visual_direction_file": direction_path.name,
              "visual_direction_sha256": sha(direction_bytes),
              "visual_gate_file": gate_file, "visual_gate_sha256": gate_sha}
    sample_coverage = {name: {"status": "not_applicable" if name == "technical_display" else "pass",
                              "evidence": ("The voice/screen map contains no technical-display beat in this sample." if name == "technical_display"
                                           else f"Representative sample visibly covers {name}.")}
                       for name in ("real_ui", "technical_display", "annotations", "motion", "captions")}
    payload = {"schema_version": 1, "stage": stage, "video": video, "inputs": inputs,
               "project_inventory": inventory, "beats": beats,
               "review": {"harness_id": "visual-quality-harness", "reviewed_at": "2026-10-24T11:00:00+08:00",
                          "decision": "pass", "self_evaluation": {"status": "PASS", "dimensions": {"coverage": "Every selected beat checked."}, "open_findings": []},
                          "watched_video_at_1x": True, "sample_coverage": sample_coverage if stage == "design_sample" else None,
                          "findings": []}}
    quality_path = root / ("sample-quality.json" if stage == "design_sample" else "final-quality.json")
    quality_hash = write_json(quality_path, payload)
    return payload, quality_path, quality_hash, project_root, inventory, voice_map, asset_path


def make_visual_gate(root, quality_path, quality_hash, *, decision="approved"):
    asset = root / "visual-asset-review.json"
    narration = root / "narration.txt"
    voice_map = root / "voice-screen-map.json"
    options = []
    for index in range(1, 4):
        path = root / f"option-{index}.png"
        data = direction_data(index)
        path.write_bytes(data)
        options.append({"id": str(index), "title": f"Direction {index}", "image_file": path.name, "sha256": sha(data)})
    sample_path = root / "design-sample.mp4"
    sample_data = sample_path.read_bytes()
    manifest = {"schema_version": 2,
                "asset_review": {"manifest_file": asset.name, "manifest_sha256": sha(asset.read_bytes()),
                                 "narration_file": narration.name, "narration_sha256": sha(narration.read_bytes()),
                                 "voice_screen_map_file": voice_map.name, "voice_screen_map_sha256": sha(voice_map.read_bytes())},
                "options": options, "selected_option_id": "1",
                "design_sample": {"video_file": sample_path.name, "sha256": sha(sample_data), "based_on_option_id": "1",
                                  "quality_review_file": quality_path.name, "quality_review_sha256": quality_hash,
                                  "decision_status": decision}}
    gate_path = root / "visual-gate.json"
    gate_hash = write_json(gate_path, manifest)
    return manifest, gate_path, gate_hash
