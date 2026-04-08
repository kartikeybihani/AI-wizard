# TOMS Operator UI (`ui/`)

Next.js operator app for running and reviewing the full workflow.

Pages:

- `/` - Run (Part 1 discovery)
- `/results` - Ranked output + artifacts
- `/monitor` - Part 2 post monitoring
- `/engage` - Part 4 human review for generated comments

This UI orchestrates Python scripts from `../project`.

## Requirements

- Node.js 20+
- npm
- Python environment available for `../project`
- `yt-dlp` + `ffmpeg` installed (needed by engagement generation)

## Environment Loading

Server resolves env in this order:

1. `ui/.env.local`
2. `ui/.env`
3. `project/.env`

Minimum keys (usually placed in `project/.env`):

```bash
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=mistralai/mixtral-8x7b-instruct

APIFY_TOKEN=...
APIFY_HASHTAG_ACTOR_ID=...
APIFY_PROFILE_ACTOR_ID=...
APIFY_POST_ACTOR_ID=...
APIFY_COMMENT_ACTOR_ID=...
```

Optional path overrides:

```bash
PIPELINE_CWD=/Users/kartikeybihani/Finek/TOMS/project
PIPELINE_PYTHON_BIN=/Users/kartikeybihani/Finek/TOMS/project/.venv/bin/python
```

## Install + Run

```bash
cd /Users/kartikeybihani/Finek/TOMS/ui
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## User Flow

### 1) Run

- Start a discovery run (`short`, `standard`, `deep`)
- Watch live logs and progress

### 2) Results

- Review ranked accounts
- Inspect score components
- Download artifacts

### 3) Monitor

- Bootstrap tracked accounts from latest run
- Run monitor on a small subset (live or mock)
- Queue new posts (reels/videos only for generation)

### 4) Engage

- Select queue status filter (`Ready`, `Pending`, `Failed`, etc.)
- Use `Generate Next N` for one chunk, `Generate Remaining` for chunked drain, or `Retry Selected` for one post
- Review reel preview + comment candidates
- Approve/edit/reject
- `Submit & Copy`

Notes:

- Transcript text is intentionally not shown in the operator UI.
- Queue header shows `Showing X of Y` and supports `Show All`.
- After generation actions, visible cards auto-expand to reduce operator friction.

## Key API Routes

- `POST /api/runs` start run
- `GET /api/runs` list runs
- `GET /api/runs/:id/stream` SSE logs
- `GET /api/runs/:id/results` parsed results
- `POST /api/monitor/bootstrap` bootstrap tracked accounts
- `POST /api/monitor/run` run monitor job
- `POST /api/monitor/schedule` ensure Apify schedule
- `GET /api/engage/posts` fetch review cards
- `POST /api/engage/generate` generate/regenerate comments
- `POST /api/engage/suggestions/:id/approve` approve suggestion
- `POST /api/engage/suggestions/:id/reject` reject suggestion
- `POST /api/engage/posts/:id/submit` mark submitted + return final text

## Validation

```bash
cd /Users/kartikeybihani/Finek/TOMS/ui
npm run lint
npm run test
npm run build
```
