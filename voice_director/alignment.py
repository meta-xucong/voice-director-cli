"""Conservative audit of WhisperX-style word alignments; never fills missing times."""

import math


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _compact_whitespace(text):
    # Explicitly ignore whitespace only. Do not normalize punctuation, case,
    # Unicode composition, or alternative spellings.
    return "".join(text.split())


def audit_alignment(source, source_sha256, alignment):
    errors = []
    warnings = []
    aligned_words = []
    unaligned_words = []
    seen_text_parts = []
    previous_start = None
    previous_end = None
    duration = alignment.get("duration") if isinstance(alignment, dict) else None

    if not isinstance(alignment, dict):
        return {
            "status": "FAIL", "source_sha256": source_sha256,
            "errors": ["alignment root must be a JSON object"], "warnings": [],
            "aligned_words": [], "unaligned_words": [],
            "text_match": {"matches_after_whitespace_normalization": False, "source_compact_characters": len(_compact_whitespace(source)), "alignment_compact_characters": 0, "matched_prefix_characters": 0},
            "scope_note": "This checks supplied text/timestamps only; it is not an ASR or phonetic correctness audit.",
        }
    if "duration" in alignment and not _number(duration):
        errors.append("alignment.duration must be a finite non-negative number when provided")
    elif _number(duration) and duration < 0:
        errors.append("alignment.duration must be non-negative")

    segments = alignment.get("segments")
    if not isinstance(segments, list):
        errors.append("alignment.segments must be an array")
        segments = []
    word_index = 0
    for segment_index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            errors.append(f"segments[{segment_index}] must be an object")
            continue
        seg_start, seg_end = segment.get("start"), segment.get("end")
        if (seg_start is None) != (seg_end is None):
            errors.append(f"segments[{segment_index}] must provide both start and end or neither")
        segment_bounds_valid = False
        if seg_start is not None and seg_end is not None:
            if not _number(seg_start) or not _number(seg_end) or seg_start < 0 or seg_end <= seg_start:
                errors.append(f"segments[{segment_index}] has an invalid time interval")
            else:
                segment_bounds_valid = True
                if _number(duration) and seg_end > duration:
                    errors.append(f"segments[{segment_index}].end exceeds alignment.duration")
        words = segment.get("words")
        if not isinstance(words, list):
            errors.append(f"segments[{segment_index}].words must be an array")
            continue
        for local_index, word in enumerate(words):
            location = f"segments[{segment_index}].words[{local_index}]"
            if not isinstance(word, dict):
                errors.append(f"{location} must be an object")
                unaligned_words.append({"index": word_index, "location": location, "reason": "not_an_object"})
                word_index += 1
                continue
            token = word.get("word")
            if not isinstance(token, str):
                errors.append(f"{location}.word must be a string")
                unaligned_words.append({"index": word_index, "location": location, "reason": "missing_word_text"})
                token = ""
            else:
                seen_text_parts.append(token)
            start, end = word.get("start"), word.get("end")
            item = {"index": word_index, "word": token, "start": start, "end": end}
            missing = []
            if start is None:
                missing.append("start")
            if end is None:
                missing.append("end")
            if missing:
                item["time_status"] = "missing"
                item["missing_fields"] = missing
                unaligned_words.append({"index": word_index, "word": token, "reason": "missing_timestamp", "missing_fields": missing})
                errors.append(f"{location} has missing timestamp field(s): {', '.join(missing)}")
            elif not _number(start) or not _number(end):
                item["time_status"] = "invalid"
                unaligned_words.append({"index": word_index, "word": token, "reason": "invalid_timestamp"})
                errors.append(f"{location} start/end must be finite numbers")
            else:
                item["time_status"] = "present"
                if start < 0 or end <= start:
                    item["time_status"] = "invalid"
                    unaligned_words.append({"index": word_index, "word": token, "reason": "invalid_interval"})
                    errors.append(f"{location} has an invalid interval; expected 0 <= start < end")
                if previous_start is not None and start < previous_start:
                    errors.append(f"{location}.start is nonmonotonic ({start} < previous start {previous_start})")
                    item["time_status"] = "nonmonotonic"
                    unaligned_words.append({"index": word_index, "word": token, "reason": "nonmonotonic_start"})
                if previous_end is not None and end < previous_end:
                    errors.append(f"{location}.end is nonmonotonic ({end} < previous end {previous_end})")
                    item["time_status"] = "nonmonotonic"
                    unaligned_words.append({"index": word_index, "word": token, "reason": "nonmonotonic_end"})
                if start >= 0 and end > start:
                    if segment_bounds_valid and (start < seg_start or end > seg_end):
                        errors.append(f"{location} lies outside its segment time interval")
                        item["time_status"] = "out_of_bounds"
                        unaligned_words.append({"index": word_index, "word": token, "reason": "outside_segment"})
                    if _number(duration) and end > duration:
                        errors.append(f"{location}.end exceeds alignment.duration")
                        item["time_status"] = "out_of_bounds"
                        unaligned_words.append({"index": word_index, "word": token, "reason": "exceeds_duration"})
                    previous_start = start
                    previous_end = end
            aligned_words.append(item)
            word_index += 1

    source_compact = _compact_whitespace(source)
    alignment_compact = _compact_whitespace("".join(seen_text_parts))
    common = 0
    for expected, observed in zip(source_compact, alignment_compact):
        if expected != observed:
            break
        common += 1
    text_matches = source_compact == alignment_compact
    if not text_matches:
        errors.append("alignment word text does not match the source in order after whitespace-only normalization")
    return {
        "status": "PASS" if not errors else "FAIL",
        "source_sha256": source_sha256,
        "errors": errors,
        "warnings": warnings,
        "aligned_words": aligned_words,
        "unaligned_words": unaligned_words,
        "text_match": {
            "matches_after_whitespace_normalization": text_matches,
            "source_compact_characters": len(source_compact),
            "alignment_compact_characters": len(alignment_compact),
            "matched_prefix_characters": common,
            "first_mismatch_compact_offset": None if text_matches else common,
        },
        "scope_note": "This checks supplied text/timestamps only; it is not an ASR or phonetic correctness audit.",
    }
