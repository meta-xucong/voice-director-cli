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

## 5. Required final harness editorial pass

After the source-faithful narration draft is complete, the **current main harness** (the agent orchestrating this run, usually Codex) must personally perform the final editorial pass; do not delegate this pass or treat a worker's style edit as its substitute.

1. Briefly assess the draft's strengths and weaknesses for spoken delivery: directness, speakable syntax, sentence and pause shape, transitions, classroom voice, terminology, functional repetition, and phrases that sound like written notes or editorial caveats.
2. Make one bounded polish pass to improve those issues while preserving all mapped source content, meaning, attribution, uncertainty, examples, exam cues, and teaching repetitions. Do not optimize runtime or shorten content unless the user explicitly asks.
3. Make each edit answer a concrete listener problem; treat style cues as prompts, never as a blacklist. After editing, compare the before/after for added or omitted information, stronger or weaker certainty, and changed attribution. Do not apply English-specific bans mechanically to Mandarin narration.
4. Record the concise assessment and material edits in the private editorial notes. If no wording change is warranted, record the reason; the required pass still occurs.
5. Update paragraph references in the source map and rerun source-to-draft coverage and draft-to-source integrity checks against the polished text. Any text change invalidates prior coverage or fidelity approval. If the polish causes a fidelity issue, correct that issue and obtain a fresh read-only semantic review; do not silently carry forward an earlier PASS.
6. Keep the spoken script clean: assessment, critique, and edit notes belong in sidecar files, never in `narration.txt`.

## 6. Acceptance and handoff

After the harness pass, have a read-only reviewer check the **polished frozen draft** against the complete source map and source evidence, not just the topic ledger. Report separate verdicts for (a) extraction/review coverage, (b) source-item coverage, (c) factual and attribution integrity, (d) natural spoken delivery, (e) clean-copy readiness, and (f) unresolved uncertainty. Use `PASS`, `NEEDS REVISION`, or `INSUFFICIENT EVIDENCE` with concrete evidence. Source-item coverage can pass only when every content-bearing item has a narration location or a documented, justified disposition; missing, unreviewed, or unsupported items block PASS. Never claim full coverage if only samples or a topic checklist were checked.

Deliver `narration.txt` as UTF-8 containing only approved spoken copy. Keep the knowledge ledger, correction log, coverage matrix, and review notes in separate files. If the optional Voice Director CLI path is used, freeze the exact bytes and set `director.json.source_sha256` to their SHA-256; any text or encoding/newline edit invalidates that director map and requires recalculating its hash.
