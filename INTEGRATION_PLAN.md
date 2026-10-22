# Implementation plan: source video to directed narration

`INTEGRATION_CONTRACT.md` is authoritative. This plan maps its accepted scope into repository files and verification steps.

## Objective

Present the existing source-to-script skills and the Voice Director CLI as one reusable project with two independently usable stages. Stage A uses an LLM/Codex skill workflow to extract, correct, preserve, and rewrite lesson content into a clean narration script. Stage B uses the deterministic offline CLI to validate that exact script, compile provider-specific draft artifacts, split semantic chunks, and audit supplied alignments.

## Scope and boundaries

- Include only generic instructions adapted from the local `courseware-video-remake` and `humanized-source-rewrite` skills and their general editing playbook.
- Keep Stage A explicitly LLM-orchestrated. This repository does not implement ASR, OCR, contextual correction, knowledge-ledger generation, or rewriting as deterministic Python functionality.
- Keep Stage B as the existing offline Python CLI. It never calls TTS providers, generates audio, uploads files, or changes narration text.
- Do not include source-course material, media, private task artifacts, machine-specific paths, credentials, or personal examples.
- Do not add a license. Public visibility does not grant reuse rights.
- Do not modify existing voice-director implementation unless the handoff test exposes a real bridge defect.

## Shared handoff contract

1. Stage A outputs a UTF-8 `narration.txt` containing only the approved, clean spoken copy. Keep the knowledge ledger, correction notes, coverage audit, and prosody direction outside this file.
2. Freeze the exact narration bytes before Stage B. Any text edit, newline conversion, or Unicode normalization after freezing requires regenerating the director map.
3. Stage B `director.json` uses `schema_version: 1`, provides `source_sha256` equal to SHA-256 of the exact UTF-8 narration bytes, and segments that cover the decoded narration in code-point offsets without gaps or overlaps.
4. `python -m voice_director validate --script narration.txt --director director.json` is the acceptance gate. A mismatch blocks the handoff. The CLI's input hash in its manifest records the same script fingerprint.
5. The prose and editorial review remains a Stage A responsibility; the CLI validates structural and byte-level integrity, not content accuracy or voice quality.

## Planned repository changes

- Add `skills/courseware-pipeline/SKILL.md`: integrated entry workflow for the two independent modules.
- Add `skills/source-to-script/SKILL.md`: source extraction, correction, coverage, and clean narration workflow.
- Add `skills/humanized-source-rewrite/SKILL.md` and `references/editing-playbook.md`: reusable content-preservation and spoken-language editing criteria.
- Add `docs/PIPELINE.md` with stage responsibilities, files, commands, and limitations.
- Add `references/source-skill-mapping.md` with frozen source hashes and a requirement-to-destination crosswalk.
- Update `README.md` to describe the integrated two-module project and link to its workflow.
- Add an integration test demonstrating exact-byte hash handoff acceptance and mismatch rejection using the existing CLI.

## Verification and audit targets

- Run the existing standard-library unit suite plus new integration tests.
- Confirm the bundled skills do not contain source-course text/media, local absolute paths, private artifact references, or claims that the CLI performs LLM or TTS work.
- Confirm the no-license state remains intact.
- Inspect the final diff and ensure the handoff contract agrees with `voice_director` validation behavior.
- Compare the source material against the crosswalk and verify each material requirement has a destination in the bundled skills/docs.
