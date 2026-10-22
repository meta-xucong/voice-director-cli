"""Offline backend draft compilers. No provider or model calls live here."""

import re
import xml.etree.ElementTree as ET

from .errors import ValidationError
from .profiles import CONTROL_NAMES, get_license_review, get_profile

_AZURE_NS = "http://www.w3.org/2001/10/synthesis"
_MSTTS_NS = "http://www.w3.org/2001/mstts"
ET.register_namespace("mstts", _MSTTS_NS)
ET.register_namespace("", _AZURE_NS)


def _requested(segment, control):
    if control in ("delivery", "energy", "pace", "function"):
        return control in segment
    if control == "emphasis":
        return bool(segment.get("emphasis_spans"))
    if control == "pauses":
        return bool(segment.get("pauses"))
    if control == "pronunciation_overrides":
        return bool(segment.get("pronunciation_overrides"))
    if control == "fish_tags":
        return bool(segment.get("fish_tags"))
    return False


def _control_report(backend, director, per_control_overrides=None):
    profile = get_profile(backend)
    if profile is None:
        controls = {}
        for name in CONTROL_NAMES:
            requested = any(_requested(segment, name) for segment in director["segments"])
            controls[name] = {
                "status": "unsupported" if requested else "not_requested",
                "requested": requested,
                "reason": "unknown backend; no automatic backend selection",
            }
        return {
            "backend": backend,
            "supported": False,
            "profile_id": None,
            "evidence": None,
            "license_review": get_license_review(backend),
            "controls": controls,
            "warnings": ["Unknown backend. No fallback or provider call was attempted."],
        }

    controls = {}
    overrides = per_control_overrides or {}
    for name in CONTROL_NAMES:
        requested = any(_requested(segment, name) for segment in director["segments"])
        if not requested:
            status = "not_requested"
        else:
            status = profile["capabilities"].get(name, "unsupported")
        extra = overrides.get(name)
        detail = {"status": status, "requested": requested}
        if extra:
            detail.update(extra)
        if status == "unsupported" and requested and "reason" not in detail:
            detail["reason"] = "backend profile does not define a safe supported control for this request"
        controls[name] = detail
    return {
        "backend": backend,
        "supported": True,
        "profile_id": profile["profile_id"],
        "evidence": profile["evidence"],
        "license_review": profile["license_review"],
        "controls": controls,
        "notes": profile.get("notes", []),
    }


def _segment_records(source, director):
    return [
        {
            "id": segment["id"],
            "start": segment["start"],
            "end": segment["end"],
            "text": source[segment["start"]:segment["end"]],
            "delivery": segment.get("delivery"),
            "function": segment.get("function"),
            "energy": segment.get("energy"),
            "pace": segment.get("pace"),
            "emphasis_spans": list(segment.get("emphasis_spans", [])),
            "pauses": [dict(pause) for pause in segment.get("pauses", [])],
            "pronunciation_overrides": [dict(item) for item in segment.get("pronunciation_overrides", [])],
            "fish_tags": list(segment.get("fish_tags", [])),
        }
        for segment in director["segments"]
    ]


def _collision_tokens(source, tokens):
    return sorted(token for token in set(tokens) if token in source)


def _eleven_cue_tag(segment):
    values = []
    delivery = segment.get("delivery")
    energy = segment.get("energy")
    pace = segment.get("pace")
    emphasis_spans = segment.get("emphasis_spans", [])

    for value in [delivery, pace, *emphasis_spans]:
        if value is not None and ("[" in value or "]" in value):
            raise ValidationError(
                f"Eleven v4 cue values in segment {segment['id']} must not contain '[' or ']'"
            )
    if delivery:
        values.append(f"请采用“{delivery}”的表达方式")
    if energy is not None:
        values.append(f"表达能量等级为 {energy}")
    if pace:
        values.append(f"语速倾向为“{pace}”")
    if emphasis_spans:
        emphasized = "、".join(f"“{span}”" for span in emphasis_spans)
        values.append(f"请适度突出{emphasized}，不要求逐词精确重音")
    if not values:
        return None
    return "[voice_director: " + "；".join(values) + "]"


