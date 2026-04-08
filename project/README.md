# Influencer Discovery + Monitoring

This project now includes:

1. Discovery/scoring/ranking (Part 1)
2. Ongoing new-post monitoring queue (Part 2)

## Setup

```bash
cd /Users/kartikeybihani/Finek/TOMS/project
python3 -m pip install -r requirements.txt
cp .env.example .env
```

Load env vars from `.env` (or export directly):

```bash
export APIFY_TOKEN=...
export APIFY_HASHTAG_ACTOR_ID=...
export APIFY_PROFILE_ACTOR_ID=...
export APIFY_POST_ACTOR_ID=...
export APIFY_COMMENT_ACTOR_ID=...

export OPENROUTER_API_KEY=...
export OPENROUTER_MODEL=mistralai/mixtral-8x7b-instruct
```

Optional schedule env (for `monitor_schedule.py`):

```bash
export APIFY_MONITOR_ACTOR_TASK_ID=...
# or:
export APIFY_MONITOR_ACTOR_ID=...
```

## Part 1 Run (Discovery Pipeline)

```bash
python3 seed.py --overwrite
python3 enrich.py
python3 score.py
python3 rank.py --max-accounts 100
```

Outputs:

- `data/raw_handles.csv`
- `data/enriched.json`
- `data/scored.csv`
- `data/final_ranked.csv`
- `data/review_bucket.csv`

## Part 2 Run (Post Monitoring)

### 1) Bootstrap tracked accounts from ranked output

```bash
python3 monitor_bootstrap.py --input data/final_ranked.csv --limit 20
```

This upserts into monitor DB while preserving manual inactive flags.

### 2) Run monitor job (live)

```bash
python3 monitor_run.py --mode live --posts-per-account 5 --batch-size 25
```

### 3) Run monitor job (mock fallback)

```bash
python3 monitor_run.py --mode mock --fixture data/monitor/mock_posts.json
```

### 4) Ensure 4-hour Apify schedule

```bash
python3 monitor_schedule.py --ensure --cron "0 */4 * * *" --timezone "America/Phoenix"
```

## Part 2 Data Model

SQLite DB: `data/monitor/monitor.db`

Tables:

- `tracked_accounts`
- `seen_posts`
- `new_posts_queue`
- `monitor_runs`

Queue contract for Part 3:

- Source: `new_posts_queue` table and `data/monitor/new_posts_<run_id>.csv`
- Required fields: `username`, `post_id`, `caption`, `url`, `posted_at`, `detected_at`, `status`
- Current status lifecycle: `pending_comment_generation`

## Part 2 Artifacts

For each monitor run:

- `data/monitor/new_posts_<run_id>.csv`
- `data/monitor/run_report_<run_id>.json`

## Testing

```bash
python3 -m unittest discover -s tests -p "test_*.py"
```

Coverage includes:

- post normalization on heterogeneous payloads
- idempotent dedupe by `post_id`
- retry/backoff continuation after batch failures
- bootstrap upsert preserving manual inactive accounts
- mock rerun proving no duplicate queue inserts

## Notes

- Monitoring is scheduled polling (4-hour cadence), not pseudo realtime.
- New post detection uses strict `post_id` uniqueness (never caption-based dedupe).
- Batch retries use exponential backoff with jitter and continue after partial failures.
- If API keys are missing, scripts still support mock mode for deterministic demos.
