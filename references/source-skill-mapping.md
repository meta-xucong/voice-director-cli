# Source skill mapping

This crosswalk records how the source skills were adapted into the repository workflow. The source files are local user skills; their frozen SHA-256 values are recorded here so the adaptation can be audited. The values identify inputs, not licenses or permission to copy user data.

| Source material | Frozen SHA-256 | Adapted destination | Material behavior retained |
|---|---|---|---|
| `courseware-video-remake/SKILL.md` | `ec2cb0b3b04f193c2f164e6435805007d008de16a95b611e6e102d63885f8a3d` | `skills/source-to-script/SKILL.md` | Source inspection; separate ASR/OCR evidence; uncertainty-aware correction; source-indexed atomic knowledge ledger; source-to-script and script-to-source coverage; fidelity before style; clean narration; explicit acceptance evidence. |
| `humanized-source-rewrite/SKILL.md` | `cdff4db5fbf0cfc21020ecf861d72d3f05911ae2092721644b9fe842859c7f26` | `skills/humanized-source-rewrite/SKILL.md` | Edit-mode selection; immutable evidence; separate meaning and verbatim confidence; fact/attribution integrity; atomic coverage; voice boundary; functional repetition review; genre-fit oral edit; separate acceptance axes. |
| `humanized-source-rewrite/references/editing-playbook.md` | `a231b51fe04bb4548e5879ea6356b3cff7889b060bd0f5cf66448e7781ea7788` | `skills/humanized-source-rewrite/references/editing-playbook.md` | Reader-purpose questions; Chinese prose cues with non-mechanical guardrails; maturity and handoff checks; teaching-narration adaptation; voice calibration; no detector-score optimization. |

The adaptation intentionally omits visual redesign, final video rendering, cloud service selection, audio generation, and distribution workflows. Those are outside this repository integration's frozen scope. Stage A remains an LLM/skill workflow; Stage B remains the offline CLI. No course-specific transcript, media, outputs, local personal paths, or credentials are bundled.
