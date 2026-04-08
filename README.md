# Mental Health Influencer Engagement Agent (TOMS Technical Assessment)

This is a working prototype for Blake Mycoskie's assessment brief.

The goal: discover mental-health influencers, monitor their new posts, generate Blake-style comment suggestions, and give a human a clean approve/edit/reject workflow.

## What This Repository Contains

- `project/` - Python backend pipeline (discovery, monitoring, generation)
- `blake/` - Blake corpus + voice extraction pipeline + final character bible
- `ui/` - Next.js operator app (`Discovery Run`, `Results`, `Monitor`, `Engage`)

## Architecture (End-to-End)

1. Discovery (Part 1)
- Seed handles (`seed.py`)
- Enrich profile + posts + comments (`enrich.py`)
- Score and rank (`score.py`, `rank.py`)

2. Monitoring (Part 2)
- Bootstrap tracked accounts from ranked output (`monitor_bootstrap.py`)
- Poll recent posts on a small live subset (`monitor_run.py`)
- Queue reel/video-eligible posts for comment generation

3. Comment Generation (Part 3)
- Transcribe reel audio with local Whisper (`yt-dlp` + `ffmpeg` + `openai-whisper`)
- Build context from caption + transcript
- Generate Blake-style candidates + critic scoring (`engage_generate.py`)
- Store suggestions and status in SQLite

4. Human-in-the-loop UI (Part 4)
- Reel preview on the left, suggestions on the right
- Approve/edit/reject
- Submit + copy final comment text

Storage is intentionally simple: SQLite (no Supabase in this version).

## Discovery Philosophy (Why These Creators)

I intentionally did not optimize discovery for generic quote pages or broad "motivation" pages.

My lens for mental-health creators:

- prioritize creators whose content helps people actually work through anxiety, depression, trauma, burnout, identity, and recovery
- prefer evidence of trust in comments ("this helped", "I needed this", emotional disclosure) over vanity metrics
- score down accounts that look like generic dopamine loops (high posting, low depth, broad motivation with little therapeutic signal)

The result is a pipeline that favors practical, emotionally resonant mental-health voices over high-volume inspiration pages.

## Part 1 Discovery: How It Actually Works

Discovery is a 4-step pipeline: `seed -> enrich -> score -> rank`.

### `seed.py` (candidate handle collection)

By default, seed combines three sources:

1. curated manual handles (`manual_seed`)
2. aggregator-style starter handles (`aggregator_seed`)
3. Apify hashtag discovery (`apify_hashtag:<tag>`)

Default hashtags:
- `#mentalhealth`
- `#anxietyhelp`
- `#therapy`
- `#mentalhealthadvocate`
- `#mentalhealthawareness`
- `#enoughmovement`

Important: the hashtag pass recursively scans actor payloads and extracts plausible usernames from nested objects, then deduplicates.

`--overwrite` behavior:
- with `--overwrite`: rebuilds `data/raw_handles.csv` from current run inputs only
- without `--overwrite`: merges new rows with existing `data/raw_handles.csv` before deduping

### `enrich.py` (evidence gathering)

For each handle, enrich collects:
- profile signals: bio, followers/following, avg likes/comments
- recent posts (caption + likes/comments + timestamps)
- recent comments (or embedded comments from post actor)

It prioritizes accounts above a follower threshold for post scraping, then picks strongest candidates for comment scraping.

### `score.py` (mental-health relevance scoring)

Each account gets four core scores:
- `relevance_score`: is this primarily a mental-health account?
- `audience_intent_score`: do comments show trust/help-seeking/emotional resonance?
- `content_depth_score`: are captions specific/insightful vs generic?
- `engagement_quality_score`: quality-normalized engagement (median ER + consistency + ratio penalties)

Final ranking score is a weighted blend with confidence-aware dynamic weighting:
- base blend: relevance `0.35`, audience intent `0.30`, engagement quality `0.20`, content depth `0.15`
- if text evidence is sparse, weight shifts toward behavioral signals (intent + engagement)
- if comments are sparse, audience-intent dependence is reduced and text/engagement get more weight

