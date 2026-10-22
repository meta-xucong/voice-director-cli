# Integrated workflow: source to directed narration

The repository contains two modules joined by a strict narration-byte handoff. Module 1 handles source understanding and clean-script editing through an LLM skill workflow. Module 2 handles structural validation and deterministic voice-direction artifacts through the offline Python CLI.

## Responsibility map

| Stage | Input | Work | Output | What it does not prove/do |
|---|---|---|---|---|
| 1. Source to script | Authorized video/audio, slides, or extracted materials | Separate ASR and OCR evidence; review uncertain recognition; create atomic knowledge coverage; rewrite for spoken clarity after fidelity passes | `narration.txt` plus separate source ledger, correction log, coverage matrix, review notes | The repository CLI does not run ASR/OCR, perform LLM correction, validate course facts, or rewrite text. |
| 2. Voice direction | Frozen UTF-8 narration plus a director map | Check source fingerprint/coverage; produce supported backend draft metadata, lossless chunks, capability reports, or alignment audits | `compiled.json`, `chunks.json`, reports, and manifest under the selected output folder | No TTS API call, audio generation, provider discovery, upload, playback, or human-quality guarantee. |

Use the [integrated skill](../skills/courseware-pipeline/SKILL.md) to orchestrate both stages. Stage 1 details: [source-to-script skill](../skills/source-to-script/SKILL.md). Optional editorial method: [humanized source rewrite](../skills/humanized-source-rewrite/SKILL.md).

## Handoff file contract

Stage 1 exports a clean copy as UTF-8 `narration.txt`. The file contains only words intended to be spoken. Keep the knowledge ledger and editorial review material in separate files. Store the source video/audio, extracted text, narration, director map, alignment input, and generated reports outside the public repository. An alignment audit can contain recognized narration words, so its output is user content too. For example, from the repository root use a sibling private directory such as `..\courseware-private\`; `.gitignore` also excludes `audit/` and `private-work/` as a safeguard.

Before creating `director.json`, freeze the exact byte sequence of `narration.txt`:

```powershell
$bytes = [System.IO.File]::ReadAllBytes((Resolve-Path ..\courseware-private\narration.txt))
$sha = [Convert]::ToHexString([System.Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()
$sha
```

Set that exact lowercase SHA-256 value as `source_sha256` in `director.json`. The director map's segment offsets count Python Unicode code points in the decoded text. Segments must cover all characters, in order, without gaps or overlaps. Newline conversion, Unicode normalization, or any edit changes the fingerprint and can also invalidate offsets; regenerate the map or review all offsets after a change.

Validate before compiling:

```powershell
python -m voice_director validate --script ..\courseware-private\narration.txt --director ..\courseware-private\director.json
```

The command must return `"valid": true`. A mismatch fails closed. The compilation/chunking manifest records the same input script hash, and reports `provider_calls: 0` and `network_access: false`.

## Typical Stage 2 commands

```powershell
python -m voice_director --help
python -m voice_director capabilities
python -m voice_director compile --script ..\courseware-private\narration.txt --director ..\courseware-private\director.json --backend eleven_v4 --out ..\courseware-private\out
python -m voice_director chunk --script ..\courseware-private\narration.txt --director ..\courseware-private\director.json --backend f5 --max-chars 1200 --out ..\courseware-private\out
python -m voice_director alignment-audit --script ..\courseware-private\narration.txt --alignment ..\courseware-private\whisperx.json --out ..\courseware-private\audit
```

See [README.md](../README.md) for director map fields, backend capability semantics, and the offline test command.

## Quality gates

Stage 1 independently reports extraction coverage, atomic source-to-script coverage, factual/attribution integrity, natural spoken delivery, clean-copy readiness, and unresolved evidence. A high-level outline is not proof of full coverage, and uncertain ASR must not be silently guessed.

Stage 2 structurally validates the director map, exact source hash, and segment coverage. Compile and alignment reports establish only the checks stated in those reports. They do not prove the script is accurate, TTS sounds natural, a service supports a control today, or final audio matches the text.

## Security and reuse boundary

Do not place source-course material, private transcripts, media, narration, director maps, alignment inputs/reports, credentials, or unrelated personal artifacts in the repository. Keep user content in a private work directory outside the clone; the ignore rules for `audit/` and `private-work/` are only a secondary safeguard. The skill folders are not auto-registered by a clone: manually copy `courseware-pipeline`, `source-to-script`, and `humanized-source-rewrite` together into the Codex skills directory, preserving sibling paths and references. No provider requests or uploads are part of these modules. This repository has no license file; public visibility alone does not grant reuse rights.
