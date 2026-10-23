# Integration Contract: source-to-script plus voice director

## Goal

Integrate the generic source-video-to-clean-narration workflow and the existing voice-director CLI as two independent modules in this repository, with a documented, verifiable handoff between them. Then perform independent audits and comprehensive deterministic tests before updating the already-authorized public repository.

## Scope and non-goals

- Module A: generic, LLM-assisted workflow for video/source inspection, separate ASR and OCR evidence, uncertainty-aware correction, complete source-indexed item coverage, natural speech rewrite, and clean narration output. Source fidelity is established by mapping the complete source and independently reviewing the frozen narration against it.
- Module B: existing offline Python CLI for validating locked narration plus director map, compiling supported backend drafts, lossless chunking, and alignment audit.
- Handoff: narration UTF-8 bytes are frozen by SHA-256; the voice module's `director.json.source_sha256` must equal that hash. No normalization is permitted.
- Every source-to-script run includes one final spoken-delivery assessment and bounded polish performed by the current main harness after drafting; notes remain outside narration, and source mapping plus independent semantic review are refreshed against the polished frozen text.
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

Allow generic integration docs and skill files, tests for the handoff contract, and narrowly required README/reference updates. Existing `voice_director/` behavior is out of scope unless a concrete handoff defect is found and separately justified. One writer owns implementation; independent auditors are read-only.

## D/I/A assessment

- D0: scope is the explicit two-module integration and handoff, with no new provider execution or generated media.
- I2: integration crosses a generative skill workflow and deterministic CLI, sharing a narration artifact and hash contract.
- A2: it changes the public repository's stated product scope and redistributes generic workflow instructions; privacy, source mapping, and license boundaries require independent review.

## Acceptance evidence

1. Written module architecture, operator workflow, limits, and handoff contract.
2. Source-to-script starts from a complete segment-indexed source map; a topic ledger alone cannot pass source-fidelity review.
3. Automated tests verify clean handoff and reject wrong/stale narration hashes.
4. Existing and added deterministic tests pass offline.
5. Separate general audit and source-fidelity audit both return PASS against the same frozen revision; all findings are resolved and re-audited.
6. No license file, private course content, machine paths, or secrets enter the public diff.
7. After gates pass, update the existing GitHub repository and verify the pushed commit.

## Bounded audit repair: input preservation

Concrete defect: `--overwrite` could replace a frozen script, director map, or alignment input when an artifact path aliases it. The CLI repair is limited to rejecting output/input aliases (resolved paths and existing hardlinks) across compile, chunk, and alignment-audit, including the manifest, before writing any artifact. Regression tests must prove unchanged input bytes and no partial batch writes. The user authorized correction, independent re-audit, testing, and publication after those gates pass.

## Evidence not claimed

`ROUTE_UNVERIFIED`; no special model/effort provenance is asserted. `HOOK_UNVERIFIED`; no lifecycle Hook registration is asserted. The bundled multi-agent workflow's terminal notification is a separate operational step.
