# Voice Director CLI

This standard-library-only tool validates a locked UTF-8 narration script, prepares backend-specific draft artifacts, builds lossless chunks, and audits word-alignment JSON. It is offline: it does not install or load models, call TTS APIs, upload text, edit audio, or rewrite the narration.

Run commands from this directory with Python 3.12:

```powershell
python -m voice_director --help
python -m voice_director validate --script narration.txt --director director.json
python -m voice_director capabilities
python -m voice_director compile --script narration.txt --director director.json --backend eleven_v4 --out out
python -m voice_director chunk --script narration.txt --director director.json --backend f5 --max-chars 1200 --out out
python -m voice_director alignment-audit --script narration.txt --alignment whisperx.json --out audit
```

Use `--overwrite` only when replacing artifacts in the chosen output directory. All generated files use fixed filenames under `--out`; input files are read-only. Each generated manifest records input and artifact hashes, `provider_calls: 0`, and `network_access: false`.

## Director map v1

The top-level object must contain exactly `schema_version`, `source_sha256`, `voice_profile`, and `segments`. The source hash is calculated from the exact source UTF-8 bytes, without newline or Unicode normalization. Segment and pause offsets are absolute Python Unicode code-point offsets into the decoded source. Segments must cover the whole source in order with no gaps or overlaps. Pause offsets fall in `(segment.start, segment.end]`.

Example:

```json
{
  "schema_version": 1,
  "source_sha256": "<64 lowercase hex characters>",
  "voice_profile": {
    "description": "清晰、亲切、克制的普通话课堂讲解",
    "azure_voice": "zh-CN-XiaoxiaoNeural",
    "azure_style_allowlist": ["chat"],
    "azure_style": "chat",
    "chattts_token_allowlist": ["[uv_break]", "[lbreak]"]
  },
  "segments": [
    {
      "id": "S001",
      "start": 0,
      "end": 12,
      "delivery": "自然地提出问题，结尾留一点思考空间",
      "function": "question",
      "energy": 2,
      "pace": "steady",
      "emphasis_spans": ["关键术语"],
      "fish_tags": ["excited"],
      "pauses": [{"after": 8, "kind": "short", "target_ms": 250}],
      "pronunciation_overrides": [{"text": "重", "pronunciation": "chóng"}]
    }
  ]
}
```

All fields outside the v1 allowlist are rejected. `fish_tags` accepts only the exact values `excited` and `whisper`, with no duplicates. On Fish S2-Pro, these explicitly requested values become the documented `[excited]` and `[whisper]` tags; a pause event becomes `[pause]`. Fish free-text `delivery`, `energy`, `pace`, and `emphasis` are unsupported and are never converted into custom bracket syntax. Other backends report `fish_tags` as unsupported when requested. Pronunciation overrides use `{ "text": ..., "pronunciation": ... }`; the target spelling must occur in its segment. `energy` is retained as an integer direction without claiming a universal numeric scale. Azure compilation requires `voice_profile.azure_voice`. An Azure style is emitted only if the exact style string also appears in `azure_style_allowlist`; this caller-supplied list does not prove that a cloud voice currently supports it. ChatTTS tokens are emitted only from the tool's known token set and only when also explicitly listed in `chattts_token_allowlist`.

## Capability and fallback behavior

The capability report gives every requested control one of `native_exact`, `model_guided`, `unsupported`, or `not_requested`, plus reasons and emitted items where relevant. An unsupported control is never silently dropped. Eleven v4 compiles requested delivery, energy, pace, and emphasis into an experimental `[voice_director: ...]` natural-language cue tag in `draft_text`; each requested control is reported as model-guided, and manual audition is required. This cue does not promise deterministic word-level emphasis. Cue values containing `[` or `]` are rejected. `exact_text` retains the original narration separately, so removing the emitted cue and pause tags recovers the exact source. If a required backend setting is missing, compilation is blocked; `compiled.json` retains the exact narration and contains no backend draft, alongside the capability report and manifest. Unknown backends have no automatic fallback. If a source already contains bracketed control-like tags, Eleven v4 and Fish drafts are blocked; ChatTTS drafts are blocked if a reserved token occurs in the source. The tool preserves the exact source in `exact_text` in every compiled artifact and does not rewrite the script to escape such collisions.

Every profile and capability report includes `license_review` with separate `code` and `weights` entries. Fish fields identify the license materials and frozen README/LICENSE hashes; other backends are marked `not_assessed`. The status asks for review before production use and is not a legal conclusion.

Capability profiles are frozen declarations, not runtime discovery. Repository-backed profile IDs refer to commits recorded in `references/frozen-sources.json`; Eleven v4 and Azure profile limits are those declared by TaskSpec v1 and must be independently checked against the chosen service/version. Model-guided means the adapter emitted a soft instruction or documented tag, not that the eventual audio will obey it.

The Azure adapter serializes SSML with `xml.etree.ElementTree`, escapes source text, and reparses its output to verify that concatenated text nodes equal the original script. Azure `<break time="...ms"/>` uses the requested integer milliseconds in the draft; this verifies serialization, not playback accuracy. Eleven v4 pause tags are qualitative and do not encode exact milliseconds. Eleven v4 cue tags are experimental natural-language prompts, not a guarantee that the service will realize every direction. No adapter sends a request.

Chunking first respects director segments; sentence punctuation is used only to split a segment that exceeds `--max-chars`. A sentence that still exceeds the limit fails with the segment ID; the CLI never cuts through it. Rejoining chunk text must equal the source exactly.

The alignment audit compares concatenated WhisperX `words[].word` values to the source after whitespace-only normalization. It does not normalize punctuation, spelling, or Unicode composition. Missing word times stay missing and are reported; malformed, decreasing, negative, out-of-segment, or over-duration intervals are errors. Alignment results are not ASR or phonetic validation.

## Tests

Run the deterministic standard-library suite offline:

```powershell
python -m unittest discover -s tests -v
```


## License

No license has been selected for this project. Public visibility does not grant permission to reuse, modify, or distribute the code. A license can be added by the rights holder later.
