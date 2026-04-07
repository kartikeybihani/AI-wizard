# TOMS Operator UI

Next.js operator console for the existing Python influencer pipeline.

- UI app: `/Users/kartikeybihani/Finek/TOMS/ui`
- Pipeline source of truth: `/Users/kartikeybihani/Finek/TOMS/project`
- Single active run at a time
- Queued runs supported
- Live progress + logs through SSE
- Run history persisted in SQLite (`/ui/data/runs.db`)
- Artifacts copied per run into `/project/data/runs/<run_id>/`

## Requirements

- Node.js 20+
- npm
- `python3` available in PATH
- Python dependencies installed for `/project` scripts

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
