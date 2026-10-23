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

1. Stage A outputs a UTF-8 `narration.txt` containing only approved, clean spoken copy. After drafting, the current main harness personally assesses spoken delivery and repeats bounded review/revision rounds until its self-evaluation passes. Every revision addresses recorded finding IDs and refreshes the source map. A distinct read-only reviewer compares the exact final narration against the complete source map. Release through `voice_director editorial-gate`; only its `release/narration.txt` is eligible for downstream TTS. Keep all review notes outside narration.
2. Freeze the exact narration bytes before Stage B. Any text edit, newline conversion, or Unicode normalization after freezing requires regenerating the director map.
3. Stage B `director.json` uses `schema_version: 1`, provides `source_sha256` equal to SHA-256 of the exact UTF-8 narration bytes, and segments that cover the decoded narration in code-point offsets without gaps or overlaps.
4. `python -m voice_director editorial-gate --bundle <private-run-directory> --out <new-release-directory>` is the narration release gate. The legacy `validate` command still validates only the director-map hash and is not a release signal. A later Stage B director map must use the released narration bytes and their exact hash.
5. If a final independent review reports only `INSUFFICIENT_EVIDENCE` uncertainties, the CLI displays a hash-bound human review packet and blank decision template. It never defaults to approval. Explicit `accept_as_is` decisions permit a separately labeled release that retains the original non-pass verdict; revision or evidence requests remain blocked until a fresh review passes.
6. The prose and editorial review remains a Stage A responsibility; the CLI validates structural and byte-level integrity, not content accuracy or voice quality.

## Planned repository changes

- Add a deterministic `editorial-gate` CLI command, strict evidence schema, and offline tests while preserving existing command behavior.
- Update source-to-script, courseware-pipeline, and humanized-source-rewrite skills so the iterative review/revision loop and editorial gate are normative.
- Add `skills/courseware-pipeline/SKILL.md`: integrated entry workflow for the two independent modules.
- Add `skills/source-to-script/SKILL.md`: source extraction, correction, coverage, and clean narration workflow.
- Add a private-use source coverage matrix template for mapping source segments to the final narration.
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
