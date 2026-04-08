# Operator UI (`ui/`)

Next.js control surface for the full workflow:

- run discovery
- inspect ranked influencers
- monitor recent posts
- review/approve/reject Blake-style comment suggestions

The UI orchestrates Python scripts in `/Users/kartikeybihani/Finek/TOMS/project`.

## Routes

- `/` - Discovery Run
- `/results` - Discovered influencer results and score evidence
- `/monitor` - Watchlist bootstrap + monitor job controls
- `/engage` - Human-in-the-loop review queue

## Product Workflow (Daily Operator View)

1. Run discovery on a cost-aware preset.
2. Inspect ranked influencers and remove weak fits.
3. Bootstrap monitor watchlist from a selected run.
4. Run monitor for a small live subset.
5. Generate suggestions in chunks.
6. Approve/edit/reject and submit with one-click copy.

## Requirements

- Node.js 20+
- npm
- Python backend set up in `/Users/kartikeybihani/Finek/TOMS/project`
- `yt-dlp` and `ffmpeg` installed for reel transcription

## Environment Resolution

Server reads env in this order:

1. `ui/.env.local`
2. `ui/.env`
3. `project/.env`

Minimum keys (usually in `project/.env`):

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

## Page-by-Page Behavior

### Discovery Run (`/`)

- Start preset: `short`, `standard`, or `deep`
- Use advanced overrides for cost/time control
- Streams live logs for `seed -> enrich -> score -> rank`
- Stores run artifacts for later review and monitor bootstrap

Recommended assessment setting:

- `standard` preset
- `seed.overwrite=true`
- `seed.skipApify=true` for stable low-cost demo
- `enrich.maxPostAccounts=60`
- `enrich.maxCommentAccounts=20`
- `rank.maxAccounts=60`

### Results (`/results`)

- Shows discovered influencer ranked table
- Columns include `Final`, `Rel`, `Intent`, `Eng`, `Depth`, `Conf`
- Click username to open details modal
- Detail modal includes evidence snippets and Instagram profile link
- Remove button lets operator drop low-fit accounts from that run output

### Monitor (`/monitor`)

- Step 1: bootstrap watchlist from latest run or explicit run id
- Step 2: run monitor job in live/mock mode
- Only reel/video-eligible posts are queued for generation
- Supports auto-generation right after monitor run

Monitor generation controls:

- `Auto Generate Comments After Run`
- `Generate Chunk Size`
- `Auto Drain Pending Queue (chunked)`
- `Max Drain Batches`

Run report cards surface:

- checked accounts
- new posts
- failures
- queued video count
- skipped non-video count

### Engage (`/engage`)

Primary actions:

- `Generate Next N`
- `Generate Remaining`
- `Regenerate Selected`
- `Clear Queue`

Reviewer actions:

- `Approve`
- `Reject`
- `Submit & Copy`

UX behavior:

- reel preview on left and suggestion panel on right
- status filters (`Ready`, `Pending`, `Failed`, `Approved`, `Submitted`, etc.)
- `Showing X of Y` with `Show All`
- approved action includes visual pulse and auto-advances to reduce review friction
- transcript text is intentionally hidden in UI for a cleaner operator experience

## API Surface

- `POST /api/runs` start discovery run
- `GET /api/runs` list runs
- `GET /api/runs/:id/stream` live step logs (SSE)
- `GET /api/runs/:id/results` parsed run results
- `POST /api/runs/:id/rows/remove` remove username from a run result
- `POST /api/monitor/bootstrap` bootstrap tracked accounts
- `POST /api/monitor/run` start monitor job
- `POST /api/monitor/schedule` configure schedule metadata
- `GET /api/engage/posts` fetch review cards
- `POST /api/engage/generate` generate/regenerate suggestions
- `POST /api/engage/suggestions/:id/approve` approve suggestion
- `POST /api/engage/suggestions/:id/reject` reject suggestion
- `POST /api/engage/posts/:id/submit` mark submitted and return final text
- `POST /api/engage/reset` clear queued review data

## Demo Script (Fast, Reliable)

1. Start a `standard` discovery run.
2. Open `Results`, verify 30+ credible mental-health accounts, remove weak outliers.
3. Open `Monitor`, bootstrap from latest run with limit 10-20.
4. Run monitor with small subset and auto-generate on.
5. Open `Engage`, click `Generate Next N` (or `Generate Remaining`), then approve/edit/reject/submit.

This demonstrates all four assessment parts with a practical live subset and clear operator UX.

## Validation

```bash
cd /Users/kartikeybihani/Finek/TOMS/ui
npm run lint
npm run test
npm run build
```

## Troubleshooting

- If monitor shows many failures with status `succeeded`, inspect the run report errors (often API quota/rate limits).
- If engage generation fails with Whisper missing, run UI against the same Python env where `openai-whisper` is installed.
- If no cards appear in Engage, check `Monitor` run metrics for `queued_video` and use `All` filter first.
- After changing API tokens in `.env`, restart `npm run dev` so server-side env is refreshed.