To avoid generic meme/motivation pages, scoring also applies topical signals:
- positive mental-health terms (anxiety, therapy, trauma, etc.)
- negative off-topic terms (hustle/discount/shop-now style language)

### `rank.py` (final selection)

Accounts are tiered (`micro`, `mid`, `macro`, `major`) and filtered/ranked by `final_score`, with configurable minimum followers and max accounts.
An additional quality guard filters low audience-intent accounts (`audience_intent_score >= 0.4` by default).

Low-confidence but high-potential accounts are sent to `review_bucket.csv` for manual review.

## Run Presets (`short`, `standard`, `deep`)

From UI `Discovery Run` page:

- `short`: quick smoke test (small limits; fastest)
- `standard`: day-to-day run (balanced quality/cost)
- `deep`: larger research run (broadest coverage; highest cost/time)

Current defaults differ mainly in:
- seed breadth (`manualCount`, `aggregatorCount`, `hashtagLimitPerTag`)
- enrich depth (`maxPostAccounts`, `postsPerAccount`, `maxCommentAccounts`, `commentsPerAccount`)

Preset snapshot (current defaults):

- `short`: seed `all/all/5`; enrich `15 post accounts`, `8 posts/account`, `8 comment accounts`, `20 comments/account`
- `standard`: seed `all/all/20`; enrich `80 post accounts`, `20 posts/account`, `30 comment accounts`, `40 comments/account`
- `deep`: seed `all/all/60`; enrich `150 post accounts`, `40 posts/account`, `80 comment accounts`, `120 comments/account`

## If You Want Pure Discovery (No Curated Seed Handles)

In UI Advanced overrides for `seed`:
- set `manualCount = 0`
- set `aggregatorCount = 0`
- keep `skipApify = false`
- keep `overwrite = true`

That run will rely only on hashtag-based discovery.

## My Approach to Capturing Blake's Voice

This was the coolest part of the assessment.

I did not treat this as "summarize Blake." I treated it as building a character bible from a person who has evolved across eras.

Core principle:
- Blake from early TOMS years is not the same as current Blake in the Enough era.
- I used past + present to model identity shift, not just current captions.

I split sources into 5 buckets:

1. Self
- Personal site
- Substack
- Wikipedia

2. Podcasts / long-form interviews
- Tim Ferriss + YouTube interviews

3. Instagram
- Captions corpus across his posts (high-volume short-form voice)

4. External articles / company about pages
- News + third-party framing + company narratives

5. Book
- `Start Something That Matters` material

Then I ran a staged extraction pipeline and synthesized one final artifact:

- Step 1: Instagram pattern mining
- Step 2: YouTube voice primitives
- Step 3: Podcast depth arcs
- Step 4: Written values
- Step 5: External calibration
- Step 6: Anti-patterns ("anti-Blake": what he would not say from his podcasts/interview transcripts)
- Step 7: Final character bible

Final output used by generation:
- `blake/voice_builder/runs/blake_v1/07_character_bible.json`

Voice weighting used in the final bible (concise):
- source weights: podcasts/transcripts `45%`, Substack/personal site `30%`, Instagram captions `20%`, external factual sources `5%`
- era weights: early TOMS builder `10%`, transition/seeker era `30%`, current Enough-era voice `60%`

This anti-pattern step was critical because it constrained generic "warm founder" output and made comments feel specifically Blake.

## Tools and Models Used

- Data collection: Apify actors + custom ingestion scripts
- Transcript/audio: `yt-dlp`, `ffmpeg`, `openai-whisper` (local)
- LLM provider: OpenRouter (many free model options, including strong classification and reasoning models for pipeline stages)
- Generation stack: prompt templates + JSON structured output
- Backend: Python
- UI: Next.js
- Storage: SQLite

Model choice is configurable by env. Defaults are in the code (`OPENROUTER_MODEL`, plus extract/synthesis/critic variants for the voice builder).

### Why `mistralai/mixtral-8x7b-instruct` by default

I used Mixtral because it gave the best practical tradeoff for this prototype:

