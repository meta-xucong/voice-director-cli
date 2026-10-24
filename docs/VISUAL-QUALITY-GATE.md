# Courseware visual quality gate

## Frozen task contract

**User goal:** “全部固化，打包，传GitHub。让现在调整后的整体工作流形成一个整体”

**Baseline:** branch `editorial-gate-20261023`, clean at `b20d904` (`Add harness-reviewed visual asset gate`). The branch already contains narration/source-fidelity gates, voice/screen mapping, Internet asset review, three visual directions, user-approved design sample, and motion/pacing guidance.

**Scope:** connect those existing stages and add a final visual-quality evidence gate used for both the design sample and the full video. Bind the exact narration, voice/screen map, reviewed asset manifest, visual direction, private HyperFrames project inventory, rendered video and review frames. Add deterministic checks for media metadata, actual PNG dimensions, upscale/crop geometry, annotation alignment, review completeness and human-decision states. Update the workflow skill, user documentation, CLI and tests as one release.

**Hard constraints:**

- Preserve HyperFrames/GSAP as the renderer; do not implement another renderer or automatic Internet search/download client.
- Keep course materials, screenshots, rendered video, contact sheets, probes, and manifests in the private run directory; commit only schemas, code, documentation, and synthetic tests.
- Do not represent structural validation as proof of semantic correctness or visual quality. The harness must inspect the actual evidence and the user must approve the exact sample hash.
- Keep search/review before visual direction and creation; sample quality review and user approval before full render; final quality review before delivery.
- Any unresolved quality finding returns `AWAITING_HUMAN` or blocks release. No implicit approval.

**Decisions from D1 design review:** D1 resolved with explicit defaults: 1920×1080 minimum, 16:9, progressive, constant 30 fps or higher, video timestamp zero; no screenshot upscaling at maximum planned zoom; title/body/subtitle/technical-display minimums of 48/32/36/24 px at 1080p; annotation anchor/edge error ≤4 px and rotation error ≤0.1° at 1080p; static-hold drift ≤0.5 px and rotation drift ≤0.05°; meaningful teaching beats 3–10 seconds, >12 seconds documented, default transitions 0.25–0.60 seconds. Pixel and font thresholds scale with output height. These are conservative project defaults, not automatic proof of polish.

**D/I/A:** D1 (resolved numeric quality thresholds); I2 (cross-stage manifests, hash bindings, and failure/human-review paths); A1 (render-release gate, privacy and integrity). **Writer:** main session only. **Audit:** separate read-only reviewer; requested model route provenance is currently `ROUTE_UNVERIFIED` unless runtime metadata establishes otherwise.

**Allowed files:** `docs/VISUAL-QUALITY-GATE.md`, `docs/EDITING-RHYTHM.md`, `docs/VISUAL-ASSET-REVIEW.md`, `docs/PIPELINE.md`, `README.md`, `skills/courseware-pipeline/SKILL.md`, `voice_director/cli.py`, `voice_director/visual_gate.py`, new `voice_director/visual_quality.py`, and related/new tests. No renderer internals or user media.

**Acceptance evidence:** frozen manifest contracts; negative tests for stale hashes, invalid probe metadata, low-resolution and upscaled screenshots, crooked/misaligned annotations, missing frame evidence, jitter, quality failures, and missing human approvals; full offline suite; whitespace check; independent audit result with route provenance caveat; fast-forward push to the authorized GitHub branch.

## Workflow contract

The workflow is a single ordered chain:

1. Lock source-faithful narration and the beat-level voice/screen map.
2. Search the Internet before asking for images. The harness opens and inspects source pages, checks every candidate against every beat, and shows exact evidence and a specific image request or human question when needed.
3. Only after asset review passes, show three distinct visual directions and wait for the user's choice.
4. Build a representative 20–60 second HyperFrames sample from reviewed authentic assets. Bind it to a complete private render-project inventory and the chosen direction image ID/hash, then produce a quality evidence packet.
5. The quality validator checks the packet and requires the sample to demonstrate applicable lesson-wide elements (real UI, technical display, annotations, captions, and planned motion); the harness watches the exact sample at 1× and inspects the supplied frame evidence. The user approves that exact sample hash. Any change to the sample, project inventory, narration, map, or selected assets invalidates the approval.
6. Render the complete lesson. Produce the same quality evidence packet for the full video, linked to the approved sample and current upstream hashes. Run the final delivery gate. Deliver only after it returns `PASS` and all human checks pass.

