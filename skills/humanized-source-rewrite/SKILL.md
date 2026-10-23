---
name: humanized-source-rewrite
description: Edit source-based writing into clear, natural, audience-fit prose while preserving all useful information before style changes. Not for detector evasion or unsupported invention.
metadata:
  short-description: Fidelity-first natural language editing
---

# Humanized Source Rewrite

Use this as the editorial method within `source-to-script`, or independently for transcript cleanup, source-based rewriting, and narration adaptation. Human-sounding means specific, useful, and context-aware; it does not mean adding slang, fake intimacy, anecdotes, or deliberate roughness.

## Choose the edit mode

- **Transcript cleanup:** preserve every useful claim, explanation, example, qualification, list, anecdote, cue, and conclusion; remove only clearly empty disfluency or functionless duplication.
- **Light edit:** keep structure and content; minimally repair stiff, unclear, or awkward lines.
- **Substantial rewrite:** rebuild expression while preserving all useful information and meaning; map source items before any authorized reordering.
- **Adaptation:** fit the requested genre without dropping source information unless selection/compression is explicitly authorized.
- **Voice edit:** keep content and structure unless broader rewriting is requested; infer only relevant voice traits from supplied samples.

## Fidelity-first method

1. Identify audience, purpose, medium, and degree of change. “Humanize” is a style request, not permission to shorten.
2. Preserve an immutable source record for long, technical, extracted, or high-stakes material. Map claims, reasons, examples, terms, numbers, contrasts, caveats, attribution, uncertainty, cues, and conclusions.
3. For uncertain ASR, preserve raw text; separate likely meaning from exact speech; log evidence and separate semantic/verbatim confidence. Never silently guess, omit, or claim acoustic verification that did not occur.
4. Complete the fidelity pass before style edits. Distinguish source claims, ASR repairs, paraphrases, editorial inferences, and factual corrections. Make material corrections traceable.
5. Check atomic source-to-draft coverage and draft-to-source integrity. A topic checklist is insufficient. If evidence is incomplete, say so.
6. Keep source evidence and editor notes out of the final reader-facing copy. Preserve attribution and uncertainty. Do not invent hooks, examples, experiences, or facts.
7. Review repetition by function across the whole piece. Keep recall, emphasis, navigation, contrast, rhythm, and teaching repetitions; consolidate only accidental duplicates and recheck coverage.
8. Fit the genre. For Mandarin narration, favor speakable syntax, direct wording, stable terms, varied sentence lengths, and pauses at thought boundaries. Avoid slang, fake intimacy, and fictional persona as a proxy for naturalness.
9. Once narration is accepted, freeze its text during TTS tuning. Keep emotion, emphasis, pace, and pauses in the separate prosody map unless wording changes are approved.
10. Assess coverage, claim integrity, audience/genre fit, repetition/function, delivery readiness, and unresolved evidence independently. Do not infer one pass from another.
11. Surface every unresolved item outside the spoken copy with its source location, candidate location, observed evidence, question, impact, and recommendation. Wait for the user's explicit decision. Record the user's actual response and rationale; never assume approval. If the user requests revision or more evidence, continue the bounded review loop. Only `accept_as_is` can disposition a listed residual uncertainty, and the release receipt must keep that uncertainty visible.

When this skill is used within `source-to-script`, the current main harness must assess spoken delivery and repeat bounded revisions until its self-evaluation passes. Each revision must address concrete findings while preserving all mapped information. Refresh the source map after text changes. A distinct read-only reviewer must review the exact candidate; any non-passing finding triggers another harness round and a fresh independent review. Keep assessments and edit summaries outside the spoken copy. Release only through the editorial gate described in `../source-to-script/SKILL.md`.

Consult [the editing playbook](references/editing-playbook.md) for Chinese prose cues and genre-specific review prompts. Treat cues as questions, not automatic bans. Do not use detector scores or word-count changes as evidence of naturalness or quality.