- Strong instruction-following for strict prompt formats (especially JSON extraction stages)
- Good long-context handling for multi-source voice synthesis
- MoE behavior that feels close to GPT-4-class reasoning for this task, at a practical cost/latency point

For this project, that mattered in two places:

- Building Blake's character bible from mixed source buckets
- Generating comments that stay on-voice while still reacting to what the reel is actually about

## Results Table: Column Meaning

In `Results` table:

- `Final` = weighted final ranking score
- `Rel` = `relevance_score` (mental-health topical fit)
- `Intent` = `audience_intent_score` (help-seeking/trust signals in comments)
- `Eng` = `engagement_quality_score` (quality-adjusted engagement, not raw likes only)
- `Depth` = `content_depth_score` (specificity and insight depth)
- `Conf` = `confidence_grade` (`high` / `medium` / `low`) based on text/comment/post evidence volume

## How To Run (Manual)

## 1) Prerequisites

- Python 3.10+
- Node.js 20+
- npm
- `ffmpeg`
- `yt-dlp`
- Apify API token + actor IDs
- OpenRouter API key

## 2) Backend setup

```bash
cd /Users/kartikeybihani/Finek/TOMS/project
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill `project/.env`:

```bash
APIFY_TOKEN=...
APIFY_HASHTAG_ACTOR_ID=apify~instagram-hashtag-scraper
APIFY_PROFILE_ACTOR_ID=apify~instagram-scraper
APIFY_POST_ACTOR_ID=apify~instagram-scraper
APIFY_COMMENT_ACTOR_ID=apify~instagram-scraper

OPENROUTER_API_KEY=...
OPENROUTER_MODEL=mistralai/mixtral-8x7b-instruct
WHISPER_MODEL=base.en
```

Note: discovery uses username-based profile/post/comment enrichment. Reels-only behavior is enforced later in Monitor/Engage queueing, not by forcing reel-only actors in discovery.

## 3) UI setup + run

```bash
cd /Users/kartikeybihani/Finek/TOMS/ui
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## 4) Test the full workflow in UI

1. `Discovery Run` page
- Start `standard` run
- Recommended low-cost, high-signal settings in Advanced:
  - `seed.overwrite = true`
  - `seed.skipApify = true` (fastest/cheapest repeatable demo; uses curated + aggregator handle pools)
  - `enrich.minFollowersForPosts = 5000`
  - `enrich.maxPostAccounts = 60`
  - `enrich.maxCommentAccounts = 20`
  - `enrich.postsPerAccount = 10`
  - `enrich.commentsPerAccount = 30`
  - `rank.maxAccounts = 60`
- Wait for ranked output

If you want live hashtag expansion instead of curated-only, set `seed.skipApify = false`.

2. `Results` page
- Inspect ranked accounts and rationale

3. `Monitor` page
- Bootstrap from latest run
- Run monitor on small subset (for cost/rate limits)

4. `Engage` page
- `Generate Next N` or `Generate Remaining`
- Review suggestions
- Approve/edit/reject
- `Submit & Copy`

This demonstrates all four parts of the brief with a practical live subset.

## What I Would Improve With More Time

1. Deeper discovery quality (beyond surface metrics)
- Build a richer influencer graph: historical consistency, topical drift, cross-platform context, long-horizon credibility.
- Score on deeper semantic fit, not only engagement/hashtags.

2. Continuous autonomous monitoring
- Event-driven workers that keep tracking selected influencers every 1-2 hours.
- Auto-prioritize posts worth commenting on, then notify human reviewer.

3. Better multimodal post understanding
- Stronger reel-level analysis (speech, context, emotional intent, claims/risk).
- Better relevance detection before generation.

4. Human workflow and execution
- SLA-style inbox for reviewer queue, urgency sorting, and one-click bulk actions.
- Optional direct publish integration later (kept manual in this prototype intentionally).

5. Reliability and governance
- Better eval harness for voice consistency and safety drift.
- Versioned prompts + model routing + automatic fallback.

### Why This Is Scoped This Way

The assessment explicitly values working software and clear system logic over over-engineered infra.
So this version is intentionally practical with real pipeline, clean human review loop, simple storage, and reproducible local run.