def _build_eleven_draft(source, segments, cue_tags, pause_tag_for_kind):
    events = []
    sequence = 0
    for segment in segments:
        cue = cue_tags.get(segment["id"])
        if cue:
            events.append((segment["start"], 1, sequence, cue))
            sequence += 1
        for pause in segment.get("pauses", []):
            events.append((pause["after"], 0, sequence, pause_tag_for_kind(pause["kind"])))
            sequence += 1
    events.sort(key=lambda item: (item[0], item[1], item[2]))
    parts = []
    cursor = 0
    for offset, _priority, _sequence, tag in events:
        parts.append(source[cursor:offset])
        parts.append(tag)
        cursor = offset
    parts.append(source[cursor:])
    return "".join(parts)


def _build_azure_ssml(source, director):
    for index, char in enumerate(source):
        codepoint = ord(char)
        valid_xml_char = (
            codepoint in (0x9, 0xA, 0xD)
            or 0x20 <= codepoint <= 0xD7FF
            or 0xE000 <= codepoint <= 0xFFFD
            or 0x10000 <= codepoint <= 0x10FFFF
        )
        if not valid_xml_char:
            raise ValidationError(f"source contains a character forbidden by XML 1.0 at code-point offset {index}")
    voice_profile = director["voice_profile"]
    voice_name = voice_profile.get("azure_voice")
    if not voice_name:
        raise ValidationError("Azure compilation requires voice_profile.azure_voice so the SSML selects an explicit voice")
    if any(char in voice_name for char in "\r\n\t"):
        raise ValidationError("voice_profile.azure_voice cannot contain XML attribute whitespace")

    root = ET.Element(
        f"{{{_AZURE_NS}}}speak",
        {"version": "1.0", "xml:lang": "zh-CN"},
    )
    voice = ET.SubElement(root, f"{{{_AZURE_NS}}}voice", {"name": voice_name})
    style = voice_profile.get("azure_style")
    container = voice
    if style:
        if any(char in style for char in "\r\n\t"):
            raise ValidationError("voice_profile.azure_style cannot contain XML attribute whitespace")
        allowed = voice_profile.get("azure_style_allowlist", [])
        if style not in allowed:
            raise ValidationError("Azure express-as style is not allowlisted for the selected voice profile")
        container = ET.SubElement(voice, f"{{{_MSTTS_NS}}}express-as", {"style": style})

    pauses = sorted(
        (pause["after"], pause["target_ms"])
        for segment in director["segments"]
        for pause in segment.get("pauses", [])
    )
    cursor = 0
    tail_parent = container
    for offset, target_ms in pauses:
        text_chunk = source[cursor:offset]
        if len(tail_parent) == 0 and tail_parent.text is None:
            tail_parent.text = text_chunk
        else:
            # A break may follow another break at the same offset; preserve an
            # empty text span rather than moving or normalizing source text.
            last_child = tail_parent[-1]
            last_child.tail = (last_child.tail or "") + text_chunk
        ET.SubElement(tail_parent, f"{{{_AZURE_NS}}}break", {"time": f"{target_ms}ms"})
        cursor = offset
    final_chunk = source[cursor:]
    if len(tail_parent) == 0 and tail_parent.text is None:
        tail_parent.text = final_chunk
    else:
        last_child = tail_parent[-1]
        last_child.tail = (last_child.tail or "") + final_chunk

    try:
        rendered = ET.tostring(root, encoding="unicode", short_empty_elements=True)
        # XML parsers normalize literal CR and CRLF in text nodes to LF. Replace
        # the serialized CR with a character reference so the locked narration
        # round-trips byte-for-byte after UTF-8 encoding.
        rendered = rendered.replace("\r", "&#13;")
        reparsed = ET.fromstring(rendered)
    except (ET.ParseError, ValueError) as exc:
        raise ValidationError(f"Azure SSML could not be safely serialized and reparsed: {exc}") from exc
    recovered = "".join(reparsed.itertext())
    if recovered != source:
        raise ValidationError("internal Azure SSML round-trip check failed; source text was not preserved")
    return rendered


