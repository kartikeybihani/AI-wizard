# Prompt: Written Values Extraction (Compact)

## Purpose
Extract Blake's intentional written voice from Substack and personal-site writing with an ultra-compact JSON output.

## Use Case
Run on one written chunk at a time, then consolidate per document.

## Input

```text
{{written_source_json}}
```

The input JSON includes:

- `doc_id`
- `title`
- `bucket`
- `date_key`
- `era`
- `text`

## Instructions

Focus on deliberate writing signals:

- values hierarchy
- concise rhetorical moves
- recurring lexical choices
- emotional stance in written form
- what this implies for comment tone

Do not summarize biography. Do not produce broad life-story arcs.

Temporal rule:

- Weight 2025-2026 phrasing as strongest for current voice.
- Keep older wording as supporting evidence only.

## Output Rules

Return strict JSON only.
Keep output extremely small and deterministic.

Hard limits (must obey):

- `values`: exactly 3 items
- `rhetoric`: exactly 3 items
- `implications`: exactly 3 items
- `avoid`: exactly 3 items
- each quote (`q`) <= 12 words
- each string field <= 12 words
- no extra keys, no prose paragraphs

## Output Schema

```json
{
  "prompt_version": "voice_builder.written_values.v1",
  "source_type": "written_chunk",
  "m": {
    "doc_id": "",
    "era": ""
  },
  "values": [
    {
      "v": "",
      "q": "",
      "confidence": 0.0
    }
  ],
  "rhetoric": [
    {
      "p": "",
      "q": "",
      "confidence": 0.0
    }
  ],
  "lex": {
    "w": [],
    "b": [],
    "t": ""
  },
  "implications": [
    ""
  ],
  "avoid": [
    ""
  ]
}
```

## Quality Bar

- Keep only repeated patterns visible in text.
- Prefer short evidence snippets.
- If uncertain, use shorter text not longer text.
