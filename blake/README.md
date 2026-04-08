# Blake Corpus + Voice Builder (`blake/`)

This folder contains the complete Blake Mycoskie research corpus and the 7-step extraction pipeline used to build a generation-ready character bible.

This is personality/style modeling, not biometric audio voice cloning.

## Folder Map

- `podcasts/` - Tim Ferriss + YouTube interview transcripts
- `self/` - personal site, Substack, Wikipedia text
- `instagram/` - caption dataset (`captions.csv`)
- `articles/` - external calibration articles
- `book/` - book-related notes/material
- `manifest/` - source manifests from ingestion
- `scripts/` - ingestion + builder scripts
- `prompts/voice_builder/` - prompt templates for steps 1-7
- `voice_builder/` - config + run outputs

## Ingestion Scripts

Run from repo root (`/Users/kartikeybihani/Finek/TOMS`):

### Base source ingest (Tim + YouTube + Substack)

```bash
python3 blake/scripts/ingest_phase3_sources.py
```

### Personal site crawl

```bash
python3 blake/scripts/ingest_personal_site.py
```

### Wikipedia ingest

```bash
python3 blake/scripts/ingest_wikipedia.py --title Blake_Mycoskie
```

### External article ingest

```bash
python3 blake/scripts/ingest_articles.py
```

## Voice Builder (7-Step Pipeline)

Main runner:

```bash
python3 blake/scripts/run_voice_builder.py --run-id blake_v1
```

Step wrappers:

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

## Environment Variables

Required:

```bash
OPENROUTER_API_KEY=...
```

Optional model overrides:

```bash
OPENROUTER_MODEL_EXTRACT=openrouter/auto
OPENROUTER_MODEL_SYNTHESIS=openrouter/auto
OPENROUTER_MODEL_CRITIC=openrouter/auto
```

## Key Outputs

Run directory:

- `blake/voice_builder/runs/<run_id>/`

Important artifacts:

- `01_instagram_patterns/consolidated.json`
- `02_youtube_primitives/consolidated.json`
- `03_podcast_depth/consolidated.json`
- `04_written_values/consolidated.json`
- `05_external_calibration/consolidated.json`
- `06_antipatterns.json`
- `07_character_bible.json`
- `07_character_bible.md`
- `run_summary.json`

Primary artifact used by generation system:

- `blake/voice_builder/runs/blake_v1/07_character_bible.json`

## Notes

- The pipeline intentionally weights current-era voice more heavily (post-Enough era).
- External articles are calibration context, not primary style ground truth.
- If generation quality degrades on one step, run per-step wrappers and inspect each consolidated output before moving forward.

