---
name: courseware-pipeline
description: Coordinate source-video-to-narration work and route full lesson-video remakes through the existing courseware-video-remake and HyperFrames workflows.
metadata:
  short-description: Source video to rendered lesson
---

# Courseware Pipeline

Use this skill as the routing entry for the complete workflow. It reuses the existing `courseware-video-remake` skill for source understanding, narration, visuals, voice, captions, and HyperFrames production; it does not itself call those tools. The planned routine choice is the TTS provider/voice. Keep the existing workflow's source-use permission, cloud-transfer/cost authorization, and narration/voice-audition acceptance points when they apply. Do not build another ASR, rewrite, TTS, compositor, or orchestration implementation.

The skill files in this repository are not automatically registered with Codex. Run `scripts/install.ps1` from the repository root or follow the [repository installation guide](https://github.com/meta-xucong/voice-director-cli/blob/main/INSTALL.md) to install the four related Skills together, preserving their sibling structure and the rewrite skill's `references/` folder. Keep source media, extracted text, narration, director maps, and generated reports in a private work directory outside the public repository; alignment reports can contain narration words.

## Source-faithful end-to-end chain

1. Before writing a new narration from source, run `../source-to-script/SKILL.md` as the required content-preservation stage. Build the complete source map and draft in source order. After the draft, the current main harness personally assesses its spoken-delivery strengths and weaknesses and makes one bounded polish pass; then an independent reviewer checks the polished frozen narration against the complete source map. Release only after every content-bearing source item is accounted for or has a justified disposition; the core-topic ledger alone is not enough. Keep the assessment and edit summary outside the narration.
2. Give the accepted, locked narration to `courseware-video-remake` for its existing courseware, visual, voice, caption, and render work. It may improve presentation, but it must keep mapped source content; any text edit requires rechecking the source map. If the user already has a manually edited final, use it as the baseline and do not replace its structure or examples without instruction.
3. Ask for the TTS provider/voice if it is not already specified. Create the voice audition required by that workflow and proceed to full generation after the user accepts the narration and audition, following existing external-transfer and cost approval rules.
4. Use the final voice audio for captions and scene timing, then pass audio, narration, captions, and visuals to the existing HyperFrames project for composition and rendering. Use Voice Director only if the selected backend benefits from its existing offline direction or chunking features.

If the user requests only clean narration, use `../source-to-script/SKILL.md` and stop there. If they supply approved narration, skip source-to-script work and continue at step 2. Keep intermediate files in the remake workflow's private work folder. This is skill-level routing, not a standalone one-click executable; actual execution depends on the installed skills, provider tools, and HyperFrames project.

## Required handoff

- The source-to-script step produces UTF-8 `narration.txt` containing only spoken copy. Keep source ledger, correction log, coverage matrix, and editorial notes in separate files.
- Only when Voice Director is useful, freeze narration bytes and prepare its existing `director.json` handoff. The CLI writes offline draft artifacts; it does not synthesize speech or contact providers.
- Give the selected TTS tool the approved narration and any prepared voice-direction text. After audio generation, pass the audio, narration, visuals, and audio-timed captions to HyperFrames; do not recreate its scene or render logic here.

## Boundaries

- Keep ASR/OCR evidence, confidence judgments, and correction notes outside the spoken script.
- Keep source evidence and editing notes separate from spoken narration. Do not create a second ASR, rewrite, or renderer. Complete source mapping and independent editorial fidelity review are required within `source-to-script`, not optional additions to the production workflow.
- Do not claim complete source coverage when extraction or review was partial.
- The CLI cannot establish transcript accuracy, factual correctness, natural TTS delivery, provider behavior, publication rights, or audio/video synchronization.
- This repository has no software license. Its public visibility does not grant reuse rights.

For end-to-end commands and file layout, see the [pipeline guide](https://github.com/meta-xucong/voice-director-cli/blob/main/docs/PIPELINE.md). The installed skill directory is not the CLI checkout. Locate your repository clone, confirm `git remote get-url origin` points to `https://github.com/meta-xucong/voice-director-cli` (an equivalent SSH URL is valid), and run the CLI commands from that clone's root. Use paths to your private work directory for inputs and outputs.
