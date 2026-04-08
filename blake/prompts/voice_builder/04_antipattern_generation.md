# Prompt: Anti-Pattern Generation

## Purpose
Define the negative space of Blake's voice by generating near-miss examples that feel wrong.

## Use Case
Run after you have a strong set of positive examples from Instagram, YouTube, podcasts, and written sources.

## Input

```text
{{positive_examples_bundle_json}}
```

The input JSON should include:

- `positive_examples`
- `source_type`
- `era`
- `what_works`

## Instructions

Generate examples of what Blake would NOT say, even if the topic is correct.

Use these constraints:

- no therapy-speak cliches
- no preachy tone
- no corporate language
- no generic self-help filler
- no overexplaining
- no hashtags in personal voice
- no brand-dropping unless contextually necessary

This prompt should help the critic model and the final generation prompt by making the failure modes explicit.

## Output Rules

Return strict JSON only.

## Output Schema

```json
{
  "prompt_version": "voice_builder.antipatterns.v1",
  "source_type": "anti_pattern_generation",
  "positive_example_summary": {
    "sources_used": [],
    "dominant_era": "",
    "dominant_voice_traits": []
  },
  "forbidden_moves": [
    {
      "move_name": "",
      "why_it_is_wrong": "",
      "bad_example": "",
      "repair_hint": ""
    }
  ],
  "near_miss_examples": [
    {
      "topic": "",
      "bad_comment": "",
      "failure_reasons": [
        ""
      ],
      "fixed_version_hint": ""
    }
  ],
  "language_traps": [
    {
      "trap": "",
      "why_it_dilutes_blake": "",
      "replacement_strategy": ""
    }
  ],
  "voice_boundaries": {
    "never_do": [],
    "usually_avoid": [],
    "allowed_only_when_contextually_earned": []
  }
}
```

## Quality Bar

- Make the bad examples realistically tempting.
- Explain why they fail in terms of voice, not just taste.
- Keep the output useful for a critic and a generator.

