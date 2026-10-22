---
name: courseware-pipeline
description: Coordinate a source-video-to-clean-narration workflow with the offline Voice Director CLI. Use when a user wants to extract, correct, preserve, rewrite, then prepare narration for a selectable TTS backend.
metadata:
  short-description: Source video to validated voice direction
---

# Courseware Pipeline

This is the integrated workflow entry point. It coordinates two independent modules; it does not imply that the Python CLI performs the LLM work.

The skill files in this repository are not automatically registered with Codex. Run `scripts/install.ps1` from the repository root or follow the [repository installation guide](https://github.com/meta-xucong/voice-director-cli/blob/main/INSTALL.md) to install the four related Skills together, preserving their sibling structure and the rewrite skill's `references/` folder. Keep source media, extracted text, narration, director maps, and generated reports in a private work directory outside the public repository; alignment reports can contain narration words.

## Modules

1. **Source to script (LLM/skill stage):** Read `../source-to-script/SKILL.md`. Extract audio and slide evidence separately, correct uncertainty with context, preserve every useful knowledge item, then produce a clean narration file.
2. **Voice direction (deterministic CLI stage):** Use this repository's `voice_director` Python package and the `director.json` contract. Freeze narration bytes, create segment and prosody directions, and validate the hash-bound handoff.

The modules can be used independently. If a user supplies an already-approved narration, begin at Module 2. If they only want a clean script, stop after Module 1.

## Required handoff

- Module 1 produces UTF-8 `narration.txt` containing only spoken copy. Keep source ledger, correction log, coverage matrix, and editorial notes in separate files.
- Freeze the exact narration bytes before creating `director.json`. Do not normalize Unicode, change line endings, or edit wording after the hash is made. Any text change requires recalculating the hash and reviewing segment offsets.
- `director.json.source_sha256` must be the lowercase SHA-256 of the exact bytes of `narration.txt`; segment `start` and `end` positions index the decoded text by Python Unicode code points and must cover it in order without gaps or overlaps.
- Run `python -m voice_director validate --script narration.txt --director director.json`. Continue only on `valid: true`.
- Use `python -m voice_director compile ...` or `chunk ...` as needed. The tool writes offline draft artifacts and reports capabilities; it does not synthesize speech or contact providers.

## Boundaries

- Keep ASR/OCR evidence, confidence judgments, and correction notes outside the spoken script.
- Treat source fidelity, factual integrity, naturalness, and structural validation as separate checks.
- Do not claim complete source coverage when extraction or review was partial.
- The CLI cannot establish transcript accuracy, factual correctness, natural TTS delivery, provider behavior, publication rights, or audio/video synchronization.
- This repository has no software license. Its public visibility does not grant reuse rights.

For end-to-end commands and file layout, see `../../docs/PIPELINE.md`.