## Render and frame evidence

Each quality packet references the exact video, a complete private project inventory, the selected direction image ID/hash, and hash-bound visual evidence. The validator invokes FFprobe on that exact video (it does not trust a supplied probe JSON file) and checks width/height, aspect ratio, average and nominal frame rate, field order, start time, and duration. Output must be at least 1920×1080, 16:9, progressive, constant frame rate, timestamp zero, and at least 30 fps. FFmpeg/FFprobe must be installed and discoverable on `PATH`, or passed with `--ffprobe <path>` and `--ffmpeg <path>`. The project inventory must enumerate every regular file below the isolated render-project root; symlinks are rejected. Keep rendered output and evidence outside that root so the frozen input inventory remains unchanged. The validator uses a temporary FFmpeg filter script to avoid operating-system command-line limits, streams selected RGB frames one at a time, decodes corresponding PNG evidence, and compares immediately. Raw RGB memory stays bounded to one frame at a time; only frame references and the temporary selection script grow with evidence count. Extraction has a one-hour deadline and drains stderr concurrently with bounded diagnostic storage. Frame times must map to distinct output frames; entry, settled, and exit are strictly ordered. The harness separately inspects actual frame pixels and playback.

Every beat supplies entry, settled, and exit full-resolution frames. Animated beats additionally supply motion samples and explicit `motion_extremum` frames for zoom/pan endpoints; transition/motion intervals have evidence at gaps no greater than 0.5 seconds. Annotated beats include matching geometry evidence at every motion and extremum frame. The harness watches the entire short design sample at 1× and frame-steps any suspected shimmer or jitter; sparse frames alone cannot certify temporal stability.

## Screenshot and annotation requirements

For genuine product UI, record the selected source crop and its displayed output rectangle. At the maximum planned zoom the crop must not be upscaled: source crop width/height must each be at least the corresponding displayed output dimensions. The screenshot may not be stretched by more than 1% across axes. Prefer full-frame screenshots; use a focused crop only when it helps teach a specific control and preserves context.

For every box, underline, or arrow, record the target geometry and observed annotation geometry in each required evidence frame, in output pixels. Rectangles use four ordered corners, underlines use two endpoints, and arrows record their tip. The CLI computes direct point error and line/edge rotation difference from those supplied output-pixel measurements. At 1080p, point/edge error must be ≤4 px and relative rotation ≤0.1°; scale point-error tolerances with output height. Arrow tips must land inside the intended target. The harness checks that the screenshot and annotation share the same transform. During a static reading hold, measured drift must stay ≤0.5 px and rotation drift ≤0.05°.

For a multi-image comparison, use the [contrast-reveal sequence contract](CONTRAST-REVEAL.md): let the learner orient in the full authentic capture, trace a crop from its exact source pixels into a readable detail view, repeat with matched timing for the second capture, and hold a balanced synthesis long enough to read. Bind each crop to the actual source dimensions and planned display rectangle; do not upscale. Keep the visual link to the original target clear during reframing. Motion must settle before the reading hold and the synthesis; test the rendered frames for drift and edge shimmer.

## Visual polish and readability review

The harness records pass/fail evidence per beat for consistency with the chosen design, visual hierarchy, spacing/alignment, typography, color consistency, clean edges/anti-aliasing, screenshot readability, crop safety, factual/UI authenticity, motion stability, and pacing. At 1080p, default minimum text sizes are title 48 px, body 32 px, captions 36 px and essential screenshot/code details 24 px. Scale them with output height. Every technical-display beat must report its measured technical text size. Numeric size does not replace inspection at normal playback size. A failed item, unreadable essential text, clipping, shimmer, jitter, misplaced annotation, or unmotivated motion blocks the quality gate and requires corrected evidence.

