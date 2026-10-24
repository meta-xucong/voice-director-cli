"""Structural validation for harness-authored, cross-beat visual sequences."""

import math

from .errors import ValidationError


_STAGES = ("context_a", "detail_a", "context_b", "detail_b", "synthesis")
_MOVEMENTS = {"source_linked_zoom", "mask_reveal", "matched_push", "slide_align"}
_MAX_PIXEL_DIMENSION = 1_000_000


def _object(value, label):
    if not isinstance(value, dict):
        raise ValidationError(f"{label} must be an object")
    return value


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} must be a non-empty string")
    return value


def _number(value, label, *, minimum=0, maximum=None):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or (isinstance(value, float) and not math.isfinite(value)) or value < minimum):
        raise ValidationError(f"{label} must be a finite number >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValidationError(f"{label} must be <= {maximum}")
    return value


def validate_visual_sequences(payload):
    """Validate a visual-sequence declaration without asserting semantic quality.

    The harness authors the sequence after interpreting the narration and reviewing
    assets. This function only verifies declared structure, evidence links and geometry.
    """
    sequences = payload.get("visual_sequences", [])
    if not isinstance(sequences, list):
        raise ValidationError("visual_sequences must be an array")

    beats = payload.get("beats", [])
    by_id = {beat["id"]: (index, beat) for index, beat in enumerate(beats)}
    seen_ids = set()
    reports = []
    for sequence_index, sequence in enumerate(sequences, 1):
        prefix = f"visual_sequences[{sequence_index}]"
        sequence = _object(sequence, prefix)
        sequence_id = _text(sequence.get("id"), f"{prefix}.id")
        if sequence_id in seen_ids:
            raise ValidationError(f"duplicate visual sequence id: {sequence_id}")
        seen_ids.add(sequence_id)
        if sequence.get("pattern") != "contrast_reveal":
            raise ValidationError(f"{prefix}.pattern must be contrast_reveal")
        _text(sequence.get("trigger"), f"{prefix}.trigger")
        _text(sequence.get("takeaway"), f"{prefix}.takeaway")

        stage_beats = _object(sequence.get("stage_beats"), f"{prefix}.stage_beats")
        if set(stage_beats) != set(_STAGES):
            raise ValidationError(f"{prefix}.stage_beats must declare exactly {_STAGES}")
        stage_ids = [_text(stage_beats[stage], f"{prefix}.stage_beats.{stage}") for stage in _STAGES]
        unknown = [beat_id for beat_id in stage_ids if beat_id not in by_id]
        if unknown:
            raise ValidationError(f"{prefix} references unknown beat {unknown[0]}")
        indices = [by_id[beat_id][0] for beat_id in stage_ids]
        if indices != sorted(indices) or len(set(indices)) != len(_STAGES):
            raise ValidationError(f"{prefix}.stage_beats must reference five distinct beats in teaching order")
        for stage in _STAGES:
            beat_id = _text(stage_beats[stage], f"{prefix}.stage_beats.{stage}")
            _, beat = by_id[beat_id]
            marker = _object(beat.get("visual_sequence"), f"beats[{beat_id}].visual_sequence")
            if marker.get("id") != sequence_id or marker.get("stage") != stage:
                raise ValidationError(f"beat {beat_id} is not marked as {sequence_id}/{stage}")
            expected_participant = ("a" if stage.endswith("_a") else "b" if stage.endswith("_b") else None)
            if expected_participant and marker.get("participant_id") != expected_participant:
                raise ValidationError(f"beat {beat_id} must name participant {expected_participant}")
            _number(beat.get("duration_seconds"), f"beat {beat_id}.duration_seconds", minimum=1.5, maximum=12)
        participants = sequence.get("participants")
        if not isinstance(participants, list) or len(participants) != 2:
            raise ValidationError(f"{prefix}.participants must contain exactly two participants")
        participant_ids = set()
        for participant_index, participant in enumerate(participants, 1):
            pfx = f"{prefix}.participants[{participant_index}]"
            participant = _object(participant, pfx)
            participant_id = _text(participant.get("id"), f"{pfx}.id")
            if participant_id in participant_ids:
                raise ValidationError(f"{prefix} participant ids must be distinct")
            participant_ids.add(participant_id)
            _text(participant.get("label"), f"{pfx}.label")
            if participant.get("authentic") is not True:
                raise ValidationError(f"{pfx} must be marked authentic")
            source = _text(participant.get("asset_source"), f"{pfx}.asset_source")
            _text(participant.get("focus"), f"{pfx}.focus")
            context_stage, detail_stage = (("context_a", "detail_a") if participant_index == 1
                                            else ("context_b", "detail_b"))
            for stage in (context_stage, detail_stage):
                stage_id = stage_beats[stage]
                stage_beat = by_id[stage_id][1]
                matches = [asset for asset in stage_beat.get("assets", [])
                           if asset.get("kind") == "real_ui" and asset.get("source") == source
                           and asset.get("authentic") is True]
                if not matches:
                    raise ValidationError(f"{pfx}.asset_source must match an authentic real_ui asset in {stage}")

            regions = participant.get("source_pixel_regions")
            if not isinstance(regions, list) or not regions:
                raise ValidationError(f"{pfx}.source_pixel_regions must be a non-empty array")
            region_ids = set()
            for region_index, region in enumerate(regions, 1):
                rfx = f"{pfx}.source_pixel_regions[{region_index}]"
                region = _object(region, rfx)
                region_id = _text(region.get("id"), f"{rfx}.id")
                if region_id in region_ids:
                    raise ValidationError(f"{pfx}.source_pixel_regions ids must be distinct")
                region_ids.add(region_id)
                _text(region.get("purpose"), f"{rfx}.purpose")
                crop = _object(region.get("crop"), f"{rfx}.crop")
                if crop.get("coordinate_space") != "source_pixels":
                    raise ValidationError(f"{rfx}.crop.coordinate_space must be source_pixels")
                x = _number(crop.get("x"), f"{rfx}.crop.x", maximum=_MAX_PIXEL_DIMENSION)
                y = _number(crop.get("y"), f"{rfx}.crop.y", maximum=_MAX_PIXEL_DIMENSION)
                width = _number(crop.get("width"), f"{rfx}.crop.width", minimum=1, maximum=_MAX_PIXEL_DIMENSION)
                height = _number(crop.get("height"), f"{rfx}.crop.height", minimum=1, maximum=_MAX_PIXEL_DIMENSION)
                source_width = _number(crop.get("source_width"), f"{rfx}.crop.source_width", minimum=1, maximum=_MAX_PIXEL_DIMENSION)
                source_height = _number(crop.get("source_height"), f"{rfx}.crop.source_height", minimum=1, maximum=_MAX_PIXEL_DIMENSION)
                display_width = _number(crop.get("display_width"), f"{rfx}.crop.display_width", minimum=1, maximum=_MAX_PIXEL_DIMENSION)
                display_height = _number(crop.get("display_height"), f"{rfx}.crop.display_height", minimum=1, maximum=_MAX_PIXEL_DIMENSION)
                if x + width > source_width or y + height > source_height:
                    raise ValidationError(f"{rfx}.crop extends beyond its source image")
                if width < display_width or height < display_height:
                    raise ValidationError(f"{rfx}.crop would be upscaled at the planned display size")
                if abs(width / height - display_width / display_height) > (width / height) * 0.01:
                    raise ValidationError(f"{rfx}.crop display aspect ratio must stay within 1% of its source crop")

        synthesis = by_id[stage_beats["synthesis"]][1]
        for participant in participants:
            if not any(asset.get("kind") == "real_ui" and asset.get("source") == participant["asset_source"]
                       and asset.get("authentic") is True for asset in synthesis.get("assets", [])):
                raise ValidationError(f"synthesis beat must retain both authentic participant screenshots")

        motion = _object(sequence.get("motion"), f"{prefix}.motion")
        movement = _text(motion.get("movement"), f"{prefix}.motion.movement")
        if movement not in _MOVEMENTS:
            raise ValidationError(f"{prefix}.motion.movement must be one of {sorted(_MOVEMENTS)}")
        context_hold = _number(motion.get("context_hold_seconds"), f"{prefix}.motion.context_hold_seconds", minimum=1.2, maximum=4.5)
        reframe = _number(motion.get("reframe_seconds"), f"{prefix}.motion.reframe_seconds", minimum=0.25, maximum=0.9)
        if "region_stagger_seconds" in motion:
            _number(motion["region_stagger_seconds"], f"{prefix}.motion.region_stagger_seconds", minimum=0, maximum=0.8)
        detail_hold = _number(motion.get("detail_hold_seconds"), f"{prefix}.motion.detail_hold_seconds", minimum=1.5, maximum=8)
        synthesis_hold = _number(motion.get("synthesis_hold_seconds"), f"{prefix}.motion.synthesis_hold_seconds", minimum=2, maximum=8)
        for stage in ("context_a", "context_b"):
            if context_hold + reframe > by_id[stage_beats[stage]][1]["duration_seconds"]:
                raise ValidationError(f"{prefix}.motion context hold and reframe exceed the {stage} beat duration")
        if detail_hold > by_id[stage_beats["detail_a"]][1]["duration_seconds"] or detail_hold > by_id[stage_beats["detail_b"]][1]["duration_seconds"]:
            raise ValidationError(f"{prefix}.motion.detail_hold_seconds exceeds a detail beat duration")
        if synthesis_hold > synthesis["duration_seconds"]:
            raise ValidationError(f"{prefix}.motion.synthesis_hold_seconds exceeds the synthesis beat duration")
        uncertainty = sequence.get("uncertainty")
        if uncertainty is not None:
            uncertainty = _object(uncertainty, f"{prefix}.uncertainty")
            for key in ("question", "evidence", "impact", "recommendation"):
                _text(uncertainty.get(key), f"{prefix}.uncertainty.{key}")
            decision_status = _text(uncertainty.get("decision_status", "pending"),
                                    f"{prefix}.uncertainty.decision_status")
            if decision_status not in {"pending", "resolved"}:
                raise ValidationError(f"{prefix}.uncertainty.decision_status must be pending or resolved")
        reports.append({"id": sequence_id, "pattern": "contrast_reveal", "stages": list(_STAGES),
                        "beat_ids": [stage_beats[stage] for stage in _STAGES],
                        "participant_labels": [participant["label"] for participant in participants],
                        "region_ids": [[region["id"] for region in participant["source_pixel_regions"]]
                                       for participant in participants],
                        "uncertainty": uncertainty})
    return reports
