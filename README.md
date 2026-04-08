# Mental Health Influencer Engagement Agent (TOMS Technical Assessment)

This is a working prototype for Blake Mycoskie's assessment brief.

The goal: discover mental-health influencers, monitor their new posts, generate Blake-style comment suggestions, and give a human a clean approve/edit/reject workflow.

## What This Repository Contains

- `project/` - Python backend pipeline (discovery, monitoring, generation)
- `blake/` - Blake corpus + voice extraction pipeline + final character bible
- `ui/` - Next.js operator app (`Run`, `Results`, `Monitor`, `Engage`)

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

## My Approach to Capturing Blake's Voice

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
- Step 6: Anti-patterns ("anti-Blake": what he would not say)
- Step 7: Final character bible

Final output used by generation:
- `blake/voice_builder/runs/blake_v1/07_character_bible.json`

This anti-pattern step was critical because it constrained generic "warm founder" output and made comments feel specifically Blake.

## Tools and Models Used

- Data collection: Apify actors + custom ingestion scripts
- Transcript/audio: `yt-dlp`, `ffmpeg`, `openai-whisper` (local)
- LLM provider: OpenRouter
- Generation stack: prompt templates + JSON structured output
- Backend: Python
- UI: Next.js
- Storage: SQLite

Model choice is configurable by env. Defaults are in the code (`OPENROUTER_MODEL`, plus extract/synthesis/critic variants for the voice builder).

## How To Run (Manual, Evaluator-Friendly)

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
APIFY_HASHTAG_ACTOR_ID=...
APIFY_PROFILE_ACTOR_ID=...
APIFY_POST_ACTOR_ID=...
APIFY_COMMENT_ACTOR_ID=...

OPENROUTER_API_KEY=...
OPENROUTER_MODEL=mistralai/mixtral-8x7b-instruct
WHISPER_MODEL=base.en
```

## 3) UI setup + run

```bash
cd /Users/kartikeybihani/Finek/TOMS/ui
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## 4) Test the full workflow in UI

1. `Run` page
- Start `short` or `standard` run
- Wait for ranked output

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

## Why This Is Scoped This Way

The assessment explicitly values working software and clear system logic over over-engineered infra.

So this version is intentionally practical:
- real pipeline
- live subset support
- clean human review loop
- simple storage
- reproducible local run

