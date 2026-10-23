# Public skill review: source-based Mandarin narration

**Reviewed:** 2026-10-23

This is a fit review, not a popularity ranking. GitHub stars show attention, not quality, correctness, suitability, or endorsement. Counts are approximate observations at review time and change over time. The marketplace search client was blocked by the local network permission, so the review used public primary repository pages instead.

| Skill | Recognition signal at review time | Useful ideas | Fit decision |
|---|---:|---|---|
| [Humanizer-zh](https://github.com/op7418/Humanizer-zh) | about 20.5k GitHub stars | Preserve meaning, certainty, attribution, author voice, and genre; make only edits supported by a real expression problem; treat patterns as prompts rather than bans; compare before and after for additions and omissions. | Closest fit. Adopted the bounded, evidence-sensitive edit and explicit before/after integrity check. |
| [blader/humanizer](https://github.com/blader/humanizer) | about 59.7k GitHub stars | General guidance for removing formulaic prose while retaining meaning; patterns are possible signals rather than proof. | Useful caution against mechanical editing; not a narration workflow and not Mandarin-specific. No files or wording copied. |
| [hardikpandya/stop-slop](https://github.com/hardikpandya/stop-slop) | about 18.1k GitHub stars | Encourages direct, specific prose and removal of empty filler. | Do not adopt its broad English-oriented bans (for example blanket restrictions on adverbs, passive constructions, rhetorical forms, or punctuation) for Mandarin classroom narration. These can remove legitimate teaching transitions or alter voice. |

## Changes absorbed

- Added a small rule to `skills/source-to-script/SKILL.md`: each final-pass edit must address a concrete listener problem; style cues are not a blacklist; compare for changed information, certainty, and attribution; do not mechanically import English-specific bans into Mandarin.
- Applied that rule in the bounded r12 → r13 opening pass. The edits preserve all six chapter names and order, teacher information's courseware attribution, course philosophy, and stated exam priorities. The remaining 43 paragraphs are byte-for-byte unchanged.

## Not imported

No full third-party skill was copied. The project already contains source mapping, a fidelity-first pass, spoken-style review, sidecar notes, and a main-harness final pass, so replacing it with a generic “humanizer” would add process without solving a gap. Detector evasion, arbitrary word-count reduction, and provider-specific TTS setup are outside this project's editing goal.

This file summarizes the public materials in original wording; it does not reproduce their skill text. Links identify the reviewed sources for attribution and future rechecking.