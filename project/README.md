# Project Pipeline (`project/`)

Python backend for discovery, monitoring, and Blake-style comment generation.

## What This Folder Owns

- Part 1: discovery (`seed.py`, `enrich.py`, `score.py`, `rank.py`)
- Part 2: monitoring (`monitor_bootstrap.py`, `monitor_run.py`, `monitor_schedule.py`)
- Part 3.5: reel transcription + comment generation (`engage_generate.py`)
- Shared DB + queue logic (`utils/monitoring.py`)

## Setup

```bash
cd /Users/kartikeybihani/Finek/TOMS/project
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Recommended `.env` values:

```bash
APIFY_TOKEN=...
APIFY_HASHTAG_ACTOR_ID=...
APIFY_PROFILE_ACTOR_ID=...
APIFY_POST_ACTOR_ID=...
APIFY_COMMENT_ACTOR_ID=...
APIFY_MONITOR_ACTOR_TASK_ID=
APIFY_MONITOR_ACTOR_ID=

OPENROUTER_API_KEY=...
OPENROUTER_MODEL=mistralai/mixtral-8x7b-instruct
WHISPER_MODEL=base.en
```

Optional shell helper:

```bash
set -a
source /Users/kartikeybihani/Finek/TOMS/project/.env
set +a
```

## Part 1: Discovery Pipeline

Run full pipeline:

```bash
python3 seed.py --overwrite
python3 enrich.py
python3 score.py
python3 rank.py --max-accounts 100
```

Main outputs:

- `data/raw_handles.csv`
- `data/enriched.json`
- `data/scored.csv`
- `data/final_ranked.csv`
- `data/review_bucket.csv`

### Seed Source Behavior

`seed.py` combines 3 sources by default:

- manual seed handles
- aggregator seed handles
- Apify hashtag discovery

If you want only hashtag-driven discovery, set manual/aggregator to zero:

```bash
python3 seed.py --manual-count 0 --aggregator-count 0 --overwrite
```

## Part 2: Monitoring Pipeline

### Bootstrap tracked accounts from ranked output

```bash
python3 monitor_bootstrap.py --input data/final_ranked.csv --limit 20
```

### Run monitor (live)

```bash
python3 monitor_run.py \
  --mode live \
  --limit-accounts 10 \
  --posts-per-account 10 \
  --batch-size 10 \
  --delay-seconds 1 \
  --max-retries 1 \
  --auto-generate-comments \
  --generate-limit 10 \
  --whisper-model base.en
```

### Run monitor (mock)

```bash
python3 monitor_run.py --mode mock --fixture data/monitor/mock_posts.json
```

### Ensure schedule (4-hour cadence)

```bash
python3 monitor_schedule.py --ensure --cron "0 */4 * * *" --timezone "America/Phoenix"
```

## Reels/Video Eligibility

Monitoring stores all unseen posts for dedupe, but queues only video/reel-eligible posts for generation.

Eligibility uses multiple signals (URL + payload fields), including cases where Instagram reel/video URLs appear under `/p/`.

Run metrics include:

- `posts_seen_total`
- `posts_queued_video`
- `posts_skipped_non_video`

## Part 3.5: Comment Generation

Manual generation:

```bash
python3 engage_generate.py --db-path data/monitor/monitor.db --limit 10
```

Generate by post id:

```bash
python3 engage_generate.py --post-ids 123,456 --force
```

Drain pending queue in chunks:

```bash
python3 engage_generate.py --limit 10 --drain-pending --max-batches 20
```

Default character bible path used by generator:

- `../blake/voice_builder/runs/blake_v1/07_character_bible.json`

Override if needed:

```bash
python3 engage_generate.py --character-bible /abs/path/to/07_character_bible.json
```

## Queue Status Lifecycle

`new_posts_queue.status` values used in workflow:

- `pending_comment_generation`
- `transcribing`
- `ready_for_review`
- `generation_failed`
- `skipped_non_video`
- `approved`
- `rejected`
- `submitted`

## Data Model and Artifacts

SQLite DB:

- `data/monitor/monitor.db`

Core tables:

- `tracked_accounts`
- `seen_posts`
- `new_posts_queue`
- `post_processing`
- `comment_suggestions`
- `monitor_runs`

Per monitor run artifacts:

- `data/monitor/new_posts_<run_id>.csv`
- `data/monitor/run_report_<run_id>.json`

## Tests

```bash
cd /Users/kartikeybihani/Finek/TOMS/project
.venv/bin/python -m unittest discover -s tests -p "test_*.py"
```

Coverage includes normalization, dedupe, retry behavior, and reels/video eligibility.

