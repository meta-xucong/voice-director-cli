# Integration Contract: source-to-script plus voice director

## Goal

Integrate the generic source-video-to-clean-narration workflow and the existing voice-director CLI as two independent modules in this repository, with a documented, verifiable handoff between them. Then perform independent audits and comprehensive deterministic tests before updating the already-authorized public repository.

## Scope and non-goals

- Module A: generic, LLM-assisted workflow for video/source inspection, separate ASR and OCR evidence, uncertainty-aware correction, complete source-indexed item coverage, natural speech rewrite, and clean narration output. Source fidelity is established by mapping the complete source and independently reviewing the frozen narration against it.
- Module B: existing offline Python CLI for validating locked narration plus director map, compiling supported backend drafts, lossless chunking, and alignment audit.
- Handoff: narration UTF-8 bytes are frozen by SHA-256; the voice module's `director.json.source_sha256` must equal that hash. No normalization is permitted.
- Every source-to-script run includes as many bounded main-harness spoken-delivery assessment/revision rounds as needed to reach a passing self-evaluation. Wording findings must link to changed text; evidence-only findings may be resolved by a documented source-map repair with unchanged narration. Refresh the source map after wording edits, and require a distinct read-only semantic review against the exact final text and map. Every source-to-script narration handoff passes the deterministic editorial gate before downstream TTS work.
- The repository may describe the combined workflow as an integrated project, but must state clearly that Module A is executed through an LLM/skill workflow, while the Python CLI does not perform ASR/OCR, semantic correction, rewriting, or TTS synthesis.
- Do not include any course-specific source transcript, media, outputs, user data, secrets, machine-specific paths, or unrelated personal workflow artifacts.
- Do not add a software license. Preserve the user's choice that the repository is public for viewing without a license grant.
- No provider/API requests, uploads, TTS generation, or paid calls are in scope.

## Baseline

- Repository: `voice-director-cli`, branch `main`, base commit `d720fca`
- Initial worktree: clean; tracking `origin/main`
- Baseline deterministic tests: `python -m unittest discover -s tests -v` — 33 tests passed.
- Frozen source references:
  - `courseware-video-remake/SKILL.md` SHA-256 `ec2cb0b3b04f193c2f164e6435805007d008de16a95b611e6e102d63885f8a3d`
  - `humanized-source-rewrite/SKILL.md` SHA-256 `cdff4db5fbf0cfc21020ecf861d72d3f05911ae2092721644b9fe842859c7f26`
  - `humanized-source-rewrite/references/editing-playbook.md` SHA-256 `a231b51fe04bb4548e5879ea6356b3cff7889b060bd0f5cf66448e7781ea7788`

## Change boundary

Allow generic integration docs and skill files, tests for the handoff contract, narrowly required README/reference updates, and a deterministic offline `voice_director editorial-gate` command with its module/tests. Keep existing `validate`, `compile`, `chunk`, and `alignment-audit` behavior compatible. The gate validates hash-bound workflow evidence and exact-byte release only; it does not provide semantic review or prove declared identities. One writer owns implementation; independent auditors are read-only.

## D/I/A assessment

- D1: an authorized follow-on adds a local release gate and iterative review-evidence contract, without changing provider execution or generating media.
- I2: integration crosses a generative skill workflow and deterministic CLI, sharing a narration artifact and hash contract.
- A1: it adds a release decision for supplied artifacts and stale-review invalidation; privacy and role claims require independent review.

## Acceptance evidence

1. Written module architecture, operator workflow, limits, and handoff contract.
2. Source-to-script starts from a complete segment-indexed source map; a topic ledger alone cannot pass source-fidelity review.
3. Automated tests verify clean handoff and reject wrong/stale narration hashes.
4. Existing and added deterministic tests pass offline.
5. Separate general audit and source-fidelity audit both return PASS against the same frozen revision; all findings are resolved and re-audited.
6. No license file, private course content, machine paths, or secrets enter the public diff.
7. Push the reviewed and tested change to the already configured GitHub remote, as explicitly authorized by the user in the follow-on request.

## Follow-on uncertainty review contract

- If a final independent review identifies uncertainty with `INSUFFICIENT_EVIDENCE`, the CLI must show a structured, hash-bound human review packet with source location, narration location, observed evidence, unresolved question, impact, and recommendation. It must not guess or silently omit the uncertainty.
- The packet includes a blank decision template. No decision defaults to acceptance. A human decision must be explicit and must bind the exact source, map, candidate, and independent-review bytes.
- Only a final review with purely `INSUFFICIENT_EVIDENCE` uncertainty items can be considered for user disposition. `NEEDS_REVISION`, known errors, spoken-delivery failure, clean-copy failure, or missing/corrupt evidence remain blocking.
- `accept_as_is` may release with a distinct `RELEASED_WITH_HUMAN_DECISIONS` state. The receipt preserves the independent review's original non-pass verdict and lists each accepted uncertainty and decision-file hash. It must never relabel the review as PASS.
- `request_revision` and `provide_evidence` remain blocked and route the work back through the harness and a fresh independent review. Any material hash change invalidates prior decisions.
- Backward compatibility: schema-v1 bundles that already pass all checks remain releasable; schema-v1 non-pass reviews do not gain a human override.

## Bounded audit repair: input preservation

Concrete defect: `--overwrite` could replace a frozen script, director map, or alignment input when an artifact path aliases it. The CLI repair is limited to rejecting output/input aliases (resolved paths and existing hardlinks) across compile, chunk, and alignment-audit, including the manifest, before writing any artifact. Regression tests must prove unchanged input bytes and no partial batch writes. The user authorized correction, independent re-audit, testing, and publication after those gates pass.

## Evidence not claimed

`ROUTE_UNVERIFIED`; no special model/effort provenance is asserted. `HOOK_UNVERIFIED`; no lifecycle Hook registration is asserted. The bundled multi-agent workflow's terminal notification is a separate operational step.
