# Lesson editing rhythm

This contract governs visual timing across the whole lesson. The narration leads the edit: a picture, cue, crop, or transition must help the point being spoken, and its reading time must fit inside the spoken passage.

## Timing rules

- Keep the narration continuous. Do not add silence or leave an empty screen to give a visual more reading time. Bring the next cue or visual in before its line begins, then use a local highlight, crop, diagram step, or restrained transition while the voice continues.
- When a real interface screenshot carries the explanation, show the whole capture clearly for at least 2.5 seconds after its fade-in settles. Keep the screenshot large enough to establish which application and workspace the learner is seeing. If the spoken passage continues, retain that context while attention moves to a detail.
- For a source-linked crop, show the calibrated selection on the original for at least 0.8 seconds, move it smoothly to the reading position over roughly 0.8–1.2 seconds, and keep the settled crop clear for at least 4 seconds. Extend the hold when the narration or screen content needs longer. Blur the remaining source image while the crop overlaps it; restore the full image as the scene leaves.
- Keep a key instruction or teaching cue readable for at least 4 seconds, or for the complete spoken passage it explains when that is longer. Introduce it about 0.4–1 second before the relevant words when that avoids a pause. Do not flash text briefly between cuts.
- Let subtitles follow the actual voice. Keep technical examples on screen while they are explained, but summarize their purpose in speech instead of reading dense code, JSON, paths, or configuration aloud.
- Change the full screen only when the teaching point changes. Within one point, prefer a stable screenshot with a precise local emphasis or a small ordered reveal. Avoid competing movements, continuous drift, skewed callouts, and motion during a reading hold.
- Align every transition with the narration. A short overlap is acceptable after the outgoing evidence has received its full reading hold; do not cover a key item early or insert a dead pause before the next shot.

## Review and release

The storyboard records, per beat, the spoken passage, visual purpose, cue text, source asset, transition, full-context hold, crop preview/travel/read durations, cue visibility interval, and any reason for a longer static hold. Durations are measured as clearly visible time after fades, movement, and overlays have settled, not merely as nominal clip lengths.

For declared `contrast_reveal` sequences, the offline validator enforces a 2.5–4.5 second context hold, 0.8–1.2 second crop travel, and 4–8 second detail hold. The harness checks the broader beat timing, speech-to-screen alignment, source and crop geometry, annotation alignment, subtitle coverage, and transitions. It then reviews the rendered file at 1× playback, samples scene entry/settle/exit and motion frames, and checks suspected jitter or shimmer frame by frame. Structural checks do not establish that a visual is relevant or easy to understand; any uncertain screenshot identity, crop target, or reading fit must be shown in the conversation for the user to decide.

The approved sample is the timing reference for the full lesson. After the user approves its exact hash, apply the same rules to every scene and audit the complete render before delivery. Any material change to timing or visuals after approval requires a fresh sample review.
