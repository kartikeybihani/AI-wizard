# Blake Corpus + Character Bible Builder (`blake/`)

This folder contains the full research corpus and extraction pipeline used to model Blake Mycoskie's written/personality voice for comment generation.

This is personality modeling, not biometric audio voice cloning.

## What This Folder Owns

- Source corpus (podcasts, YouTube transcripts, Substack, personal site, Instagram captions, external calibration, book notes)
- Ingestion scripts for pulling and normalizing those sources
- Prompt library for a staged extraction workflow
- Voice-builder pipeline that produces the final character bible artifact

## Source Buckets

- `podcasts/` - Tim Ferriss and long-form interview transcripts
- `self/` - personal website pages, Substack, Wikipedia
- `instagram/` - high-volume caption corpus
- `articles/` - third-party external calibration sources
- `book/` - book notes/material
- `manifest/` - source inventory and ingestion outputs

Pipeline internals:

- `scripts/` - ingestion and voice-builder runners
- `prompts/voice_builder/` - prompt templates for steps 1-7
- `voice_builder/` - run configs, per-step outputs, final artifacts

## Modeling Approach

Core idea: Blake's voice evolved over time, so extraction must model era shift, not just average style.

Current weighting used in `blake_v1`:

- source weights: podcasts/transcripts `45%`, Substack/personal site `30%`, Instagram captions `20%`, external factual sources `5%`
- era weights: early TOMS builder `10%`, transition/seeker era `30%`, current Enough-era voice `60%`

Why this matters:

- comments should sound like current Blake in mental-health context
- external sources should anchor facts, not dominate style

## Ingestion Commands

Run from repo root (`/Users/kartikeybihani/Finek/TOMS`):

```bash
python3 blake/scripts/ingest_phase3_sources.py
python3 blake/scripts/ingest_personal_site.py
python3 blake/scripts/ingest_wikipedia.py --title Blake_Mycoskie
python3 blake/scripts/ingest_articles.py
```

## Voice Builder (7-Step Extraction)

Main runner:

```bash
python3 blake/scripts/run_voice_builder.py --run-id blake_v1
```

Step wrappers (recommended for debugging and incremental reruns):

```bash
python3 blake/scripts/run_voice_step_01_instagram.py --run-id blake_v1
python3 blake/scripts/run_voice_step_02_youtube.py --run-id blake_v1
python3 blake/scripts/run_voice_step_03_podcast_depth.py --run-id blake_v1
python3 blake/scripts/run_voice_step_04_written_values.py --run-id blake_v1
python3 blake/scripts/run_voice_step_05_external_calibration.py --run-id blake_v1
python3 blake/scripts/run_voice_step_06_antipatterns.py --run-id blake_v1
python3 blake/scripts/run_voice_step_07_character_bible.py --run-id blake_v1
```

Dry run (no API calls):

```bash
python3 blake/scripts/run_voice_builder.py --dry-run
```

## What Each Step Produces

- Step 1 (`01_instagram_patterns`): short-form caption pattern mining
- Step 2 (`02_youtube_primitives`): spoken cadence and voice primitives
- Step 3 (`03_podcast_depth`): depth arcs and emotional narrative structures
- Step 4 (`04_written_values`): values hierarchy from edited written voice
- Step 5 (`05_external_calibration`): factual calibration and third-person consistency
- Step 6 (`06_antipatterns`): negative-space constraints (what Blake should not sound like)
- Step 7 (`07_character_bible`): consolidated generation-ready identity + voice rules

## Environment Variables

Required:

```bash
OPENROUTER_API_KEY=...
```

Optional model routing:

```bash
OPENROUTER_MODEL_EXTRACT=openrouter/auto
OPENROUTER_MODEL_SYNTHESIS=openrouter/auto
OPENROUTER_MODEL_CRITIC=openrouter/auto
```

## Key Artifacts

Run output directory:

- `blake/voice_builder/runs/<run_id>/`

Important files:

- `01_instagram_patterns/consolidated.json`
- `02_youtube_primitives/consolidated.json`
- `03_podcast_depth/consolidated.json`
- `04_written_values/consolidated.json`
- `05_external_calibration/consolidated.json`
- `06_antipatterns.json`
- `07_character_bible.json`
- `07_character_bible.md`
- `run_summary.json`

Primary artifact consumed by generation system:

- `blake/voice_builder/runs/blake_v1/07_character_bible.json`

## How This Connects to Engage Generation

`project/engage_generate.py` uses this artifact to:

- ground generation with identity core and voice rules
- pull bucket-matched examples for context fit
- enforce anti-pattern constraints during generation and critique

Prompts used at generation time:

- `blake/prompts/voice_builder/06_comment_generation.md`
- `blake/prompts/voice_builder/07_comment_critic.md`

## Practical Notes

- If one step degrades, rerun that step wrapper and inspect its `consolidated.json` before continuing.
- If model outputs truncate, reduce chunk size and/or use a stronger JSON-following model.
- Keep the final bible under practical size so generation calls remain stable and cheap.
