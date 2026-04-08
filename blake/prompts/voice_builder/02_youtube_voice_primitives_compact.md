# Prompt: YouTube Voice Primitives (Compact)

## Purpose
Extract Blake's conversational voice behavior from a YouTube transcript chunk.

## Input

```text
{{youtube_transcript_chunk_json}}
```

Input JSON includes:

- `doc_id`
- `title`
- `date_key`
- `era`
- `chunk_index`
- `chunk_count`
- `text`

## Instructions

Focus on how he speaks, not topic summary:

- rhythm
- bridge words
- self-corrections
- uncertainty handling
- vulnerability signals

## Output Rules

Return strict JSON only.
Keep output compact and deterministic.

Hard limits:

- `primitives`: exactly 6
- `thought_patterns`: max 4
- `vulnerability`: max 4
- `rhythm.openers/bridges/closers`: max 4 each
- any quote <= 14 words
- each string <= 14 words
- no extra keys, no paragraphs

## Output Schema

```json
{
  "prompt_version": "voice_builder.youtube.v2_compact",
  "source_type": "youtube_chunk",
  "m": {
    "doc_id": "",
    "era": ""
  },
  "primitives": [
    {
      "p": "",
      "q": "",
      "c": 0.0
    }
  ],
  "rhythm": {
    "openers": [],
    "bridges": [],
    "closers": []
  },
  "thought_patterns": [
    ""
  ],
  "vulnerability": [
    ""
  ],
  "signature_words": []
}
```

## Quality Bar

- Prefer repeated patterns.
- Keep evidence direct and short.
- If uncertain, output less not more.
