---
name: source-to-script
description: Turn an authorized lesson video or source recording into a complete, accurate, natural, speech-ready narration script while retaining all useful source information.
metadata:
  short-description: Evidence-first video transcript to narration
---

# Source Video to Narration Script

Use this module for the first stage of the pipeline. It is an LLM-assisted editorial workflow, not a program implemented by the Voice Director CLI.

## 1. Scope and source evidence

- Confirm the user has rights or permission to adapt the source when that is not already established. Keep any authorization scoped to the supplied source and approved use.
- Record source identity, audience, purpose, language, output location, terminology constraints, and any explicit length or exclusion decision. Do not impose a shorter target runtime by default.
- Inspect source duration, streams, and available companion materials. Treat spoken audio and displayed text as separate evidence channels.
- Transcribe the full audio and OCR every distinct slide/page or materially changed frame. Preserve raw ASR/OCR separately with timestamps or page/frame IDs. Sparse screenshots do not establish complete visual-text coverage.
- Review low-confidence spans and high-impact items (names, numbers, definitions, negation, lists, examples, terminology, and exam wording) against available audio/pixels. State what was actually verified.
- When factual correction or verification is needed, check high-impact proper nouns (authors, titles, organizations, places), dates/numbers, and technical or disputed claims against reliable references. Use the reference to assess the factual claim, not to infer what the speaker literally said; keep factual corrections distinct from ASR repairs, preserve attribution, and record evidence and confidence outside narration.

## 2. Correct uncertain extraction without guessing

- Keep raw ASR immutable. For an unclear/accented/domain-specific phrase, generate bounded interpretations using neighboring audio/text, the full lesson context, synchronized slides/OCR, and reliable references when factual checking is needed.
- Keep “likely meaning” separate from “exact words spoken.” A domain reference may verify a fact but cannot establish the speaker's exact wording; slide text cannot establish pronunciation.
- Track source span, raw recognition, candidate meaning, evidence, semantic confidence, verbatim confidence, chosen narration wording, and rationale in an editorial correction log.
- Correct an ASR error only when evidence supports it. For medium confidence, paraphrase only the supported meaning and mark the inference outside the narration. For low confidence, retain uncertainty and do not silently invent or discard a useful point.
- Distinguish ASR repair from a correction to a factual/logical claim in the source. Make material corrections and their evidence visible in notes.
- Do not silently rewrite a source claim into a different attribution or stronger conclusion. If reference evidence is uncertain or conflicts, preserve the source attribution and uncertainty or flag the item for review.

## 3. Build the coverage contract before drafting

- Build a source map from the complete transcript in source order before writing an outline. Split it into content-bearing items and give each a stable ID linked to timestamped speech and, where relevant, slide/page evidence. A topic ledger is an index, not the coverage contract: include explanations, examples, comparisons, anecdotes that teach, lists, exam cues, corrections, caveats, meaningful repetition, review questions, and conclusions.
- Default every content-bearing source item to `retain`. Do not mark an item optional or redundant merely because it is not a headline concept, repeats an earlier definition, or falls outside a preferred runtime. If the user says source content must be preserved, keep all useful source items; add clarifications and practice as supplements rather than substitutes.
- For each item, record its source wording or ASR, normalized meaning, evidence/confidence, disposition, exact narration location, and reason for any exclusion or correction. Allowed dispositions are `retained`, `merged`, `faithfully paraphrased`, `corrected with note`, `excluded as non-content`, or `unresolved`. An exclusion requires a specific reason; unresolved useful content must remain visible for review and cannot be silently dropped.
- Map every content-bearing item to the draft. Also account for transcript spans that contain only empty disfluency or extraction noise so unmapped ranges are explicit. Use [the source coverage matrix template](references/source-coverage-matrix-template.csv). Spoken and visual evidence must remain distinguishable.
- If a user-approved or manually edited narration already exists, preserve it as the baseline. Map its content to the source before proposing changes; record every addition, removal, or material rewrite. Do not replace the user's structure or examples with a new hook or framework unless the user requested that change.

## 4. Draft for fidelity, then edit for spoken naturalness

