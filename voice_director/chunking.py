"""Lossless semantic chunk manifests inspired by the frozen F5 workflow."""

from .errors import ValidationError

_SENTENCE_ENDS = set("。！？!?；;\n")


def _atomic_pieces(source, director, max_chars):
    pieces = []
    for segment in director["segments"]:
        start, end = segment["start"], segment["end"]
        text = source[start:end]
        if len(text) <= max_chars:
            pieces.append({"start": start, "end": end, "text": text, "segment_id": segment["id"], "boundary_reason": "segment_end"})
            continue
        sentence_start = 0
        local_ranges = []
        for index, char in enumerate(text):
            if char in _SENTENCE_ENDS:
                local_ranges.append((sentence_start, index + 1, "sentence_punctuation"))
                sentence_start = index + 1
        if sentence_start < len(text):
            local_ranges.append((sentence_start, len(text), "segment_end"))
        if not local_ranges:
            local_ranges = [(0, len(text), "segment_end")]
        for local_start, local_end, reason in local_ranges:
            span = text[local_start:local_end]
            if len(span) > max_chars:
                raise ValidationError(
                    f"segment {segment['id']} contains an atomic sentence of {len(span)} characters, "
                    f"over max_chars={max_chars}; split the director map at a safe semantic boundary"
                )
            if span:
                pieces.append({
                    "start": start + local_start,
                    "end": start + local_end,
                    "text": span,
                    "segment_id": segment["id"],
                    "boundary_reason": reason,
                })
    return pieces


def build_chunks(source, director, max_chars, backend):
    if type(max_chars) is not int or max_chars <= 0:
        raise ValidationError("max_chars must be a positive integer")
    if not source:
        return {
            "backend": backend,
            "max_chars": max_chars,
            "chunks": [],
            "reconstructed_text": "",
            "text_integrity": {"exact_text_preserved": True, "source_characters": 0},
            "notes": ["Empty source produces an empty chunk manifest."],
        }

    pieces = _atomic_pieces(source, director, max_chars)
    chunks = []
    current = None
    for piece in pieces:
        if current is None or len(current["text"]) + len(piece["text"]) > max_chars:
            if current is not None:
                chunks.append(current)
            current = {
                "id": f"C{len(chunks) + 1:04d}",
                "start": piece["start"],
                "end": piece["end"],
                "text": piece["text"],
                "segment_ids": [piece["segment_id"]],
                "boundary_reasons": [piece["boundary_reason"]],
            }
        else:
            if current["end"] != piece["start"]:
                raise ValidationError("internal chunking error: pieces are not contiguous")
            current["end"] = piece["end"]
            current["text"] += piece["text"]
            if piece["segment_id"] not in current["segment_ids"]:
                current["segment_ids"].append(piece["segment_id"])
            current["boundary_reasons"].append(piece["boundary_reason"])
    if current is not None:
        chunks.append(current)

    reconstructed = "".join(chunk["text"] for chunk in chunks)
    if reconstructed != source:
        raise ValidationError("internal chunking invariant failed: chunks do not reconstruct the exact source")
    if any(len(chunk["text"]) > max_chars for chunk in chunks):
        raise ValidationError("internal chunking invariant failed: output chunk exceeds max_chars")
    return {
        "backend": backend,
        "max_chars": max_chars,
        "chunks": chunks,
        "reconstructed_text": reconstructed,
        "text_integrity": {
            "exact_text_preserved": True,
            "source_characters": len(source),
            "chunk_characters": sum(len(chunk["text"]) for chunk in chunks),
        },
        "notes": [
            "Chunks use director segment boundaries first and sentence punctuation only to split an over-limit segment.",
            "No characters or separators are added, removed, or normalized.",
        ],
    }
