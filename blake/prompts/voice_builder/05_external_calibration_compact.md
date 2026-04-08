# Prompt: External Calibration (Compact)

## Purpose
Extract third-person calibration signals from external articles and biographies.

## Use Case
Use this only as a secondary QA layer. Do not treat this as primary voice training data.

## Input

```text
{{external_article_chunk_json}}
```

Input JSON includes:

- `doc_id`
- `title`
- `bucket`
- `date_key`
- `era`
- `text`

## Instructions

Extract only:

- third-person descriptors of Blake
- factual points useful for timeline/context
- caution flags about media framing

Do not infer personal voice from this source.

## Output Rules

Return strict JSON only.
Keep output compact and deterministic.

Hard limits:

- `descriptors`: exactly 6 items
- `factual_points`: max 6 items
- `caution_flags`: max 4 items
- each string <= 14 words
- no extra keys, no long prose

## Output Schema

```json
{
  "prompt_version": "voice_builder.external_calibration.v1",
  "source_type": "external_article_chunk",
  "m": {
    "doc_id": "",
    "era": ""
  },
  "descriptors": [
    {
      "d": "",
      "e": "",
      "confidence": 0.0
    }
  ],
  "factual_points": [
    ""
  ],
  "caution_flags": [
    ""
  ]
}
```

## Quality Bar

- Keep only concrete facts or recurring descriptors.
- Avoid psychologizing.
- Keep everything short and parse-safe.
