import contextlib
import hashlib
import io
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from voice_director.adapters import compile_backend
from voice_director.alignment import audit_alignment
from voice_director.chunking import build_chunks
from voice_director.cli import main
from voice_director.errors import ValidationError
from voice_director.schema import load_inputs, validate_map


def make_director(source, *, voice_profile=None, segments=None):
    if voice_profile is None:
        voice_profile = {
            "description": "清晰、自然的普通话课堂讲解",
            "azure_voice": "zh-CN-XiaoxiaoNeural",
            "azure_style_allowlist": ["chat"],
            "azure_style": "chat",
            "chattts_token_allowlist": ["[uv_break]", "[lbreak]"],
        }
    if segments is None:
        midpoint = min(4, len(source))
        segment = {"id": "S001", "start": 0, "end": len(source)}
        if source:
            segment.update({
                "delivery": "提出问题，稍作停顿",
                "function": "question",
                "energy": 2,
                "pace": "steady",
                "emphasis_spans": ["第二句"] if "第二句" in source else [],
                "pauses": [{"after": midpoint, "kind": "short", "target_ms": 250}],
                "pronunciation_overrides": ([{"text": "第二句", "pronunciation": "dì èr jù"}] if "第二句" in source else []),
            })
            segments = [segment]
        else:
            segments = []
    return {
        "schema_version": 1,
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "voice_profile": voice_profile,
        "segments": segments,
    }