- Draft from the source map in source order, not from a summary or topic list alone. The first pass preserves all useful source information and the speaker's position, qualification, attribution, and uncertainty. A request to humanize, explain, or add practice does not authorize shortening or omission.
- Remove only empty disfluencies, repeated syllables, abandoned fragments, or material that clearly adds no informational, emphasis, recall, example, navigation, or teaching function. If a repetition may carry function, keep it or flag it.
- Keep the source's useful examples, explanations, exam cues, stories, and recap functions. New examples, definitions, transitions, and exercises may be added to improve understanding, but mark them as editorial additions in the sidecar and do not let them replace mapped source content.
- Do not paraphrase sentence by sentence. Rebuild explanations and transitions while retaining exact canonical terms where changing them could change the teaching answer.
- Only after the source-preserving draft passes its item map, edit sentence shape, clarity, transitions, and oral cadence. This style pass may improve wording but may not remove mapped content. Re-run the source-to-draft map after the style pass.
- Check source-to-draft coverage for omissions and draft-to-source integrity for unsupported additions or altered attribution. Review factual accuracy separately from coverage. Do not optimize against AI-detector scores or word-count targets. If a duration is requested, disclose which mapped items would be affected and obtain a user decision before omitting them.
- Keep evidence, citations, confidence labels, production instructions, and editor comments outside the reader-facing script. Read the draft aloud or audition it; fix awkward speech without dropping content.
- Apply `../humanized-source-rewrite/SKILL.md` and its editing playbook for the separate maturity/style pass.

## 5. Required harness editorial loop

After the source-faithful narration draft is complete, the **current main harness** (the agent orchestrating this run, usually Codex) must personally perform the final editorial pass; do not delegate this pass or treat a worker's style edit as its substitute.

1. Assess the draft's strengths and weaknesses for spoken delivery: directness, speakable syntax, sentence and pause shape, transitions, classroom voice, terminology, functional repetition, and phrases that sound like written notes or editorial caveats.
2. Make a bounded revision that addresses concrete listener problems while preserving all mapped source content, meaning, attribution, uncertainty, examples, exam cues, and teaching repetitions. Do not optimize runtime or shorten content unless the user explicitly asks.
3. Compare before and after for added or omitted information, changed certainty, and attribution. Treat style cues as prompts, never as a blacklist; do not apply English-specific bans mechanically to Mandarin narration.
4. Record the assessment, finding IDs, material edits and reasons, and post-edit self-evaluation in private review evidence. If no wording change is warranted, record why. A `NEEDS_REVISION` assessment must identify findings; the next round must address them and change candidate bytes.
5. Refresh paragraph references and rerun source-to-draft coverage and integrity checks after each text change. Any edit invalidates prior coverage or fidelity approval. Continue until the main harness self-evaluation passes; stop only for a true missing source/decision or a repeated finding without evidence-producing progress, and report that blocker.
6. Keep the spoken script clean: assessment, critique, and edit notes belong in sidecar files, never in `candidate.txt` or `narration.txt`.

## 6. Acceptance and handoff

Have a distinct read-only reviewer check the exact candidate against the complete source map and source evidence, not just the topic ledger. Report separate verdicts for (a) extraction/review coverage, (b) source-item coverage, (c) factual and attribution integrity, (d) natural spoken delivery, (e) clean-copy readiness, and (f) unresolved uncertainty. Use `PASS`, `NEEDS_REVISION`, or `INSUFFICIENT_EVIDENCE` with concrete evidence. Source-item coverage can pass only when every content-bearing item has a narration location or a documented, justified disposition; missing, unreviewed, or unsupported items block PASS. Never claim full coverage if only samples or a topic checklist were checked.

If an independent verdict indicates a defect or `NEEDS_REVISION`, record finding IDs, return to the main harness for another bounded revision round, refresh the source map, and obtain a fresh independent review. A fully passing bundle may release with `python -m voice_director editorial-gate --bundle <private-run-directory> --out <new-release-directory>`. A final typed `INSUFFICIENT_EVIDENCE` uncertainty must first be shown to the user and explicitly dispositioned as described below. Use only the gate's released narration downstream. The gate checks evidence structure, hashes, role declarations, statuses, and exact-byte copying; it does not prove the semantic judgments or declared reviewer identities. Legacy `validate` and `compile` commands do not release narration.

When the final review marks a dimension `INSUFFICIENT_EVIDENCE`, do not guess, smooth over, or hide the gap. Add a typed uncertainty with the exact source and narration references, observed evidence, the unresolved question, its impact, and a recommendation. Run the gate to display the uncertainty packet and blank decision template, then pause for the user's explicit judgment. Save that response with its rationale and reference in `human-decisions.json`; do not treat silence as consent. `accept_as_is` is allowed only for those precisely listed residual uncertainties and yields a visibly distinct release status that preserves the reviewer’s original verdict. `request_revision` or `provide_evidence` sends the work back through revision or evidence collection and a fresh independent review. A known defect, `NEEDS_REVISION`, spoken-delivery issue, or clean-copy issue cannot be overridden as an uncertainty.

Deliver `narration.txt` as UTF-8 containing only approved spoken copy. Keep the knowledge ledger, correction log, coverage matrix, and review notes in separate files. If the optional Voice Director CLI path is used, freeze the exact bytes and set `director.json.source_sha256` to their SHA-256; any text or encoding/newline edit invalidates that director map and requires recalculating its hash.
