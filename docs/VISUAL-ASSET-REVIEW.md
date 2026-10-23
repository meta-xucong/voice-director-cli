# Visual asset search and harness review

## Frozen change contract

The courseware workflow must search the Internet for visual assets before asking the user to supply images. After the beat map and narration are ready, the main harness must review the search evidence and available candidates in detail, beat by beat, then choose whether each beat is adequately covered, needs a human decision, or needs a user-provided image. A user-image request must show concrete search evidence, rejected candidates and reasons, the exact visual gap, its teaching impact, and a specific image request in the conversation.

The change extends the in-progress visual direction/sample workflow without replacing it. It adds a private evidence manifest and an offline CLI gate that validates completeness, hash continuity, provenance declarations, review coverage, and the stated decision. Internet search, image selection, semantic assessment, and conversation display remain harness responsibilities; the CLI must not claim to have performed them.

Non-goals: implement a network image-search or downloading client; call an image-generation service; decide semantic fit automatically; change rendering or the existing three-style/sample approval gate; put course assets or user content in the public repository.

Baseline: branch `editorial-gate-20261023`, HEAD `cb7a37f`; pre-existing working changes in `docs/PIPELINE.md`, `skills/courseware-pipeline/SKILL.md`, `voice_director/cli.py`, plus untracked `voice_director/visual_gate.py` and `tests/test_visual_gate.py` are retained as task baseline and are in scope only as needed to integrate the new stage. No other pre-existing changes may be overwritten.

Risk: D0 (the decision is specified by the user's request and repository pipeline); I1 (new evidence contract, validator, CLI command, and workflow integration); A1 (cross-file gate has negative paths and rights/provenance requirements). Requested audit route: `gpt-6-luna/xhigh`; actual child runtime provenance will be reported only if independently available.

Acceptance evidence:

1. The integrated skill requires Internet image search before any image request and a thorough harness review tied to the exact narration and beat-map hashes.
2. Each beat with a visual need has at least one documented search. A user-image recommendation requires at least three distinct query variants and assessment of every returned candidate for that beat.
3. The review evaluates teaching fit, visual/factual match, legibility at intended display size, authenticity where a real interface is claimed, and rights/provenance. Any insufficiency is backed by evidence and a concrete learner impact.
4. The CLI opens the visual stage only when every beat is adequately covered. It returns a human-review packet when the harness requests an image or a human decision, and rejects stale hashes, missing beats/searches, unassessed candidates, unsupported verdicts, or a recommendation unsupported by the recorded evidence.
5. Tests cover adequate coverage, user-image request, human-decision uncertainty, missing/weak searches, unassessed results, and stale/tampered input evidence. The full offline test suite passes.
6. A separate read-only A1 audit returns PASS against this contract and the frozen diff. No claim of independent acceptance is made without that result.

## Private manifest contract v1

The manifest is stored with the private courseware run. It binds the exact `narration.txt` and `voice-screen-map.json` using lowercase SHA-256 hashes. Search entries record a unique id, query, query type (`exact`, `official`, or `alternative`), engine, timestamp, covered beat ids, and inspected result candidate ids. Candidate records include a stable id, associated beat ids, title, source URL or explicit local/user source, visual kind, local relative image path and hash, dimensions, source description, rights status and evidence. A later user-provided candidate can be attached to its beat and re-reviewed without falsely recording it as an Internet result. All paths stay inside the private run directory.

The harness review records its identity, the exact input hashes, a detailed per-beat need statement, all applicable search ids, all returned candidate assessments and criterion evidence, a selected candidate when covered, and one decision: `use_candidate`, `ask_user_for_image`, or `needs_human_decision`. The criteria are teaching relevance, visual/factual match, legibility, authenticity when the beat claims a real UI, and rights/provenance. Every criterion has a `pass`, `partial`, or `fail` status plus concrete evidence. A candidate is adequate only when all applicable criteria pass.

For `ask_user_for_image`, the beat must cite at least three distinct query variants, every returned candidate must be assessed, and no adequate candidate may remain. The human packet lists the exact gap, why alternatives failed, what the learner would miss, and the image characteristics requested. If an issue concerns uncertain authenticity, source, or rights rather than a missing image, use `needs_human_decision` and show the question, evidence, impact, and recommendation instead of claiming that an image is needed.

The validator enforces structure, path containment, hashes, coverage, evidence presence, and conservative decision consistency. It cannot prove that a search really ran, that a source's rights statement is accurate, or that a harness judgment is semantically sound. The workflow therefore requires the main harness to inspect the actual source pages and image files, then show the exact resulting packet in the conversation. Only a `PASS` authorizes proceeding to visual-direction selection and the existing design-sample gate.
