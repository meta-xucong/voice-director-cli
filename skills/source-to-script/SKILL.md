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

- Split source material into atomic teachable items and assign stable IDs. Include not only topics but definitions, reasons, examples, anecdotes, lists, contrasts, conditions, exceptions, caveats, attribution, exam cues, meaningful repetition, and conclusions.
- Link each item to timestamp/page evidence and distinguish source wording from normalized meaning. Mark required, optional, redundant, unclear, or explicitly excluded items.
- Map every required item to planned narration. Ensure visual-only and spoken-only information are both represented. Do not treat a coarse topic list as complete coverage.

## 4. Draft for fidelity, then edit for spoken naturalness

- Draft from the knowledge ledger, ordinarily in source order. Preserve all useful information and the speaker's position, qualification, attribution, and uncertainty. A request to humanize or rewrite does not authorize shortening or omission.
- Remove only empty disfluencies, repeated syllables, abandoned fragments, or material that clearly adds no informational, emphasis, recall, example, navigation, or teaching function. If a repetition may carry function, keep it or flag it.
- Do not paraphrase sentence by sentence. Rebuild explanations and transitions while retaining exact canonical terms where changing them could change the teaching answer.
- Only after fidelity and coverage pass, edit sentence shape, clarity, transitions, and oral cadence. Use direct, speakable syntax, varied rhythm, consistent terminology, and natural thought boundaries. Avoid template filler, forced interjections, slang, fabricated experience, invented examples, and generic “teacherly” intimacy.
- Check source-to-draft coverage for omissions and draft-to-source integrity for unsupported additions or altered attribution. Review factual accuracy separately from coverage. Do not optimize against AI-detector scores or word-count targets.
- Keep evidence, citations, confidence labels, production instructions, and editor comments outside the reader-facing script. Read the draft aloud or audition it; fix awkward speech without dropping content.
- Apply `../humanized-source-rewrite/SKILL.md` and its editing playbook for the separate maturity/style pass.

## 5. Acceptance and handoff

Report separate verdicts for (a) extraction/review coverage, (b) source-item coverage, (c) factual and attribution integrity, (d) natural spoken delivery, (e) clean-copy readiness, and (f) unresolved uncertainty. Use `PASS`, `NEEDS REVISION`, or `INSUFFICIENT EVIDENCE` with concrete evidence. Never claim full coverage if only samples or a topic checklist were checked.

Deliver `narration.txt` as UTF-8 containing only approved spoken copy. Keep the knowledge ledger, correction log, coverage matrix, and review notes in separate files. Once approved, freeze the exact bytes. Stage B must calculate SHA-256 over those exact bytes and set `director.json.source_sha256` to that value; any text or encoding/newline edit invalidates the director map and requires a new validation pass.
