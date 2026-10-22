"""Command-line entry point for offline voice-director artifacts."""

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

from .adapters import _control_report, compile_backend
from .alignment import audit_alignment
from .chunking import build_chunks
from .errors import OutputExistsError, ValidationError, VoiceDirectorError
from .profiles import get_license_review, get_profile, list_profiles
from .schema import load_inputs, read_json, read_script, sha256_bytes


def _json_bytes(data):
    return (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _write_artifacts(out_dir, files, input_hashes, overwrite):
    output_dir = Path(out_dir)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise VoiceDirectorError(f"cannot create output directory {output_dir}: {exc}") from exc
    targets = {name: output_dir / name for name in files}
    existing = [str(path) for path in targets.values() if path.exists()]
    if existing and not overwrite:
        raise OutputExistsError("refusing to overwrite existing output(s): " + ", ".join(existing) + "; pass --overwrite explicitly")

    payloads = {name: _json_bytes(data) for name, data in files.items()}
    output_hashes = {name: hashlib.sha256(payload).hexdigest() for name, payload in payloads.items()}
    manifest = {
        "schema_version": 1,
        "tool": "voice-director",
        "tool_version": "1.0.0",
        "input_sha256": input_hashes,
        "artifacts_sha256": output_hashes,
        "provider_calls": 0,
        "network_access": False,
    }
    payloads["manifest.json"] = _json_bytes(manifest)
    manifest_path = targets.get("manifest.json", output_dir / "manifest.json")
    if manifest_path.exists() and "manifest.json" not in targets and not overwrite:
        raise OutputExistsError(f"refusing to overwrite existing output: {manifest_path}; pass --overwrite explicitly")

    temp_paths = []
    try:
        for name, payload in payloads.items():
            target = output_dir / name
            with tempfile.NamedTemporaryFile(mode="wb", dir=output_dir, prefix=".voice-director-", suffix=".tmp", delete=False) as stream:
                temp_path = Path(stream.name)
                temp_paths.append(temp_path)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        for temp_path, name in zip(temp_paths, payloads):
            os.replace(temp_path, output_dir / name)
        return manifest
    except OSError as exc:
        raise VoiceDirectorError(f"failed to write output artifacts under {output_dir}: {exc}") from exc
    finally:
        for temp_path in temp_paths:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def _print_json(data, stream=None):
    if stream is None:
        stream = sys.stdout
    stream.write(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def _input_hashes(inputs):
    return {
        "script_sha256": inputs["source_sha256"],
        "director_sha256": inputs["director_sha256"],
    }


def _blocked_compile_report(backend, director, message):
    report = _control_report(backend, director)
    report["compile_status"] = "blocked"
    report["compile_error"] = message
    for name, detail in report["controls"].items():
        if detail.get("requested"):
            detail["status"] = "unsupported"
            detail["applied"] = False
            detail["reason"] = "compiler produced no backend draft: " + message
    return report


def _command_validate(args):
    inputs = load_inputs(args.script, args.director)
    return {
        "valid": True,
        "schema_version": 1,
        "source_sha256": inputs["source_sha256"],
        "source_characters": len(inputs["source"]),
        "source_utf8_bytes": len(inputs["source_bytes"]),
        "director_sha256": inputs["director_sha256"],
        "segment_count": len(inputs["director"]["segments"]),
        "providers_called": 0,
    }, 0


def _command_compile(args):
    inputs = load_inputs(args.script, args.director)
    try:
        compiled, report = compile_backend(inputs["source"], inputs["director"], inputs["source_sha256"], args.backend)
    except ValidationError as exc:
        report = _blocked_compile_report(args.backend, inputs["director"], str(exc))
        compiled = {
            "backend": args.backend,
            "compile_status": "blocked",
            "compile_error": str(exc),
            "exact_text": inputs["source"],
            "draft": None,
            "text_integrity": {
                "source_sha256": inputs["source_sha256"],
                "source_characters": len(inputs["source"]),
                "source_utf8_bytes": len(inputs["source_bytes"]),
                "exact_text_preserved": True,
            },
        }
        files = {"compiled.json": compiled, "capability-report.json": report}
        _write_artifacts(args.out, files, _input_hashes(inputs), args.overwrite)
        return {"written": sorted([*files, "manifest.json"]), "compile_status": "blocked", "error": str(exc)}, 2
    files = {"compiled.json": compiled, "capability-report.json": report}
    _write_artifacts(args.out, files, _input_hashes(inputs), args.overwrite)
    code = 0 if report["supported"] and not str(compiled["compile_status"]).startswith("blocked") else 2
    return {"written": sorted([*files, "manifest.json"]), "compile_status": compiled["compile_status"], "backend": args.backend}, code


def _command_chunk(args):
    inputs = load_inputs(args.script, args.director)
    chunks = build_chunks(inputs["source"], inputs["director"], args.max_chars, args.backend)
    report = _control_report(args.backend, inputs["director"])
    files = {"chunks.json": chunks, "capability-report.json": report}
    _write_artifacts(args.out, files, _input_hashes(inputs), args.overwrite)
    code = 0 if report["supported"] else 2
    return {"written": sorted([*files, "manifest.json"]), "chunk_count": len(chunks["chunks"]), "backend": args.backend}, code


def _command_alignment(args):
    source, source_bytes = read_script(args.script)
    source_sha256 = sha256_bytes(source_bytes)
    alignment_path = Path(args.alignment)
    try:
        alignment, alignment_raw = read_json(alignment_path)
        report = audit_alignment(source, source_sha256, alignment)
    except ValidationError as exc:
        try:
            alignment_raw = alignment_path.read_bytes()
        except OSError:
            alignment_raw = b""
        report = {
            "status": "FAIL",
            "source_sha256": source_sha256,
            "errors": [str(exc)],
            "warnings": [],
            "aligned_words": [],
            "unaligned_words": [],
            "text_match": {
                "matches_after_whitespace_normalization": False,
                "source_compact_characters": len("".join(source.split())),
                "alignment_compact_characters": 0,
                "matched_prefix_characters": 0,
            },
            "scope_note": "This checks supplied text/timestamps only; it is not an ASR or phonetic correctness audit.",
        }
    files = {"alignment-audit.json": report}
    hashes = {"script_sha256": source_sha256, "alignment_sha256": sha256_bytes(alignment_raw)}
    _write_artifacts(args.out, files, hashes, args.overwrite)
    return {"written": sorted([*files, "manifest.json"]), "status": report["status"], "error_count": len(report["errors"])}, 0 if report["status"] == "PASS" else 1


def build_parser():
    parser = argparse.ArgumentParser(prog="voice-director", description="Validate and compile offline voice-director artifacts; never calls TTS providers.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate the immutable script and director map")
    validate.add_argument("--script", required=True)
    validate.add_argument("--director", required=True)
    validate.set_defaults(handler=_command_validate)

    compile_parser = subparsers.add_parser("compile", help="compile a backend-specific draft and capability report")
    compile_parser.add_argument("--script", required=True)
    compile_parser.add_argument("--director", required=True)
    compile_parser.add_argument("--backend", required=True)
    compile_parser.add_argument("--out", required=True)
    compile_parser.add_argument("--overwrite", action="store_true")
    compile_parser.set_defaults(handler=_command_compile)

    chunk = subparsers.add_parser("chunk", help="create a lossless semantic chunk manifest")
    chunk.add_argument("--script", required=True)
    chunk.add_argument("--director", required=True)
    chunk.add_argument("--backend", required=True)
    chunk.add_argument("--max-chars", required=True, type=int)
    chunk.add_argument("--out", required=True)
    chunk.add_argument("--overwrite", action="store_true")
    chunk.set_defaults(handler=_command_chunk)

    alignment = subparsers.add_parser("alignment-audit", help="audit WhisperX-style alignment JSON without inventing timestamps")
    alignment.add_argument("--script", required=True)
    alignment.add_argument("--alignment", required=True)
    alignment.add_argument("--out", required=True)
    alignment.add_argument("--overwrite", action="store_true")
    alignment.set_defaults(handler=_command_alignment)

    capabilities = subparsers.add_parser("capabilities", help="show frozen, declared backend capability profiles")
    capabilities.add_argument("--backend")
    capabilities.set_defaults(handler=None)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "capabilities":
        if args.backend:
            profile = get_profile(args.backend)
            if profile is None:
                _print_json({
                    "backend": args.backend,
                    "supported": False,
                    "error": "unknown backend; no fallback exists",
                    "license_review": get_license_review(args.backend),
                })
                return 2
            _print_json({"backend": args.backend, "supported": True, **profile})
            return 0
        _print_json({"profiles": list_profiles(), "live_discovery": False, "provider_calls": 0})
        return 0
    try:
        result, code = args.handler(args)
        _print_json(result)
        return code
    except VoiceDirectorError as exc:
        _print_json({"error": str(exc), "status": "FAIL"}, stream=sys.stderr)
        return 2
    except OSError as exc:
        _print_json({"error": str(exc), "status": "FAIL"}, stream=sys.stderr)
        return 2
