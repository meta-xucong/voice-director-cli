# Integrated workflow: source video to rendered lesson

The integrated workflow routes among existing tools: source video to clean narration and visual assets, TTS choice and audition, full audio generation, then captions/timing and HyperFrames rendering.

## Responsibility map

| Handoff | Existing component | Result |
|---|---|---|
| Source video → narration and visual assets | `courseware-video-remake` workflow | Clean narration and visual assets/storyboard |
| TTS choice and audition | User plus the selected provider's existing tool | Provider/voice choice; audition accepted under the existing workflow |
| Narration → final audio | Selected provider's existing TTS tool | Full narration audio |
| Audio → captions and timing | Existing remake workflow | Captions and scene timing based on final audio |
| Audio/assets → render and delivery | User's existing HyperFrames project and remake workflow | Rendered lesson and the workflow's existing delivery checks |

## Required source-to-speech editorial sequence

1. Draft from the complete source map, preserving useful content and source order.
2. The current main harness (usually Codex) personally reviews the completed narration for spoken naturalness, briefly identifies strengths and weaknesses, and performs exactly one bounded polish pass. This is part of every source-to-script run, not an optional extra or delegated worker step. The pass improves spoken syntax, transitions, classroom voice, and unnecessary written-sounding caveats while preserving mapped content. Do not impose a runtime target.
3. Record the concise assessment and edit summary in private editorial notes. Keep them out of `narration.txt`.
4. Refresh source-map paragraph references and rerun source-to-draft coverage and draft-to-source integrity after the polish. The independent read-only source-fidelity reviewer checks this polished frozen version; an earlier draft's PASS does not carry forward.

## Required source-fidelity gate

When the user wants the original lesson content retained, source-to-script is the first required stage even when the full `courseware-video-remake` workflow is requested. Start from the complete source transcript and preserve its order. A topic or learning-outcome checklist is only an index; it cannot establish that source examples, explanations, exam cues, meaningful repetition, or review prompts survived.

Before drafting, create a private source coverage matrix using [`source-coverage-matrix-template.csv`](../skills/source-to-script/references/source-coverage-matrix-template.csv). Give every numbered SRT segment and every content-bearing item an explicit disposition and a narration reference, or a documented correction/exclusion reason. Keep all useful source content by default. Add explanations and exercises as supplements. Do not use a new hook, a shorter outline, or a style pass to replace mapped source material. When an existing user-edited final is supplied, treat it as the baseline and log any proposed material changes.

A separate read-only reviewer must compare the polished frozen narration and complete source map with the source evidence. Any unmapped or unresolved useful item blocks a source-coverage PASS. If only a topic ledger was checked, report coverage as insufficient.

After any writing or style change, update the source map and repeat the semantic audit against the changed text. Keep the exact audited draft hash in the private audit report so a later edit cannot inherit a stale PASS.

Keep the existing workflow's human checkpoints: confirm source-use permission when it is not already established; get approval before sending source material or narration to a cloud provider or incurring paid generation; and proceed to full TTS only after the user accepts the clean narration and voice audition.

Use the [integrated skill](../skills/courseware-pipeline/SKILL.md) as the routing entry point. It describes which existing skill/tool handles each step; it is not a standalone executable or an automatic connector. The [source-to-script skill](../skills/source-to-script/SKILL.md) and [humanized source rewrite](../skills/humanized-source-rewrite/SKILL.md) remain reusable components of the source-to-narration step.

## Working files

Stage 1 exports a clean copy as UTF-8 `narration.txt`. The file contains only words intended to be spoken. Keep the source map, knowledge index, correction log, coverage matrix, and editorial review material in separate files. Store the source video/audio, extracted text, narration, maps, and reports outside the public repository. An alignment audit can contain recognized narration words, so its output is user content too. For example, from the repository root use a sibling private directory such as `..\courseware-private\`; `.gitignore` also excludes `audit/` and `private-work/` as a safeguard.

Only if Voice Director's optional backend-specific draft is needed, freeze the exact byte sequence of `narration.txt` before creating `director.json`:

```powershell
$sha = (Get-FileHash -LiteralPath ..\courseware-private\narration.txt -Algorithm SHA256).Hash.ToLowerInvariant()
$sha
```

Set that exact lowercase SHA-256 value as `source_sha256` in `director.json`. The director map's segment offsets count Python Unicode code points in the decoded text. Segments must cover all characters, in order, without gaps or overlaps. Newline conversion, Unicode normalization, or any edit changes the fingerprint and can also invalidate offsets; regenerate the map or review all offsets after a change.

Run the CLI validation only when using that optional Voice Director path:

```powershell
python -m voice_director validate --script ..\courseware-private\narration.txt --director ..\courseware-private\director.json
```

The command must return `"valid": true`. Hash validation is optional and applies only when using Voice Director; it does not generate TTS audio.

## Optional Voice Director commands

```powershell
python -m voice_director --help
python -m voice_director capabilities
python -m voice_director compile --script ..\courseware-private\narration.txt --director ..\courseware-private\director.json --backend eleven_v4 --out ..\courseware-private\out
python -m voice_director chunk --script ..\courseware-private\narration.txt --director ..\courseware-private\director.json --backend f5 --max-chars 1200 --out ..\courseware-private\out
python -m voice_director alignment-audit --script ..\courseware-private\narration.txt --alignment ..\courseware-private\whisperx.json --out ..\courseware-private\audit
```

See [README.md](../README.md) for director map fields, backend capability semantics, and the offline test command. The chosen provider's existing TTS tool and the existing HyperFrames project handle audio generation and video rendering.

## Security and reuse boundary

Do not place source-course material, private transcripts, media, narration, TTS audio, credentials, or unrelated personal artifacts in the repository. The chosen TTS tool may send narration to its provider under that tool's existing data-use behavior. The skill folders are not auto-registered by a clone: install `courseware-pipeline`, `source-to-script`, and `humanized-source-rewrite` together, preserving sibling paths and references. This repository has no license file; public visibility alone does not grant reuse rights.
