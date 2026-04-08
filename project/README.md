# Project Backend Pipeline (`project/`)

Python backend for the full assessment workflow:

- Part 1: influencer discovery and ranking
- Part 2: post monitoring (small live subset or mock)
- Part 3.5: reel transcription + Blake-style comment generation

This folder is the execution layer used by the UI in `/Users/kartikeybihani/Finek/TOMS/ui`.

## What This Folder Owns

- Discovery: `seed.py`, `enrich.py`, `score.py`, `rank.py`
- Monitoring: `monitor_bootstrap.py`, `monitor_run.py`, `monitor_schedule.py`
- Engagement generation: `engage_generate.py`
- Shared infra: `utils/` (Apify client, monitor store, queue lifecycle, LLM client)

## Architecture Summary

1. Seed candidate handles from curated pools + hashtag discovery.
2. Enrich each handle with profile, recent posts, and comment evidence.
3. Score accounts across relevance, intent, depth, and engagement quality.
4. Rank into `final_ranked.csv` and send low-confidence candidates to `review_bucket.csv`.
5. Bootstrap monitor watchlist from ranked output.
6. Monitor recent posts and queue only reel/video-eligible posts for generation.
7. Transcribe reel audio locally with Whisper, generate 3 candidates, critique/select best, persist review cards.

## Discovery Logic (How Ranking Is Justified)

### Seed collection strategy

Seed merges and deduplicates:

- manual seed handles
- aggregator seed handles
- Apify hashtag discovery

Default hashtag inputs:

- `#mentalhealth`
- `#anxietyhelp`
- `#therapy`
- `#mentalhealthadvocate`
- `#mentalhealthawareness`
- `#enoughmovement`

`--overwrite` controls whether seed output is rebuilt fresh or merged with prior rows.

Optional showcase scraper (research artifact):

```bash
python3 scrape_feedspot_handles.py
```

Output:

- `data/feedspot_handles.csv`

### Scoring dimensions

Each account gets these core scores:

- `relevance_score`: how clearly the account is mental-health primary
- `audience_intent_score`: help-seeking/trust/emotional resonance in comments
- `content_depth_score`: specificity and insight vs generic advice
- `engagement_quality_score`: quality-adjusted engagement (not raw likes only)

Topical signal checks are applied:

- positive terms: anxiety, depression, therapy, trauma, healing, coping, nervous system
- negative off-topic terms: hustle, discount/shop-now, generic motivation spam

Final blend starts at:

- relevance `0.35`
- audience intent `0.30`
- engagement quality `0.20`
- content depth `0.15`

Dynamic reweighting:

- sparse text evidence shifts weight toward behavioral signals
- sparse comment evidence reduces intent dependence and leans on text/engagement

Rank quality guard:

- accounts below `audience_intent_score < 0.4` are filtered from final ranked output (default)

## Setup

```bash
cd /Users/kartikeybihani/Finek/TOMS/project
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Recommended `.env`:

```bash
APIFY_TOKEN=...
APIFY_HASHTAG_ACTOR_ID=apify~instagram-hashtag-scraper
APIFY_PROFILE_ACTOR_ID=apify~instagram-profile-scraper
APIFY_POST_ACTOR_ID=apify~instagram-scraper
APIFY_COMMENT_ACTOR_ID=apify~instagram-scraper

OPENROUTER_API_KEY=...
OPENROUTER_MODEL=mistralai/mixtral-8x7b-instruct
WHISPER_MODEL=base.en
```

Load env into current shell if needed:

```bash
set -a
source /Users/kartikeybihani/Finek/TOMS/project/.env
set +a
```

## Runbook

### Discovery run (CLI)

```bash
python3 seed.py --overwrite
python3 enrich.py --min-followers-for-posts 5000 --max-post-accounts 60 --max-comment-accounts 20 --posts-per-account 10 --comments-per-account 30
python3 score.py
python3 rank.py --min-followers 5000 --max-accounts 60
```

Core outputs:

- `data/raw_handles.csv`
- `data/enriched.json`
- `data/scored.csv`
- `data/final_ranked.csv`
- `data/review_bucket.csv`

### Monitor bootstrap

```bash
python3 monitor_bootstrap.py --input data/final_ranked.csv --limit 20
```

### Monitor run (live subset)

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

### Monitor run (mock)

```bash
python3 monitor_run.py --mode mock --fixture data/monitor/mock_posts.json
```

### Ensure schedule (architecture demo)

```bash
python3 monitor_schedule.py --ensure --cron "0 */4 * * *" --timezone "America/Phoenix"
```

## Reels-Only Generation Behavior

- Monitor dedupes all unseen posts in `seen_posts`.
- Only reel/video-eligible posts are queued into `new_posts_queue` for generation.
- Eligibility uses URL and payload signals to handle Instagram `/reel/` and reel-like `/p/` payloads.

Run report metrics include:

- `posts_seen_total`
- `posts_queued_video`
- `posts_skipped_non_video`

## Engagement Generation (Part 3.5)

Manual chunk:

```bash
python3 engage_generate.py --db-path data/monitor/monitor.db --limit 10
```

Drain pending queue in chunks:

```bash
python3 engage_generate.py --limit 10 --drain-pending --max-batches 20
```

Regenerate specific posts:

```bash
python3 engage_generate.py --post-ids 123,456 --force
```

Defaults used by generator:

- Character bible: `../blake/voice_builder/runs/blake_v1/07_character_bible.json`
- Generator prompt: `../blake/prompts/voice_builder/06_comment_generation.md`
- Critic prompt: `../blake/prompts/voice_builder/07_comment_critic.md`

## Queue Lifecycle

`new_posts_queue.status` values:

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

## Validation

```bash
cd /Users/kartikeybihani/Finek/TOMS/project
.venv/bin/python -m unittest discover -s tests -p "test_*.py"
```

## Troubleshooting

- `failed_accounts > 0` with monitor status `succeeded` usually means batch/API failures were handled but process completed; check run report `errors`.
- `generation_failed: openai-whisper is not installed` means you are using a different Python env than `.venv`.
- `processed=0` in `engage_generate` means no posts currently in `pending_comment_generation` (or selected filters excluded them).
- `new_posts=0` often means dedupe worked and posts were already seen in earlier runs.
