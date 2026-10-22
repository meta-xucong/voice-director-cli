"""Strict, lossless input validation for the director map v1."""

import hashlib
import json
import math
import re
from pathlib import Path

from .errors import ValidationError

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_TOP_KEYS = {"schema_version", "source_sha256", "voice_profile", "segments"}
_VOICE_KEYS = {"description", "azure_voice", "azure_style", "azure_style_allowlist", "chattts_token_allowlist"}
_SEGMENT_KEYS = {
    "id", "start", "end", "delivery", "function", "energy", "pace",
    "emphasis_spans", "pauses", "pronunciation_overrides", "fish_tags",
}
_CHAT_TOKENS = {"[uv_break]", "[lbreak]", "[laugh]"}
_FISH_TAGS = {"excited", "whisper"}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValidationError(f"non-finite JSON number is not allowed: {value}")


def _finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValidationError(f"non-finite JSON number is not allowed: {value}")
    return number


def read_json(path):
    try:
        raw = Path(path).read_bytes()
        text = raw.decode("utf-8", errors="strict")
        data = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_reject_constant, parse_float=_finite_float)
    except UnicodeDecodeError as exc:
        raise ValidationError(f"{path}: file must be valid UTF-8: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{path}: invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    except OSError as exc:
        raise ValidationError(f"cannot read {path}: {exc}") from exc
    return data, raw


def read_script(path):
    try:
        raw = Path(path).read_bytes()
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValidationError(f"{path}: script must be valid UTF-8: {exc}") from exc
    except OSError as exc:
        raise ValidationError(f"cannot read {path}: {exc}") from exc
    return text, raw


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _keys(obj, required, allowed, path):
    if not isinstance(obj, dict):
        raise ValidationError(f"{path} must be an object")
    missing = sorted(required - set(obj))
    extra = sorted(set(obj) - allowed)
    if missing:
        raise ValidationError(f"{path} missing required field(s): {', '.join(missing)}")
    if extra:
        raise ValidationError(f"{path} has unsupported field(s): {', '.join(extra)}")


def _nonempty_string(value, path):
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{path} must be a non-empty string")
    if any(0xD800 <= ord(ch) <= 0xDFFF for ch in value):
        raise ValidationError(f"{path} contains an invalid Unicode surrogate")
    if any(ord(ch) < 0x20 and ch not in "\t\n\r" for ch in value):
        raise ValidationError(f"{path} contains an XML-invalid control character")
    return value


def _string_list(value, path):
    if not isinstance(value, list):
        raise ValidationError(f"{path} must be an array")
    result = []
    for index, item in enumerate(value):
        result.append(_nonempty_string(item, f"{path}[{index}]"))
    if len(result) != len(set(result)):
        raise ValidationError(f"{path} must not contain duplicates")
    return result


def validate_map(source, source_bytes, data):
    _keys(data, _TOP_KEYS, _TOP_KEYS, "director")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValidationError("director.schema_version must be integer 1")
    expected_hash = sha256_bytes(source_bytes)
    declared_hash = data["source_sha256"]
    if not isinstance(declared_hash, str) or not _HASH_RE.fullmatch(declared_hash):
        raise ValidationError("director.source_sha256 must be 64 lowercase hexadecimal characters")
    if declared_hash != expected_hash:
        raise ValidationError(f"source hash mismatch: map={declared_hash}, script={expected_hash}")

    voice = data["voice_profile"]
    _keys(voice, {"description"}, _VOICE_KEYS, "director.voice_profile")
    _nonempty_string(voice["description"], "director.voice_profile.description")
    for key in ("azure_voice", "azure_style"):
        if key in voice:
            _nonempty_string(voice[key], f"director.voice_profile.{key}")
    if "azure_style_allowlist" in voice:
        _string_list(voice["azure_style_allowlist"], "director.voice_profile.azure_style_allowlist")
    if "azure_style" in voice:
        allowed_styles = voice.get("azure_style_allowlist", [])
        if voice["azure_style"] not in allowed_styles:
            raise ValidationError("director.voice_profile.azure_style must appear in azure_style_allowlist")
    if "chattts_token_allowlist" in voice:
        tokens = _string_list(voice["chattts_token_allowlist"], "director.voice_profile.chattts_token_allowlist")
        invalid = sorted(set(tokens) - _CHAT_TOKENS)
        if invalid:
            raise ValidationError("director.voice_profile.chattts_token_allowlist has unknown token(s): " + ", ".join(invalid))

    segments = data["segments"]
    if not isinstance(segments, list):
        raise ValidationError("director.segments must be an array")
    if not source and segments:
        raise ValidationError("director.segments must be empty for an empty script")
    if source and not segments:
        raise ValidationError("director.segments must cover the non-empty script")

    ids = set()
    expected_start = 0
    for index, segment in enumerate(segments):
        path = f"director.segments[{index}]"
        _keys(segment, {"id", "start", "end"}, _SEGMENT_KEYS, path)
        ident = _nonempty_string(segment["id"], f"{path}.id")
        if ident in ids:
            raise ValidationError(f"duplicate segment id: {ident}")
        ids.add(ident)
        start, end = segment["start"], segment["end"]
        if type(start) is not int or type(end) is not int:
            raise ValidationError(f"{path}.start and {path}.end must be integer Unicode code-point offsets")
        if start != expected_start:
            relation = "gap" if start > expected_start else "overlap or out-of-order range"
            raise ValidationError(f"{path} creates a {relation}: expected start {expected_start}, got {start}")
        if end <= start or end > len(source):
            raise ValidationError(f"{path}.end must be greater than start and no greater than {len(source)}")
        expected_start = end
        for field in ("delivery", "function", "pace"):
            if field in segment:
                _nonempty_string(segment[field], f"{path}.{field}")
        if "energy" in segment and (type(segment["energy"]) is not int or not math.isfinite(segment["energy"])):
            raise ValidationError(f"{path}.energy must be an integer")
        if "emphasis_spans" in segment:
            spans = _string_list(segment["emphasis_spans"], f"{path}.emphasis_spans")
            content = source[start:end]
            absent = [span for span in spans if span not in content]
            if absent:
                raise ValidationError(f"{path}.emphasis_spans value not found within segment: {absent[0]!r}")
        if "fish_tags" in segment:
            fish_tags = _string_list(segment["fish_tags"], f"{path}.fish_tags")
            invalid = sorted(set(fish_tags) - _FISH_TAGS)
            if invalid:
                raise ValidationError(f"{path}.fish_tags has unsupported tag(s): " + ", ".join(invalid))
        if "pauses" in segment:
            pauses = segment["pauses"]
            if not isinstance(pauses, list):
                raise ValidationError(f"{path}.pauses must be an array")
            last_after = start
            for pause_index, pause in enumerate(pauses):
                pp = f"{path}.pauses[{pause_index}]"
                _keys(pause, {"after", "kind", "target_ms"}, {"after", "kind", "target_ms"}, pp)
                after = pause["after"]
                if type(after) is not int or after <= start or after > end:
                    raise ValidationError(f"{pp}.after must be an absolute source offset in ({start}, {end}]")
                if after < last_after:
                    raise ValidationError(f"{path}.pauses must be sorted by after offset")
                last_after = after
                if pause["kind"] not in ("short", "long"):
                    raise ValidationError(f"{pp}.kind must be 'short' or 'long'")
                target = pause["target_ms"]
                if type(target) is not int or target < 1:
                    raise ValidationError(f"{pp}.target_ms must be a positive integer")
        if "pronunciation_overrides" in segment:
            overrides = segment["pronunciation_overrides"]
            if not isinstance(overrides, list):
                raise ValidationError(f"{path}.pronunciation_overrides must be an array")
            for override_index, override in enumerate(overrides):
                op = f"{path}.pronunciation_overrides[{override_index}]"
                _keys(override, {"text", "pronunciation"}, {"text", "pronunciation"}, op)
                target = _nonempty_string(override["text"], f"{op}.text")
                _nonempty_string(override["pronunciation"], f"{op}.pronunciation")
                if target not in source[start:end]:
                    raise ValidationError(f"{op}.text must appear within its segment")
    if expected_start != len(source):
        raise ValidationError(f"director.segments leave a gap: covered [0, {expected_start}), script length is {len(source)}")
    return data


def load_inputs(script_path, director_path):
    source, source_bytes = read_script(script_path)
    director, director_bytes = read_json(director_path)
    validate_map(source, source_bytes, director)
    return {
        "source": source,
        "source_bytes": source_bytes,
        "source_sha256": sha256_bytes(source_bytes),
        "director": director,
        "director_bytes": director_bytes,
        "director_sha256": sha256_bytes(director_bytes),
    }
