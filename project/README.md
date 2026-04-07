# Influencer Discovery v1

Minimal runnable pipeline:

1. `seed.py` -> builds `data/raw_handles.csv`
2. `enrich.py` -> builds `data/enriched.json`
3. `score.py` -> builds `data/scored.csv`
4. `rank.py` -> builds `data/final_ranked.csv` and `data/review_bucket.csv`

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

## Run

```bash
python3 seed.py --overwrite
python3 enrich.py
python3 score.py
python3 rank.py --max-accounts 100
```

## Notes

- The Apify actor input schema varies by actor. This v1 sends generic keys (`usernames`, `hashtags`, `resultsLimit`, etc.), so use actors that accept those fields or adapt inputs in the scripts.
- `score.py` uses OpenRouter LLM scoring by default when `OPENROUTER_API_KEY` is present.
- Scoring is confidence-aware: when text is sparse, weights shift toward behavioral signals (audience intent + engagement quality).
- `review_bucket.csv` captures low-confidence but high-potential accounts for manual review.
- If API keys are missing, scripts still run in fallback mode for local wiring tests.
