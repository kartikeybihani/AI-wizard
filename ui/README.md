# TOMS Operator UI

Next.js operator console for the existing Python influencer pipeline.

- UI app: `/Users/kartikeybihani/Finek/TOMS/ui`
- Pipeline source of truth: `/Users/kartikeybihani/Finek/TOMS/project`
- Single active run at a time
- Queued runs supported
- Live progress + logs through SSE
- Run history persisted in SQLite (`/ui/data/runs.db`)
- Artifacts copied per run into `/project/data/runs/<run_id>/`
- Part 2 monitor operator page for ongoing post detection (`/monitor`)
- Part 3.5 engage operator page for reel transcription + Blake comments (`/engage`)

## Requirements

- Node.js 20+
- npm
- `python3` available in PATH
- Python dependencies installed for `/project` scripts
- `yt-dlp` and `ffmpeg` installed locally (for reel audio extraction/transcription)

## Environment Setup

The server loads env in this order:

1. `/ui/.env.local`
2. `/ui/.env`
3. `/project/.env`

Minimum required keys:

```bash
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=mistralai/mixtral-8x7b-instruct

APIFY_TOKEN=...
APIFY_HASHTAG_ACTOR_ID=apify/instagram-hashtag-scraper
APIFY_PROFILE_ACTOR_ID=apify/instagram-scraper
APIFY_POST_ACTOR_ID=apify/instagram-scraper
APIFY_COMMENT_ACTOR_ID=apify/instagram-scraper
```

Optional:

```bash
PIPELINE_CWD=/Users/kartikeybihani/Finek/TOMS/project
```

Notes:

- If you use one multi-purpose Apify actor, set the same actor ID for profile/post/comment IDs.
- Keep keys in `/project/.env` if you want both CLI scripts and UI to use the same credentials.
- For schedule creation from UI (`/monitor`), set one of:
  - `APIFY_MONITOR_ACTOR_TASK_ID` (preferred), or
  - `APIFY_MONITOR_ACTOR_ID`

## Install + Run

```bash
cd /Users/kartikeybihani/Finek/TOMS/ui
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Operator Flow

1. Go to `/` (Run page)
2. Pick preset:
- `short`: smoke test
- `standard`: normal operation
- `deep`: larger run
3. (Optional) open advanced overrides
4. Click **Start Run**
5. Watch live step timeline + logs
6. Go to `/results` to review ranked table, review bucket, and download artifacts
7. Go to `/monitor` to bootstrap tracked accounts, run monitor polling, and ensure the Apify 4-hour schedule
8. Go to `/engage` to review generated comments, approve/edit/reject, and submit/copy

## Monitor Flow (`/monitor`)

1. Bootstrap tracked accounts from either:
- `final_ranked.csv` (default), or
- latest successful pipeline run artifact (`/project/data/runs/<run_id>/final_ranked.csv`)
2. Run monitor job (`live` or `mock`) to detect unseen posts
3. Review recent queue rows with exact post URLs
4. Ensure/update recurring schedule through Apify Schedule API

Monitor state source:

- SQLite DB: `/Users/kartikeybihani/Finek/TOMS/project/data/monitor/monitor.db`
- Queue table: `new_posts_queue` (`pending_comment_generation` entries)

## Engage Flow (`/engage`)

1. Run monitor (with auto-generation on) to queue reel/video posts and transcribe/generate candidates
2. Open `/engage` and filter by status (`Ready`, `Failed`, `Submitted`)
3. Select a reel card, review transcript and candidate comments
4. Approve/edit/reject candidates
5. Submit approved suggestion and copy final comment text

## What Each Run Executes

Executed in `/project`:

1. `seed.py`
2. `enrich.py`
3. `score.py`
4. `rank.py`

Each step status is persisted as:

- `pending`
- `running`
- `succeeded`
- `failed`
- `cancelled`

## Stored Artifacts

For each run ID, files are copied into:

`/Users/kartikeybihani/Finek/TOMS/project/data/runs/<run_id>/`

Files:

- `raw_handles.csv`
- `enriched.json`
- `scored.csv`
- `final_ranked.csv`
- `review_bucket.csv`
- `run.log`

Retention:

- Keeps latest 30 terminal runs (`succeeded`, `failed`, `cancelled`)
- Older runs are pruned from DB and run folders

## API Endpoints

- `GET /api/monitor` monitor overview (counts, queue rows, monitor runs, tracked accounts, recent monitor jobs)
- `POST /api/monitor/bootstrap` run `monitor_bootstrap.py`
- `POST /api/monitor/run` run `monitor_run.py`
- `POST /api/monitor/schedule` run `monitor_schedule.py` (Apify schedule create/update)
- `GET /api/monitor/jobs/:id` fetch monitor job detail/logs
- `GET /api/engage/posts?status=ready_for_review&limit=10` fetch review cards
- `POST /api/engage/generate` manual generation/regeneration job (`engage_generate.py`)
- `POST /api/engage/suggestions/:id/approve` approve with optional edited text
- `POST /api/engage/suggestions/:id/reject` reject with optional reason
- `POST /api/engage/posts/:id/submit` mark submitted and return final comment
- `POST /api/runs` start run (`preset` + optional `overrides`)
- `GET /api/runs` list runs + queue/active state
- `GET /api/runs/:id` run detail + log tail
- `GET /api/runs/:id/stream` SSE events
- `POST /api/runs/:id/cancel` cancel queued/running run
- `GET /api/runs/:id/results` parsed `final_ranked` + `review_bucket`
- `GET /api/runs/:id/download?file=...` artifact download

Download `file` options:

- `raw_handles`
- `enriched`
- `scored`
- `final_ranked`
- `review_bucket`
- `run_log`

## Validation Commands

```bash
cd /Users/kartikeybihani/Finek/TOMS/ui
npm run lint
npm run test
npm run build
```
