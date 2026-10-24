# Source-to-Voice Courseware Pipeline

This repository provides source-to-narration guidance and offline voice-direction tools. For the full flow, use the [integrated pipeline skill](skills/courseware-pipeline/SKILL.md) as the routing entry: it reuses `courseware-video-remake`, gets the TTS choice, follows that workflow's narration and voice-audition acceptance points, then hands off to the selected existing TTS tool and the user's HyperFrames project. This repository does not add a second renderer or a new orchestration engine.

1. **Source to clean narration** is an LLM/skill workflow for separate ASR/OCR evidence, uncertainty-aware correction, complete source-segment coverage, and a natural spoken rewrite. The current main harness repeats bounded spoken-delivery review and revision rounds until self-evaluation passes. A separate reviewer checks the exact final candidate against complete source evidence and map. Every new source-to-script handoff must pass the offline editorial gate; only its released `narration.txt` is eligible downstream. Start with [the integrated pipeline skill](skills/courseware-pipeline/SKILL.md) or [the source-to-script module](skills/source-to-script/SKILL.md).
2. **Voice direction** is the deterministic, offline Python CLI described below. It validates a locked UTF-8 narration script and director map, prepares backend-specific draft artifacts, builds lossless chunks, and audits word-alignment JSON.

The editorial gate validates a private evidence bundle and copies candidate bytes exactly; legacy `validate`/`compile` commands remain separate voice-direction tools and are not a narration release signal. If a final review contains only typed `INSUFFICIENT_EVIDENCE` uncertainties, the gate displays a human decision packet and blank template. The user may explicitly accept residual uncertainty, with a distinct receipt status that preserves the original review verdict. It never guesses or defaults to approval. The pipeline skill is a routing guide that reuses installed skills and tools; it is not a standalone automation executable. The existing remake workflow can still require source-use permission, approval before cloud transfer or paid generation, and acceptance of the narration and voice audition. See [the chained workflow and handoffs](docs/PIPELINE.md). The CLI does not run ASR/OCR, perform LLM correction or rewriting, judge semantic quality, generate audio, call TTS services, or upload content.

For courseware visuals, the integrated skill searches the Internet before requesting images, then has the main harness assess each retained candidate against every voice/screen beat for teaching fit, factual match, legibility, UI authenticity, and rights/provenance. If no candidate is suitable after the required search coverage, or evidence leaves a concrete uncertainty, it presents the actual evidence and a specific image request or decision question in the conversation. The offline CLI checks the review packet's hashes, paths, evidence coverage, and completeness; it does not search the Internet or decide semantic suitability.

The visual workflow then presents three distinct design directions for user selection, builds a 20–60 second representative HyperFrames sample, and runs a hash-bound quality review before asking for sample approval. The quality review checks FFprobe metadata, the complete render-project inventory, FFmpeg pixel equality for sampled frames, the selected direction image, screenshot crop/upscale limits, annotation alignment, motion stability, readability and polish findings. After explicit approval of that exact sample, the same gate requires a full-video review covering every beat before delivery. The CLI checks evidence and measurements; the harness inspects actual visuals and playback, and unresolved uncertainty is shown in the conversation for the user to decide. This is a workflow gate and does not intercept direct HyperFrames render commands. See [the quality-gate contract and commands](docs/VISUAL-QUALITY-GATE.md).

## Install with Codex

Ask Codex: “Read `https://github.com/meta-xucong/voice-director-cli`, follow its [INSTALL.md](INSTALL.md), and install the project and its Codex skills on this computer.” The guide explains the clone location, and [the setup script](scripts/install.ps1) installs the related skills, checks Python 3.12, and runs the offline tests. It uses WinGet to install Python only when Python 3.12 is missing. The project has no pip dependencies.

The `skills/` entries are plain skill files in this repository; cloning it does not register them with Codex. Use the installer above to place the four related folders in your Codex skills directory while preserving their sibling structure and the rewrite skill's `references/` folder. Keep course inputs, narration, director maps, and generated reports outside this public repository. Alignment reports can contain recognized narration words; use a private work directory such as a sibling `courseware-private` folder. The `.gitignore` entries are an extra safeguard, not a substitute for keeping user material outside the repository.

The Python package uses only the standard library and remains offline: it does not install or load models, call TTS APIs, upload text, edit audio, or rewrite the narration. The courseware video quality gate additionally needs FFmpeg's `ffprobe` and `ffmpeg` executables on `PATH` or provided with `--ffprobe` and `--ffmpeg`; the installer does not install FFmpeg.

Run commands from this directory with Python 3.12:

```powershell
python -m voice_director --help
python -m voice_director editorial-gate --bundle ..\courseware-private\editorial-run --out ..\courseware-private\release [--decisions ..\courseware-private\human-decisions.json]
python -m voice_director validate --script ..\courseware-private\narration.txt --director ..\courseware-private\director.json
python -m voice_director capabilities
python -m voice_director compile --script ..\courseware-private\narration.txt --director ..\courseware-private\director.json --backend eleven_v4 --out ..\courseware-private\out
python -m voice_director chunk --script ..\courseware-private\narration.txt --director ..\courseware-private\director.json --backend f5 --max-chars 1200 --out ..\courseware-private\out
python -m voice_director alignment-audit --script ..\courseware-private\narration.txt --alignment ..\courseware-private\whisperx.json --out ..\courseware-private\audit
python -m voice_director review-visual-assets --manifest ..\courseware-private\visual-asset-review.json --narration ..\courseware-private\narration.txt --map ..\courseware-private\voice-screen-map.json
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
