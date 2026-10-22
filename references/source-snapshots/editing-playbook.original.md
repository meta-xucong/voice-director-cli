# Editing playbook: reader, genre, and Chinese prose cues

Use these as prompts to inspect the draft, not rules that every text must obey. A pattern is a problem only when it obscures meaning, sounds wrong for this reader, or repeats without doing useful work.

## First ask what this reader needs

- What is the reader trying to understand, decide, feel, or do?
- What does the source actually support?
- Which detail would make the explanation clearer, and is that detail in the source?
- What should the reader know or do after this passage?

Prefer the actual answer over a throat-clearing introduction. A short direct statement may be warmer and more credible than a warm-up question. Use a question only when it reflects a real reader question or advances the reasoning.

## Chinese prose cues to review

| Possible cue | Editorial question | Avoid automatic treatment |
|---|---|---|
| Abstract business/official verbs such as “赋能、打造、闭环、抓手、聚焦” | Who does what, to which process or person, with what evidenced result? Can the actor and action be named? | Do not replace a term if it is the correct technical or organizational term. |
| Broad praise or significance (“全面提升、意义重大、开启新篇章”) | Is there a concrete result, evidence, or decision the reader needs? If not, remove the claim rather than decorating it. | Do not remove a justified evaluation or attributed conclusion. |
| Meaning hidden in nominalizations and passive/agentless phrasing | Can the responsible actor and action be restored from the source? | Do not assign responsibility where the source does not. |
| Repeated roadmap and signposts (“接下来从三个方面…”, “首先/其次/最后”, “值得注意的是”) | Does this signpost help navigation, or restate the heading/previous sentence? | Lists and signposts are useful when they make a complex structure easier to follow. |
| Forced threes, mirrored contrasts, repeated “不是……而是……” | Is the parallel structure logically necessary, or has the prose been made too symmetrical? | Preserve real contrasts, canonical definitions, and intentional rhetoric. |
| Generic opening, filler transitions, recap that repeats the body | Does this line add a reader-relevant question, relation, evidence, or useful reminder? | Do not remove transitions that genuinely clarify a change in topic or logic. |
| Same-length sentences and evenly sized paragraphs throughout | Would a shorter conclusion, a longer explanation, or a pause better fit this idea? | Do not add random fragments or unevenness as a “human” effect. |
| Translation-like phrasing or over-explicit connectors | Would a native reader say this more directly? Is the connector already obvious from context? | Keep connectors that prevent ambiguity, especially in technical reasoning. |
| Fake intimacy or fabricated human texture | Is this warmth grounded in the writer’s real stance or source facts? | Do not add “我亲测”, classroom memories, personal feelings, or informal slang without authorization. |

## Maturity and handoff checks

Use these checks after content coverage is mapped. They assess whether the copy is ready for its intended reader; they do not authorize shortening or changing the source.

- **Voice boundary:** Identify whose words belong in the delivered copy: the source speaker, editor, narrator/author, or quoted third party. References to “the original video/article/source” can be useful in source analysis, but can break the voice of a standalone lesson or article. Keep them only when the requested genre is explicitly about the source. Move evidence, confidence labels, citations, and production notes to a separate ledger.
- **Repetition function:** Compare both neighboring paragraphs and repeated points across the whole piece. Ask whether each repeat adds recall, emphasis, navigation, contrast, rhythm, or a new example. Preserve those functions; consolidate accidental duplicates and repeated conclusions only after mapping their information back to the source.
- **Claim integrity:** Tag material statements during review as source claim, transcription repair, paraphrase, editorial inference, or factual correction. When a factual correction is needed, make the evidence and confidence visible in the edit trail and keep the reader-facing wording no stronger than that evidence. Prioritize uncertain, high-impact, technical, disputed, or absolute claims; routine statements do not all need external research.
- **Standalone-read check:** Hide the source, slide, editor notes, and prior conversation. Can the intended reader follow who is speaking, what each reference means, why each transition occurs, and what to do or remember? If not, add only the context that is already supported or clearly requested.
- **Delivery check:** Use checks suited to the medium. Narration should be speakable and term-consistent without stage directions or unresolved editor notes in voiced text. A customer message should state the relevant action and conditions plainly. A report should distinguish findings from recommendations. Do not apply a narration checklist to an unrelated genre.
- **Separate verdicts:** Record coverage, claim/attribution integrity, audience and genre fit, repetition/function, clean-copy readiness, and unresolved evidence as distinct findings. Passing coverage does not establish factual accuracy or publication readiness.

## Genre adapters

Start with the user’s requested genre. These are defaults to adjust, not rigid templates.

| Genre | Reader need | Naturalness check | Common overcorrection |
|---|---|---|---|
| Teaching / explanatory narration | Understand a concept, distinction, or procedure | Explain the confusing step; use a sourced or clearly illustrative example; speak terms accurately | Too many rhetorical questions, repeated “记住/我们来看”, fake classroom intimacy |
| Article / essay | Follow an idea or account and see why it matters | Build a clear line of thought; support emphasis with evidence or a real point of view | Generic hook, artificial story, grand conclusion, forced “three insights” |
| Report / proposal | Understand evidence and choose a next step | State finding, basis, implication, owner/action when known | Corporate abstractions, empty evaluation, confident recommendations without evidence |
| Email / message | Understand why the recipient is contacted and what response/action is needed | Put purpose and requested action where the recipient can find them | Excessive pleasantries, unnecessary context, false urgency |
| FAQ / help content | Resolve one concrete question | Lead with the answer, then give conditions and steps | Repeating the question as a heading and first sentence; overexplaining every edge case |
| Social / promotional copy | Notice a relevant angle and decide whether to engage | Use a specific, truthful point and the intended platform register | Engagement bait, invented experience, slang/emojis added as a proxy for personality |

## Voice calibration

When the user supplies their own sample, infer only traits relevant to the requested output: formality, directness, sentence length range, amount of explanation, preferred terminology, and warmth. Keep the sample’s facts and distinctive phrasing out of the rewrite unless they are also part of the source. When there is no sample, match the genre and audience rather than inventing a character.

Do not optimize against AI detectors. A lower pattern count is not proof of better writing. If a detector-like checklist is used, report concrete examples and edits rather than a score.

## Source basis and limits

These sources informed the review method; community Skills are examples, not standards or independently validated authorities:

- [blader/humanizer](https://github.com/blader/humanizer): cue-based editorial review, optional voice sample, and explicit separation from detector evasion.
- [humanizer-zh-cn](https://github.com/holygeek00/humanizer-zh-cn): Chinese-specific cues and recovery of actor/action/object/result/evidence while protecting facts and voice.
- [qu-ai-wei](https://github.com/baibanbao/qu-ai-wei): information conservation, minimal edits, and genre-sensitive handling.
- [humanize-writing](https://github.com/shir-danishyar/humanize): separating generation and edit modes and accounting for register.
- [Google voice and tone](https://developers.google.cn/style/tone) and [Microsoft brand voice](https://learn.microsoft.com/en-us/style-guide/brand-voice-above-all-simple-human): useful, respectful conversational writing adapted to purpose; read-aloud checks.
- [Study of LLM grammatical correction in learner Chinese](https://pmc.ncbi.nlm.nih.gov/articles/PMC11524451/): limited to learner Chinese correction; its observations about verbosity/connectors are cautions to test, not universal rules for Chinese prose.
