# Integrated workflow: source video to rendered lesson

The integrated workflow routes among existing tools: source video to clean narration and visual assets, TTS choice and audition, full audio generation, then captions/timing and HyperFrames rendering.

## Voice and screen are separate teaching channels

Before detailed storyboarding, create a private `voice-screen-map.json`. Each beat records:

- `id`, `duration_seconds`, exact `screen_text`, and the visual `focus`;
- `voice_mode` (`summary`, `verbatim`, or `silent`), the actual `narration`, and `spoken_purpose` for summary narration;
- `screen_only_terms` for identifiers the speaker must not read; technical beats set `technical_display: true`;
- `assets` with a kind (`real_ui`, `official_illustration`, `original_graphic`, or `other`) and source; real UI captures also set `authentic: true`;
- `transition.entry`, `transition.exit`, and `transition.motion` to bind cuts and camera movement to the teaching beat.

For JSON, TOML, code, commands, paths, and exact field values, preserve the complete sanitized text on screen and explain the purpose, sequence, risk, and verification in the voice. `verbatim` requires a `verbatim_reason`. Do not expose credentials; use a clearly named placeholder. Every visual claim needs a source label: official feature descriptions and original diagrams are not UI screenshots. Prefer meaningful 3–10 second beats. Holds longer than 12 seconds require a documented `duration_reason` so learners have time to read. Use the existing HyperFrames/GSAP composition for measured fades, push/zoom, pan, and focus highlights; this map does not render video or synthesize speech.

Validate the map locally, without a provider call:

```powershell
python -m voice_director validate-voice-screen --map ..\courseware-private\voice-screen-map.json
```

The validator checks the declared structure, summary-versus-syntax separation, source labels, long-hold reasons, and common credential patterns. It cannot verify semantic truth, rights, natural delivery, or final synchronization. If `uncertainty` is present, the command returns `AWAITING_HUMAN` and prints the question, evidence, impact, and recommendation. Show that exact packet in the conversation and wait for the user's explicit decision before approving the affected visual or narration. Then update the private map and validate again. Keep this material outside the public repository.

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
2. The current main harness (usually Codex) personally reviews spoken naturalness, records strengths and listener-facing findings, and makes a bounded revision for those findings. Repeat this review/revision loop until its self-evaluation passes. Wording findings require a documented text change; a finding about source evidence or mapping may be resolved with a documented map-only repair and unchanged narration. Do not impose a runtime target.
3. Record assessment, findings, edits, and self-evaluation in the private `harness-review.json`; keep them out of narration.
4. Refresh source-map paragraph references after each text change. A distinct read-only source-fidelity reviewer checks the exact candidate; any non-passing verdict sends the candidate back through another harness round, map refresh, and fresh independent review. An earlier version's PASS does not carry forward.
5. If the final review reports uncertainty as `INSUFFICIENT_EVIDENCE`, run `editorial-gate` to display the source and narration references, observed evidence, question, impact, recommendation, and a blank hash-bound `human-decisions.json` template. Wait for the user's explicit choice. Do not infer approval from silence.
6. A user may choose `accept_as_is` with a recorded response and rationale; the gate then releases as `RELEASED_WITH_HUMAN_DECISIONS`, retaining the original independent-review verdict in the receipt. `request_revision` and `provide_evidence` remain blocked and return to the harness/reviewer loop. All other non-passing verdicts still require correction.
7. Release through `python -m voice_director editorial-gate --bundle <private-run-directory> --out <new-release-directory> [--decisions <human-decisions.json>]`. Give downstream work only the released narration and receipt. Direct legacy `validate`/`compile` commands do not release narration.

## Required source-fidelity gate

When the user wants the original lesson content retained, source-to-script is the first required stage even when the full `courseware-video-remake` workflow is requested. Start from the complete source transcript and preserve its order. A topic or learning-outcome checklist is only an index; it cannot establish that source examples, explanations, exam cues, meaningful repetition, or review prompts survived.

Before drafting, create a private source coverage matrix using [`source-coverage-matrix-template.csv`](../skills/source-to-script/references/source-coverage-matrix-template.csv). Give every numbered SRT segment and every content-bearing item an explicit disposition and a narration reference, or a documented correction/exclusion reason. Keep all useful source content by default. Add explanations and exercises as supplements. Do not use a new hook, a shorter outline, or a style pass to replace mapped source material. When an existing user-edited final is supplied, treat it as the baseline and log any proposed material changes.

A separate read-only reviewer must compare the polished frozen narration and complete source map with the source evidence. Any unmapped or unresolved useful item blocks a source-coverage PASS. If only a topic ledger was checked, report coverage as insufficient.

After any writing or style change, update the source map and repeat the semantic audit against the changed text. The private review bundle binds source evidence, source map, draft, each harness revision, each independent review, and the final candidate with SHA-256 hashes. The gate checks that the final independent review and passing self-evaluation refer to the exact candidate it releases.

Keep the existing workflow's human checkpoints: confirm source-use permission when it is not already established; get approval before sending source material or narration to a cloud provider or incurring paid generation; and proceed to full TTS only after the user accepts the clean narration and voice audition.

Use the [integrated skill](../skills/courseware-pipeline/SKILL.md) as the routing entry point. It describes which existing skill/tool handles each step; it is not a standalone executable or an automatic connector. The [source-to-script skill](../skills/source-to-script/SKILL.md) and [humanized source rewrite](../skills/humanized-source-rewrite/SKILL.md) remain reusable components of the source-to-narration step.

## Working files

Stage 1 exports a clean copy as UTF-8 `narration.txt`. The file contains only words intended to be spoken. Keep the source map, knowledge index, correction log, coverage matrix, and editorial review material in separate files. Store the source video/audio, extracted text, narration, maps, and reports outside the public repository. An alignment audit can contain recognized narration words, so its output is user content too. For example, from the repository root use a sibling private directory such as `..\courseware-private\`; `.gitignore` also excludes `audit/` and `private-work/` as a safeguard.

Only if Voice Director's optional backend-specific draft is needed, freeze the exact byte sequence of the released `narration.txt` before creating `director.json`:

```powershell
$sha = (Get-FileHash -LiteralPath ..\courseware-private\narration.txt -Algorithm SHA256).Hash.ToLowerInvariant()
$sha
```

Set that exact lowercase SHA-256 value as `source_sha256` in `director.json`. The director map's segment offsets count Python Unicode code points in the decoded text. Segments must cover all characters, in order, without gaps or overlaps. Newline conversion, Unicode normalization, or any edit changes the fingerprint and can also invalidate offsets; regenerate the map or review all offsets after a change.

Run the editorial gate for every source-to-script release. The bundle contains `source-evidence.txt`, `source-map.csv` (with `source_item_id`, `disposition`, and `candidate_reference` columns), `draft.txt`, `candidate.txt`, `harness-review.json`, and `independent-review.json`. Review JSON schemas 1 and 2 are shown in [the optimization and evidence contract](EDITORIAL-GATE-OPTIMIZATION.md). The gate validates structure, hash continuity, role declarations, verdicts, and exact-byte copying. It cannot prove that a review was thoughtful, that a source map is complete, that role declarations are truthful, or that narration is semantically accurate.

Use the legacy CLI validation only when using the optional Voice Director path:

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
