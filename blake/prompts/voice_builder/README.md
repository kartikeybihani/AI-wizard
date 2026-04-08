# Blake Voice Builder Prompt Pack

This folder contains the production prompt stack for extracting and synthesizing Blake Mycoskie's personality voice from the corpus.

## Goal
Build a layered character document, not a flat summary:

1. Instagram pattern mining
2. YouTube voice primitive extraction
3. Podcast depth arc extraction
4. Anti-pattern generation
5. Character bible assembly
6. Comment generation
7. Critic pass

## Source Weighting
Use these weights when synthesizing the final voice:

- Podcasts / transcripts: 45%
- Substack + personal site: 30%
- Instagram captions: 20%
- External articles: 5% for facts only

## Era Weighting
For current comment generation, weight Blake's eras like this:

- Era C: Enough / 2025-2026 = 60%
- Era B: transition / seeker = 30%
- Era A: TOMS builder = 10%

## Recommended Flow

1. Run `01_instagram_pattern_mining.md` on caption batches of 50-100.
2. Run `02_youtube_voice_primitives.md` once per transcript.
3. Run `03_podcast_depth_arcs.md` once per podcast transcript.
4. Run `04_antipattern_generation.md` on the strongest positive examples from steps 1-3.
5. Run `05_character_bible_assembly.md` to merge everything into one living character document.
6. Run `06_comment_generation.md` for each target post using the character bible plus retrieved voice snippets.
7. Run `07_comment_critic.md` to score, revise, or reject generated comments before human review.

## Output Contract

Every prompt in this folder should return strict JSON only.

Rules for all prompts:

- Return valid JSON and nothing else.
- Include confidence fields where useful.
- Include source references or evidence lists when useful.
- Avoid unsupported claims.
- Favor concrete examples over abstract language.

## Anti-Generic Constraints

Across the whole stack, avoid:

- therapy-speak cliches
- preachy language
- corporate jargon
- generic wellness platitudes
- overlong comments
- hashtags in Blake's personal voice

## File Map

- `01_instagram_pattern_mining.md`: extract short-form caption structures and recurring emotional units.
- `02_youtube_voice_primitives.md`: extract conversational rhythm, interruptions, bridges, and thought patterns.
- `03_podcast_depth_arcs.md`: extract identity shifts, inner life, and repeated story arcs.
- `04_antipattern_generation.md`: produce wrong-but-near examples and forbidden moves.
- `05_character_bible_assembly.md`: merge all outputs into one structured character bible.
- `06_comment_generation.md`: generate retrieval-grounded comments in Blake's current voice.
- `07_comment_critic.md`: evaluate comments for authenticity, specificity, and safety.