def compile_backend(source, director, source_sha256, backend):
    profile = get_profile(backend)
    segments = _segment_records(source, director)
    overrides = {}
    artifact = {"backend": backend, "source_sha256": source_sha256, "exact_text": source}

    if profile is None:
        report = _control_report(backend, director)
        artifact["draft"] = None
        artifact["compile_status"] = "unsupported_backend"
        artifact["text_integrity"] = {
            "source_sha256": source_sha256,
            "source_characters": len(source),
            "source_utf8_bytes": len(source.encode("utf-8")),
            "exact_text_preserved": True,
        }
        return artifact, report

    if backend == "eleven_v4":
        cue_tags = {segment["id"]: _eleven_cue_tag(segment) for segment in segments}
        collisions = sorted(set(re.findall(r"\[[A-Za-z][A-Za-z0-9 _-]*\]", source)))
        if collisions:
            for name in CONTROL_NAMES:
                if any(_requested(segment, name) for segment in director["segments"]):
                    overrides[name] = {
                        "status": "unsupported",
                        "reason": "source contains bracketed control-like text; no backend draft was emitted to avoid accidental tag activation",
                        "collisions": collisions,
                        "applied": False,
                    }
            draft_text = None
            compile_status = "blocked_source_control_collision"
        else:
            draft_text = _build_eleven_draft(
                source, segments, cue_tags, lambda kind: profile["pause_tags"][kind]
            )
            compile_status = (
                "experimental_manual_audition_required"
                if any(cue_tags.values()) else "ready_for_manual_audition"
            )
            for control in ("delivery", "energy", "pace", "emphasis"):
                requested_segments = [
                    segment for segment in director["segments"] if _requested(segment, control)
                ]
                if requested_segments:
                    overrides[control] = {
                        "status": "model_guided",
                        "reason": "an experimental natural-language cue was inserted into draft_text; audition required; no deterministic word-level emphasis is claimed",
                        "emitted": [cue_tags[segment["id"]] for segment in requested_segments],
                        "applied": True,
                    }
            requested_pauses = sum(len(segment.get("pauses", [])) for segment in director["segments"])
            if requested_pauses:
                overrides["pauses"] = {
                    "status": "model_guided",
                    "reason": "known pause tags were inserted; target_ms remains advisory on Eleven v4",
                    "emitted": [profile["pause_tags"][pause["kind"]] for segment in director["segments"] for pause in segment.get("pauses", [])],
                }
        artifact.update({
            "draft_text": draft_text,
            "director_notes": [
                {"segment_id": segment["id"], "delivery": segment.get("delivery"), "energy": segment.get("energy"),
                 "pace": segment.get("pace"), "emphasis_spans": segment["emphasis_spans"]}
                for segment in segments
                if any((segment.get(k) is not None for k in ("delivery", "energy", "pace"))) or segment["emphasis_spans"]
            ],
            "experimental_cue_tags": [
                {"segment_id": segment_id, "tag": tag}
                for segment_id, tag in cue_tags.items() if tag and not collisions
            ],
            "compile_status": compile_status,
        })
        if collisions:
            artifact["blocking_collisions"] = collisions
    elif backend == "azure":
        ssml = _build_azure_ssml(source, director)
        artifact.update({
            "ssml": ssml,
            "compile_status": "ready_for_manual_audition",
            "selected_voice": director["voice_profile"]["azure_voice"],
            "selected_style": director["voice_profile"].get("azure_style"),
        })
        if director["voice_profile"].get("azure_style"):
            artifact["voice_style_status"] = {
                "status": "native_exact",
                "style": director["voice_profile"]["azure_style"],
                "note": "The selected SSML style value is serialized exactly; audible realization remains voice-dependent.",
            }
    elif backend == "fish_s2_pro":
        allowed_fish_tags = {"excited", "whisper"}
        for index, segment in enumerate(director["segments"]):
            fish_tags = segment.get("fish_tags", [])
            if not isinstance(fish_tags, list) or any(not isinstance(tag, str) or tag not in allowed_fish_tags for tag in fish_tags):
                raise ValidationError(f"director.segments[{index}].fish_tags contains an unsupported Fish tag")
            if len(fish_tags) != len(set(fish_tags)):
                raise ValidationError(f"director.segments[{index}].fish_tags must not contain duplicates")
        reserved = re.compile(r"\[[A-Za-z][A-Za-z0-9 _-]*\]")
        collision = sorted(set(reserved.findall(source)))
        if collision:
            for name in CONTROL_NAMES:
                if any(_requested(segment, name) for segment in director["segments"]):
                    overrides[name] = {
                        "status": "unsupported",
                        "reason": "source contains bracketed control-like text; no draft was emitted to avoid accidental control activation",
                        "collisions": collision,
                        "applied": False,
                    }
            draft_text = None
            compile_status = "blocked_source_control_collision"
        else:
            draft_parts = []
            emitted_fish_tags = []
            for segment in segments:
                for tag in segment["fish_tags"]:
                    # Schema validation pins this list to the README-documented tags.
                    draft_parts.append(f"[{tag}]")
                    emitted_fish_tags.append({"segment_id": segment["id"], "tag": f"[{tag}]"})
                cursor = segment["start"]
                for pause in segment["pauses"]:
                    draft_parts.append(source[cursor:pause["after"]])
                    draft_parts.append(profile["pause_tags"][pause["kind"]])
                    cursor = pause["after"]
                draft_parts.append(source[cursor:segment["end"]])
            draft_text = "".join(draft_parts)
            compile_status = "ready_for_manual_audition"
            if emitted_fish_tags:
                overrides["fish_tags"] = {
                    "status": "model_guided",
                    "reason": "only explicit README-documented Fish tags were emitted; audible realization remains model-guided",
                    "emitted": emitted_fish_tags,
                }
            if any(segment["pauses"] for segment in segments):
                overrides["pauses"] = {
                    "status": "model_guided",
                    "reason": "the frozen S2 profile documents [pause]; audible duration remains model-guided",
                    "emitted": ["[pause]" for segment in segments for _pause in segment["pauses"]],
                    "pause_requests": [dict(pause, segment_id=segment["id"]) for segment in segments for pause in segment["pauses"]],
                }
        artifact.update({
            "draft_text": draft_text,
            "text_segments": [{"segment_id": item["id"], "text": item["text"]} for item in segments],
            "compile_status": compile_status,
        })
        if collision:
            artifact["blocking_collisions"] = collision
        if any(segment["pronunciation_overrides"] for segment in segments):
            overrides["pronunciation_overrides"] = {
                "status": "unsupported",
                "reason": "the frozen Fish mapping does not define a safe pronunciation-override encoding",
            }
    elif backend == "cosyvoice":
        records = []
        for segment in segments:
            instructions = []
            if segment.get("delivery"):
                instructions.append(segment["delivery"])
            if segment.get("energy") is not None:
                instructions.append(f"表达能量等级 {segment['energy']}")
            if segment.get("pace"):
                instructions.append(f"语速倾向：{segment['pace']}")
            if segment["emphasis_spans"]:
                instructions.append("适度强调：" + "、".join(segment["emphasis_spans"]))
            for pause in segment["pauses"]:
                instructions.append(f"在原文偏移 {pause['after']} 处留{('短' if pause['kind'] == 'short' else '长')}停顿（目标 {pause['target_ms']}ms，时长为提示）")
            for override in segment["pronunciation_overrides"]:
                instructions.append(f"将“{override['text']}”读作“{override['pronunciation']}”")
            records.append({"segment_id": segment["id"], "text": segment["text"], "instruct_text": "；".join(instructions)})
        artifact.update({"records": records, "compile_status": "model_guided_manual_audition_required"})
    elif backend == "chattts":
        allowlist = set(director["voice_profile"].get("chattts_token_allowlist", []))
        token_map = profile["allowed_tokens"]
        collisions = _collision_tokens(source, ["[uv_break]", "[lbreak]", "[laugh]"])
        emitted = []
        unsupported_items = []
        if collisions:
            unsupported_items.extend({"token": token, "reason": "source already contains a control token; not reinterpreted"} for token in collisions)
        else:
            for segment in director["segments"]:
                for pause in segment.get("pauses", []):
                    token = token_map[pause["kind"]]
                    if token in allowlist:
                        emitted.append({"after": pause["after"], "token": token, "segment_id": segment["id"]})
                    else:
                        unsupported_items.append({"after": pause["after"], "token": token, "reason": "token is not allowlisted"})
        draft_text = source
        if collisions:
            draft_text = None
            for name in CONTROL_NAMES:
                if any(_requested(segment, name) for segment in director["segments"]):
                    overrides[name] = {
                        "status": "unsupported",
                        "reason": "source contains a ChatTTS control token; no draft was emitted to avoid accidental token activation",
                        "collisions": collisions,
                        "applied": False,
                    }
        elif emitted:
            events = sorted(emitted, key=lambda event: event["after"])
            parts = []
            cursor = 0
            for event in events:
                parts.extend((source[cursor:event["after"]], event["token"]))
                cursor = event["after"]
            parts.append(source[cursor:])
            draft_text = "".join(parts)
        if any(segment.get("pauses") for segment in director["segments"]) and not collisions:
            overrides["pauses"] = {
                "status": "unsupported" if unsupported_items else "model_guided",
                "reason": "ChatTTS pause tokens are emitted only when explicitly allowlisted; token behavior is model-guided",
                "allowlist": sorted(allowlist),
                "emitted": emitted,
                "unsupported_items": unsupported_items,
            }
        artifact.update({"draft_text": draft_text, "compile_status": "ready_for_manual_audition"})
        if collisions:
            artifact["compile_status"] = "blocked_source_control_collision"
            artifact["blocking_collisions"] = collisions
    elif backend == "parler":
        artifact.update({
            "voice_description": director["voice_profile"]["description"],
            "segments": [
                {"segment_id": item["id"], "text": item["text"], "delivery_description": item.get("delivery"),
                 "energy": item.get("energy"), "pace": item.get("pace"), "emphasis_spans": item["emphasis_spans"],
                 "pauses": item["pauses"]}
                for item in segments
            ],
            "compile_status": "model_guided_manual_audition_required",
        })
        if any(segment["pronunciation_overrides"] for segment in segments):
            overrides["pronunciation_overrides"] = {"status": "unsupported", "reason": "Parler mapping defines voice/delivery descriptions, not pronunciation overrides"}
    elif backend == "f5":
        artifact.update({
            "compile_status": "chunk_manifest_only",
            "note": "Use the chunk command to build lossless chunk boundaries; no emotion or speech markup is emitted.",
            "segments": [{"segment_id": item["id"], "text": item["text"]} for item in segments],
        })
    else:  # defensive: profile table and compiler branches must evolve together
        raise ValidationError(f"backend profile exists but no compiler is implemented: {backend}")

    report = _control_report(backend, director, overrides)
    recovered = "".join(item["text"] for item in segments)
    if recovered != source:
        raise ValidationError("internal text-integrity invariant failed: segment reconstruction differs from source")
    artifact["text_integrity"] = {
        "source_sha256": source_sha256,
        "source_characters": len(source),
        "source_utf8_bytes": len(source.encode("utf-8")),
        "exact_text_preserved": True,
    }
    return artifact, report