class SchemaTests(unittest.TestCase):
    def test_valid_map_uses_exact_utf8_source_hash_and_codepoint_offsets(self):
        source = "甲🙂。"
        director = make_director(source, segments=[{"id": "s", "start": 0, "end": len(source)}])
        self.assertIs(validate_map(source, source.encode("utf-8"), director), director)

    def test_rejects_hash_mismatch(self):
        source = "甲乙"
        director = make_director(source)
        director["source_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValidationError, "source hash mismatch"):
            validate_map(source, source.encode(), director)

    def test_rejects_duplicate_ids_gaps_and_overlaps(self):
        source = "甲乙丙丁"
        duplicate = make_director(source, segments=[
            {"id": "s", "start": 0, "end": 2}, {"id": "s", "start": 2, "end": 4},
        ])
        with self.assertRaisesRegex(ValidationError, "duplicate segment id"):
            validate_map(source, source.encode(), duplicate)
        gap = make_director(source, segments=[
            {"id": "a", "start": 0, "end": 1}, {"id": "b", "start": 2, "end": 4},
        ])
        with self.assertRaisesRegex(ValidationError, "gap"):
            validate_map(source, source.encode(), gap)
        overlap = make_director(source, segments=[
            {"id": "a", "start": 0, "end": 3}, {"id": "b", "start": 2, "end": 4},
        ])
        with self.assertRaisesRegex(ValidationError, "overlap"):
            validate_map(source, source.encode(), overlap)

    def test_rejects_unknown_fields_invalid_pause_and_missing_emphasis(self):
        source = "关键术语。"
        director = make_director(source)
        director["segments"][0]["magic"] = True
        with self.assertRaisesRegex(ValidationError, "unsupported field"):
            validate_map(source, source.encode(), director)
        director = make_director(source, segments=[{
            "id": "s", "start": 0, "end": len(source),
            "pauses": [{"after": 2, "kind": "short", "target_ms": 0}],
        }])
        with self.assertRaisesRegex(ValidationError, "positive integer"):
            validate_map(source, source.encode(), director)
        director = make_director(source, segments=[{
            "id": "s", "start": 0, "end": len(source), "emphasis_spans": ["不存在"],
        }])
        with self.assertRaisesRegex(ValidationError, "not found"):
            validate_map(source, source.encode(), director)

    def test_rejects_unlisted_azure_style_and_unknown_chat_token(self):
        source = "甲"
        voice = {"description": "voice", "azure_style": "angry", "azure_style_allowlist": ["chat"]}
        with self.assertRaisesRegex(ValidationError, "must appear in azure_style_allowlist"):
            validate_map(source, source.encode(), make_director(source, voice_profile=voice, segments=[{"id": "s", "start": 0, "end": 1}]))
        voice = {"description": "voice", "chattts_token_allowlist": ["[angry]"]}
        with self.assertRaisesRegex(ValidationError, "unknown token"):
            validate_map(source, source.encode(), make_director(source, voice_profile=voice, segments=[{"id": "s", "start": 0, "end": 1}]))

    def test_fish_tags_accept_only_unique_documented_values(self):
        source = "甲乙"
        valid = make_director(source, segments=[{
            "id": "s", "start": 0, "end": len(source), "fish_tags": ["excited", "whisper"],
        }])
        self.assertIs(validate_map(source, source.encode(), valid), valid)
        for tags in (["angry"], ["excited", "excited"], "excited", ["[pause]"]):
            with self.subTest(tags=tags), self.assertRaises(ValidationError):
                invalid = make_director(source, segments=[{
                    "id": "s", "start": 0, "end": len(source), "fish_tags": tags,
                }])
                validate_map(source, source.encode(), invalid)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.source = "第一句。第二句！"
        self.director = make_director(self.source)
        self.source_hash = hashlib.sha256(self.source.encode("utf-8")).hexdigest()

    def test_every_backend_retains_exact_source_text(self):
        backends = ("eleven_v4", "azure", "fish_s2_pro", "cosyvoice", "chattts", "parler", "f5")
        for backend in backends:
            with self.subTest(backend=backend):
                compiled, report = compile_backend(self.source, self.director, self.source_hash, backend)
                self.assertIn("license_review", report)
                self.assertIn("code", report["license_review"])
                self.assertIn("weights", report["license_review"])
                self.assertEqual(compiled["exact_text"], self.source)
                self.assertTrue(compiled["text_integrity"]["exact_text_preserved"])
                self.assertEqual(compiled["text_integrity"]["source_sha256"], self.source_hash)
                if backend == "eleven_v4":
                    import re
                    stripped = re.sub(r"\[voice_director: [^\]]+\]|\[(?:short|long) pause\]", "", compiled["draft_text"])
                    self.assertEqual(stripped, self.source)
                    self.assertEqual(report["controls"]["pauses"]["status"], "model_guided")
                    for control in ("delivery", "energy", "pace", "emphasis"):
                        self.assertEqual(report["controls"][control]["status"], "model_guided")
                        self.assertTrue(report["controls"][control]["emitted"])
                    self.assertEqual(compiled["compile_status"], "experimental_manual_audition_required")
                elif backend == "azure":
                    root = ET.fromstring(compiled["ssml"])
                    self.assertEqual("".join(root.itertext()), self.source)
                    self.assertIn("250ms", compiled["ssml"])
                elif backend == "fish_s2_pro":
                    import re
                    without_tags = re.sub(r"\[(?:pause|excited|whisper)\]", "", compiled["draft_text"])
                    self.assertEqual(without_tags, self.source)
                    self.assertEqual("".join(item["text"] for item in compiled["text_segments"]), self.source)
                    self.assertNotIn("voice_director", compiled["draft_text"])
                    self.assertEqual(report["controls"]["delivery"]["status"], "unsupported")
                    self.assertEqual(report["controls"]["fish_tags"]["status"], "not_requested")
                elif backend == "cosyvoice":
                    self.assertEqual("".join(item["text"] for item in compiled["records"]), self.source)
                    self.assertTrue(all("instruct_text" in item for item in compiled["records"]))
                elif backend == "chattts":
                    stripped = compiled["draft_text"].replace("[uv_break]", "")
                    self.assertEqual(stripped, self.source)
                    self.assertEqual(report["controls"]["delivery"]["status"], "unsupported")
                elif backend == "parler":
                    self.assertEqual("".join(item["text"] for item in compiled["segments"]), self.source)
                    self.assertEqual(compiled["voice_description"], self.director["voice_profile"]["description"])
                elif backend == "f5":
                    self.assertEqual("".join(item["text"] for item in compiled["segments"]), self.source)
                    self.assertEqual(report["controls"]["delivery"]["status"], "unsupported")

    def test_eleven_compiles_each_segments_requested_cues_into_draft_text(self):
        source = "问题？定义！"
        director = make_director(source, segments=[
            {
                "id": "S1", "start": 0, "end": 3,
                "delivery": "像在向学员提出问题", "energy": 2,
                "pauses": [{"after": 2, "kind": "short", "target_ms": 250}],
            },
            {
                "id": "S2", "start": 3, "end": 6,
                "pace": "稍慢，给出解释空间", "emphasis_spans": ["定义"],
            },
        ])
        compiled, report = compile_backend(source, director, hashlib.sha256(source.encode()).hexdigest(), "eleven_v4")
        self.assertIn("[voice_director: 请采用“像在向学员提出问题”的表达方式；表达能量等级为 2]", compiled["draft_text"])
        self.assertIn("[voice_director: 语速倾向为“稍慢，给出解释空间”；请适度突出“定义”，不要求逐词精确重音]", compiled["draft_text"])
        self.assertEqual(len(compiled["experimental_cue_tags"]), 2)
        self.assertEqual(compiled["compile_status"], "experimental_manual_audition_required")
        for control in ("delivery", "energy", "pace", "emphasis"):
            self.assertEqual(report["controls"][control]["status"], "model_guided")
            self.assertTrue(report["controls"][control]["applied"])
        import re
        recovered = re.sub(r"\[voice_director: [^\]]+\]|\[(?:short|long) pause\]", "", compiled["draft_text"])
        self.assertEqual(recovered, source)
        self.assertEqual(compiled["exact_text"], source)

    def test_eleven_rejects_bracket_delimiters_in_cue_values(self):
        source = "一段原文。"
        director = make_director(source, segments=[{
            "id": "S1", "start": 0, "end": len(source), "delivery": "neutral] [angry",
        }])
        with self.assertRaisesRegex(ValidationError, "Eleven v4 cue values.*must not contain"):
            compile_backend(source, director, hashlib.sha256(source.encode()).hexdigest(), "eleven_v4")

    def test_azure_xml_escapes_source_text_and_round_trips(self):
        source = "甲 & <乙>。"
        director = make_director(source, segments=[{
            "id": "s", "start": 0, "end": len(source),
            "pauses": [{"after": 2, "kind": "short", "target_ms": 137}],
        }])
        compiled, _ = compile_backend(source, director, hashlib.sha256(source.encode()).hexdigest(), "azure")
        self.assertIn("&amp;", compiled["ssml"])
        self.assertIn("&lt;", compiled["ssml"])
        self.assertEqual("".join(ET.fromstring(compiled["ssml"]).itertext()), source)

    def test_azure_rejects_xml_10_forbidden_source_characters(self):
        source = "甲\x00乙"
        director = make_director(source, segments=[{"id": "s", "start": 0, "end": len(source)}])
        with self.assertRaisesRegex(ValidationError, "forbidden by XML 1.0"):
            compile_backend(source, director, hashlib.sha256(source.encode()).hexdigest(), "azure")

    def test_azure_xml_preserves_crlf_and_entities(self):
        source = "甲\r\n&<乙>"
        director = make_director(source, segments=[{
            "id": "s", "start": 0, "end": len(source),
            "pauses": [{"after": 3, "kind": "long", "target_ms": 900}],
        }])
        compiled, _ = compile_backend(source, director, hashlib.sha256(source.encode()).hexdigest(), "azure")
        self.assertEqual("".join(ET.fromstring(compiled["ssml"]).itertext()), source)

    def test_azure_requires_voice_and_never_uses_unallowlisted_style(self):
        director = make_director(self.source)
        del director["voice_profile"]["azure_voice"]
        with self.assertRaisesRegex(ValidationError, "requires voice_profile.azure_voice"):
            compile_backend(self.source, director, self.source_hash, "azure")
        director = make_director(self.source)
        director["voice_profile"]["azure_style"] = "angry"
        with self.assertRaisesRegex(ValidationError, "must appear"):
            validate_map(self.source, self.source.encode(), director)

    def test_chattts_pause_tokens_require_explicit_allowlist(self):
        director = make_director(self.source)
        director["voice_profile"]["chattts_token_allowlist"] = []
        compiled, report = compile_backend(self.source, director, self.source_hash, "chattts")
        self.assertNotIn("[uv_break]", compiled["draft_text"])
        self.assertEqual(report["controls"]["pauses"]["status"], "unsupported")
        self.assertTrue(report["controls"]["pauses"]["unsupported_items"])

    def test_unknown_backend_fails_without_selecting_a_fallback(self):
        compiled, report = compile_backend(self.source, self.director, self.source_hash, "not-a-tts")
        self.assertFalse(report["supported"])
        self.assertIn("license_review", report)
        self.assertEqual(compiled["compile_status"], "unsupported_backend")
        self.assertIsNone(compiled["draft"])

    def test_fish_compiler_defensively_rejects_unknown_tag_without_schema_call(self):
        director = make_director(self.source, segments=[{
            "id": "s", "start": 0, "end": len(self.source), "fish_tags": ["angry"],
        }])
        with self.assertRaisesRegex(ValidationError, "unsupported Fish tag"):
            compile_backend(self.source, director, self.source_hash, "fish_s2_pro")

    def test_control_tag_collisions_block_unsafe_inline_drafts(self):
        for backend, source in (("eleven_v4", "[short pause]原文"), ("fish_s2_pro", "[angry]原文"), ("chattts", "[uv_break]原文")):
            with self.subTest(backend=backend):
                director = make_director(source, segments=[{
                    "id": "s", "start": 0, "end": len(source), "delivery": "平静讲述",
                    "pauses": [{"after": 3, "kind": "short", "target_ms": 250}],
                }])
                compiled, report = compile_backend(source, director, hashlib.sha256(source.encode()).hexdigest(), backend)
                self.assertIsNone(compiled["draft_text"])
                self.assertEqual(compiled["compile_status"], "blocked_source_control_collision")
                self.assertEqual(report["controls"]["delivery"]["status"], "unsupported")
                self.assertEqual(compiled["exact_text"], source)

    def test_fish_director_text_cannot_forge_closing_control_tag(self):
        source = "甲乙。"
        director = make_director(source, segments=[{
            "id": "s", "start": 0, "end": len(source), "delivery": "neutral] [angry",
        }])
        compiled, report = compile_backend(source, director, hashlib.sha256(source.encode()).hexdigest(), "fish_s2_pro")
        self.assertNotIn("voice_director", compiled["draft_text"])
        self.assertNotIn("[angry]", compiled["draft_text"])
        self.assertEqual(report["controls"]["delivery"]["status"], "unsupported")
        self.assertEqual(compiled["text_segments"][0]["text"], source)

    def test_fish_emits_only_explicit_documented_tags_and_pause(self):
        source = "甲乙。"
        director = make_director(source, segments=[{
            "id": "s", "start": 0, "end": len(source),
            "delivery": "dramatic and emotional", "energy": 4, "pace": "slow",
            "emphasis_spans": ["乙"], "fish_tags": ["excited", "whisper"],
            "pauses": [{"after": 1, "kind": "short", "target_ms": 250}],
        }])
        compiled, report = compile_backend(source, director, hashlib.sha256(source.encode()).hexdigest(), "fish_s2_pro")
        self.assertEqual(compiled["draft_text"], "[excited][whisper]甲[pause]乙。")
        self.assertNotIn("delivery=", compiled["draft_text"])
        self.assertNotIn("[voice_director", compiled["draft_text"])
        self.assertEqual(report["controls"]["fish_tags"]["status"], "model_guided")
        self.assertEqual([item["tag"] for item in report["controls"]["fish_tags"]["emitted"]], ["[excited]", "[whisper]"])
        self.assertEqual(report["controls"]["pauses"]["status"], "model_guided")
        for control in ("delivery", "energy", "pace", "emphasis"):
            self.assertEqual(report["controls"][control]["status"], "unsupported")
        import re
        self.assertEqual(re.sub(r"\[(?:pause|excited|whisper)\]", "", compiled["draft_text"]), source)

    def test_fish_source_tag_collision_blocks_explicit_fish_tags(self):
        source = "[angry]原文"
        director = make_director(source, segments=[{
            "id": "s", "start": 0, "end": len(source), "fish_tags": ["excited"],
        }])
        compiled, report = compile_backend(source, director, hashlib.sha256(source.encode()).hexdigest(), "fish_s2_pro")
        self.assertIsNone(compiled["draft_text"])
        self.assertEqual(compiled["compile_status"], "blocked_source_control_collision")
        self.assertEqual(report["controls"]["fish_tags"]["status"], "unsupported")

    def test_fish_license_review_is_source_backed_and_split(self):
        _, report = compile_backend(self.source, self.director, self.source_hash, "fish_s2_pro")
        review = report["license_review"]
        self.assertEqual(review["status"], "review_required_before_production")
        self.assertEqual(review["code"]["name"], "Fish Audio Community License Agreement, Version 1.0")
        self.assertEqual(review["weights"]["name"], "Fish Audio Research License (S2-Pro weights)")
        self.assertEqual(review["code"]["status"], "review_required_before_production")
        self.assertEqual(review["weights"]["status"], "review_required_before_production")
        self.assertEqual(review["source"]["commit"], "541566932abbaebcb0a40e562a1f846738383f38")
        self.assertEqual([item["path"] for item in review["source"]["files"]], ["README.md", "LICENSE"])
        self.assertEqual(review["source"]["files"][0]["sha256"], "BAA129FAC0B9D32C55B3972BF8CCABEAB3EBBA1CA435E313E20C0ADEA5A7088D")
        self.assertEqual(review["source"]["files"][1]["sha256"], "733A32442087ACBDA12ECAFE8E71EB8EE5890C89B50CE7AC4EA3777FAA3C823E")


class ChunkingTests(unittest.TestCase):
    def test_chunks_reconstruct_unicode_source_without_dropping_separators(self):
        source = "甲🙂。乙丁。丙\n"
        director = make_director(source, segments=[{"id": "s", "start": 0, "end": len(source)}])
        result = build_chunks(source, director, 3, "f5")
        self.assertEqual("".join(item["text"] for item in result["chunks"]), source)
        self.assertTrue(all(len(item["text"]) <= 3 for item in result["chunks"]))
        self.assertEqual(result["text_integrity"]["chunk_characters"], len(source))

    def test_over_limit_atomic_sentence_fails_with_segment_id(self):
        source = "甲乙丙丁戊。"
        director = make_director(source, segments=[{"id": "LONG", "start": 0, "end": len(source)}])
        with self.assertRaisesRegex(ValidationError, "LONG.*atomic sentence"):
            build_chunks(source, director, 4, "f5")

    def test_invalid_max_chars_fails(self):
        source = "甲"
        director = make_director(source, segments=[{"id": "s", "start": 0, "end": 1}])
        with self.assertRaisesRegex(ValidationError, "positive integer"):
            build_chunks(source, director, 0, "f5")


class AlignmentTests(unittest.TestCase):
    def setUp(self):
        self.source = "你好，世界！"
        self.sha = hashlib.sha256(self.source.encode()).hexdigest()

    def test_valid_whisperx_words_pass_after_whitespace_only_normalization(self):
        alignment = {"duration": 2.0, "segments": [{
            "start": 0.0, "end": 2.0,
            "words": [
                {"word": "你好，", "start": 0.1, "end": 0.9, "score": 0.9},
                {"word": "世界！", "start": 1.0, "end": 1.8, "score": 0.8},
            ],
        }]}
        report = audit_alignment(self.source, self.sha, alignment)
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["text_match"]["matches_after_whitespace_normalization"])

    def test_missing_times_are_reported_and_never_filled(self):
        alignment = {"segments": [{"words": [
            {"word": "你好，", "start": 0.1}, {"word": "世界！"},
        ]}]}
        report = audit_alignment(self.source, self.sha, alignment)
        self.assertEqual(report["status"], "FAIL")
        self.assertIsNone(report["aligned_words"][0]["end"])
        self.assertIsNone(report["aligned_words"][1]["start"])
        self.assertEqual(len(report["unaligned_words"]), 2)

    def test_mismatch_nonmonotonic_and_out_of_bounds_are_reported(self):
        alignment = {"duration": 2, "segments": [{
            "start": 0.5, "end": 1.5,
            "words": [
                {"word": "你好，", "start": 1.0, "end": 1.2},
                {"word": "錯字", "start": 0.8, "end": 1.7},
            ],
        }]}
        report = audit_alignment(self.source, self.sha, alignment)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("nonmonotonic" in error for error in report["errors"]))
        self.assertTrue(any("outside its segment" in error for error in report["errors"]))
        self.assertFalse(report["text_match"]["matches_after_whitespace_normalization"])


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.script = self.root / "script.txt"
        self.director = self.root / "director.json"
        source = "第一句。第二句！"
        self.script.write_bytes(source.encode("utf-8"))
        self.director.write_text(json.dumps(make_director(source), ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(args)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_validate_compile_capabilities_and_manifest(self):
        code, out, _ = self.invoke(["validate", "--script", str(self.script), "--director", str(self.director)])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)["valid"])
        out_dir = self.root / "compiled"
        code, out, _ = self.invoke(["compile", "--script", str(self.script), "--director", str(self.director), "--backend", "chattts", "--out", str(out_dir)])
        self.assertEqual(code, 0)
        self.assertTrue((out_dir / "compiled.json").is_file())
        manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["provider_calls"], 0)
        self.assertFalse(manifest["network_access"])
        code, out, _ = self.invoke(["capabilities", "--backend", "f5"])
        self.assertEqual(code, 0)
        capabilities = json.loads(out)
        self.assertEqual(capabilities["profile_id"], "f5-tts-2f866649")
        self.assertIn("license_review", capabilities)
        code, out, _ = self.invoke(["capabilities", "--backend", "unknown"])
        self.assertEqual(code, 2)
        self.assertIn("license_review", json.loads(out))

    def test_output_overwrite_requires_explicit_flag(self):
        out_dir = self.root / "compiled"
        args = ["compile", "--script", str(self.script), "--director", str(self.director), "--backend", "chattts", "--out", str(out_dir)]
        self.assertEqual(self.invoke(args)[0], 0)
        code, _, stderr = self.invoke(args)
        self.assertEqual(code, 2)
        self.assertIn("refusing to overwrite", stderr)
        self.assertEqual(self.invoke(args + ["--overwrite"])[0], 0)

    def test_unknown_backend_writes_explicit_failure_report_without_fallback(self):
        out_dir = self.root / "unknown"
        args = ["compile", "--script", str(self.script), "--director", str(self.director), "--backend", "unknown", "--out", str(out_dir)]
        code, _, _ = self.invoke(args)
        self.assertEqual(code, 2)
        report = json.loads((out_dir / "capability-report.json").read_text(encoding="utf-8"))
        self.assertFalse(report["supported"])
        compiled = json.loads((out_dir / "compiled.json").read_text(encoding="utf-8"))
        self.assertIsNone(compiled["draft"])

    def test_blocked_azure_compile_writes_exact_text_and_capability_failure(self):
        director = json.loads(self.director.read_text(encoding="utf-8"))
        del director["voice_profile"]["azure_voice"]
        self.director.write_text(json.dumps(director, ensure_ascii=False), encoding="utf-8")
        out_dir = self.root / "blocked-azure"
        code, _, _ = self.invoke([
            "compile", "--script", str(self.script), "--director", str(self.director),
            "--backend", "azure", "--out", str(out_dir),
        ])
        self.assertEqual(code, 2)
        compiled = json.loads((out_dir / "compiled.json").read_text(encoding="utf-8"))
        self.assertIsNone(compiled["draft"])
        self.assertEqual(compiled["exact_text"], "第一句。第二句！")
        report = json.loads((out_dir / "capability-report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["compile_status"], "blocked")

    def test_chunk_and_alignment_cli_write_reports(self):
        out_dir = self.root / "chunks"
        code, _, _ = self.invoke([
            "chunk", "--script", str(self.script), "--director", str(self.director),
            "--backend", "f5", "--max-chars", "5", "--out", str(out_dir),
        ])
        self.assertEqual(code, 0)
        chunks = json.loads((out_dir / "chunks.json").read_text(encoding="utf-8"))
        self.assertEqual("".join(chunk["text"] for chunk in chunks["chunks"]), "第一句。第二句！")
        alignment = self.root / "alignment.json"
        alignment.write_text(json.dumps({"segments": [{"words": [
            {"word": "第一句。", "start": 0.0, "end": 1.0}, {"word": "第二句！", "start": 1.0, "end": 2.0},
        ]}]}), encoding="utf-8")
        audit_dir = self.root / "audit"
        code, _, _ = self.invoke(["alignment-audit", "--script", str(self.script), "--alignment", str(alignment), "--out", str(audit_dir)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads((audit_dir / "alignment-audit.json").read_text(encoding="utf-8"))["status"], "PASS")

    def test_malformed_alignment_is_written_as_failure_report(self):
        alignment = self.root / "broken.json"
        alignment.write_text("{bad", encoding="utf-8")
        out_dir = self.root / "broken-audit"
        code, _, _ = self.invoke(["alignment-audit", "--script", str(self.script), "--alignment", str(alignment), "--out", str(out_dir)])
        self.assertEqual(code, 1)
        report = json.loads((out_dir / "alignment-audit.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(report["errors"])


if __name__ == "__main__":
    unittest.main()
