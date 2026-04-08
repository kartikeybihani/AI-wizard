# Blake Voice Builder (Pipeline)

This folder holds the runnable extraction/synthesis pipeline artifacts for building Blake's character bible from your corpus.

## Inputs (already in repo)

- `blake/podcasts/youtube/*.txt`
- `blake/podcasts/tim_ferriss/*.txt`
- `blake/self/substack/*.txt`
- `blake/self/personal_site/*.txt`
- `blake/instagram/captions.csv`
- `blake/articles/*.txt`
- Prompt stack: `blake/prompts/voice_builder/*.md`

## Configuration

Edit `blake/voice_builder/config.json`:

- Source weights:
  - podcasts/transcripts `0.45`
  - substack+personal_site `0.30`
  - instagram `0.20`
  - external articles `0.05`
- Era weights:
  - era A (TOMS builder) `0.10`
  - era B (transition/seeker) `0.30`
  - era C (Enough/current) `0.60`
- Models:
  - `extract`
  - `synthesis`
  - `critic`
- Cost controls:
  - `batch_sizes.instagram` (default `30`)
  - `chunk_chars.youtube` and `chunk_chars.longform`
  - `max_chunks_per_doc.youtube` (default `4`)
  - `max_chunks_per_doc.longform` (default `4`)
  - `max_chunks_per_doc.calibration` (default `2`)
  - `llm_max_tokens.*` per stage

## Run

Dry run (no LLM/API calls):

```bash
python3 blake/scripts/run_voice_builder.py --dry-run
```

Real run:

```bash
export OPENROUTER_API_KEY="your_key_here"
python3 blake/scripts/run_voice_builder.py
```

Optional model overrides per run:

```bash
python3 blake/scripts/run_voice_builder.py \
  --extract-model "openrouter/auto" \
  --synthesis-model "openrouter/auto"
```

Run only one stage at a time (same `--run-id` across all commands):

```bash
python3 blake/scripts/run_voice_builder.py --run-id my_blake_run --steps 01_instagram
python3 blake/scripts/run_voice_builder.py --run-id my_blake_run --steps 02_youtube
python3 blake/scripts/run_voice_builder.py --run-id my_blake_run --steps 03_podcast_depth
python3 blake/scripts/run_voice_builder.py --run-id my_blake_run --steps 04_written_values
python3 blake/scripts/run_voice_builder.py --run-id my_blake_run --steps 05_external_calibration
python3 blake/scripts/run_voice_builder.py --run-id my_blake_run --steps 06_antipatterns
python3 blake/scripts/run_voice_builder.py --run-id my_blake_run --steps 07_character_bible
```

Shortcut scripts (one file per stage):

```bash
python3 blake/scripts/run_voice_step_01_instagram.py --run-id my_blake_run
python3 blake/scripts/run_voice_step_02_youtube.py --run-id my_blake_run
python3 blake/scripts/run_voice_step_03_podcast_depth.py --run-id my_blake_run
python3 blake/scripts/run_voice_step_04_written_values.py --run-id my_blake_run
python3 blake/scripts/run_voice_step_05_external_calibration.py --run-id my_blake_run
python3 blake/scripts/run_voice_step_06_antipatterns.py --run-id my_blake_run
python3 blake/scripts/run_voice_step_07_character_bible.py --run-id my_blake_run
```

## Outputs

Each run is written to:

- `blake/voice_builder/runs/<run_id>/`

Key artifacts:

- `00_corpus/stats.json`
- `01_instagram_patterns/consolidated.json`
- `02_youtube_primitives/consolidated.json`
- `03_podcast_depth/consolidated.json`
- `04_written_values/consolidated.json`
- `05_external_calibration/consolidated.json`
- `06_antipatterns.json`
- `07_character_bible.json`
- `07_character_bible.md`
- `run_summary.json`

## Notes

- External articles are used as calibration/facts only.
- Character bible synthesis prioritizes current voice (2025-2026) using era weights.
- Prompt-level anti-pattern constraints are enforced before final bible assembly.