Use purposeful transitions and local focus effects. Prefer 3–10 second teaching beats; document any hold over 12 seconds. Default transition duration is 0.25–0.60 seconds; record reasons for exceptions. Keep screenshot/text layers stable during reading holds; never use continuous subpixel drift. The motion review checks the rendered video, not only the storyboard declaration.

Apply the whole-course timing rules in [EDITING-RHYTHM.md](EDITING-RHYTHM.md): clear full-screenshot context for at least 2.5 seconds, source selection for at least 0.8 seconds, crop travel over roughly 0.8–1.2 seconds, settled crop and key cue visibility for at least 4 seconds, and transitions aligned to continuous narration. Measure only clear time after motion settles. A readable visual must not create inserted silence or an empty wait.

## Deterministic boundary

The CLI verifies file/path containment, hashes, complete project file-set identity, FFprobe metadata shape and values, FFmpeg-decoded frame equality, image headers/dimensions, beat/evidence coverage, stage ordering and hash links, no-upscale/aspect-ratio arithmetic, annotation geometry/tolerances, transition/frame sampling coverage, required review criteria, selected direction identity, and exact sample approval. It does not infer whether a screenshot is truly Codex/Work, whether text is meaningful or readable to a learner, whether a design feels polished, or whether motion looks smooth. The harness and user must inspect the actual media and evidence. The harness also records a watched-at-1× decision and concrete pass/fail evidence per beat; any unresolved item returns `AWAITING_HUMAN`. A manifest claiming `PASS` without the required evidence is rejected; a valid manifest is still not a semantic or aesthetic certificate.

## Private run packet and commands

Keep all inputs below in one private run folder, outside this repository. A run normally contains `narration.txt`, `voice-screen-map.json`, `visual-asset-review.json`, three direction images, `visual-gate.json`, `project-inventory.json`, rendered sample/final MP4, PNG frame samples, and `sample-quality.json` / `final-quality.json`. The inventory lists each render-project file by relative path, SHA-256, and role; include the composition, imported assets, fonts, and other files that can affect output. Do not commit these user materials.

Run the ordered gates from the repository root:

```powershell
python -m voice_director review-visual-assets --manifest ..\courseware-private\visual-asset-review.json --narration ..\courseware-private\narration.txt --map ..\courseware-private\voice-screen-map.json
python -m voice_director visual-gate --manifest ..\courseware-private\visual-gate.json
# After user selects one of the three directions and a 20–60 second sample is rendered:
python -m voice_director review-visual-quality --manifest ..\courseware-private\sample-quality.json --project-root ..\courseware-private\hyperframes-project [--ffprobe C:\path\to\ffprobe.exe --ffmpeg C:\path\to\ffmpeg.exe]
python -m voice_director visual-gate --manifest ..\courseware-private\visual-gate.json --project-root ..\courseware-private\hyperframes-project [--ffprobe C:\path\to\ffprobe.exe --ffmpeg C:\path\to\ffmpeg.exe]
# Record explicit approval of the exact sample hash, then re-run visual-gate before full render.
# After full render and a final-quality.json review packet:
python -m voice_director review-visual-quality --manifest ..\courseware-private\final-quality.json --project-root ..\courseware-private\hyperframes-project [--ffprobe C:\path\to\ffprobe.exe --ffmpeg C:\path\to\ffmpeg.exe]
```

For nonstandard binary locations, pass both `--ffprobe` and `--ffmpeg` to quality commands and any visual-gate command that validates a sample. A gate result of `AWAITING_HUMAN` must be shown in the conversation with its concrete evidence; ask the user to choose or decide the named item. Never turn a missing/uncertain image, unresolved quality issue, pending sample, or absent approval into an inferred pass. Re-rendering or changing upstream inputs invalidates the affected hashes and requires a new review packet.
