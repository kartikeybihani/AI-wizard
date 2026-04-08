# Prompt: Podcast Depth Arcs

## Purpose
Extract Blake's deeper identity and life-story arcs from long-form podcast conversations.

## Use Case
Run once per podcast transcript. Use this for the emotional and narrative depth layer.

## Input

```text
{{podcast_transcript_json}}
```

The input JSON should include:

- `source_id`
- `title`
- `url`
- `published_at`
- `host`
- `transcript_text`

## Instructions

Focus on:

- origin story
- identity shifts
- pain points
- spiritual search
- depression / healing language
- relationship to success
- recurring philosophical claims
- how he narrates change over time

This prompt should identify the story arcs that make his comments feel lived-in rather than performative.

Temporal rule:

- Prioritize 2025-2026 voice when the transcript comes from the Enough era.
- Preserve older arcs as origin evidence, but do not let them override current voice.

Global synthesis weights:

- podcasts / transcripts 45%
- substack + personal site 30%
- instagram captions 20%
- external articles 5% facts only

## Output Rules

Return strict JSON only.

## Output Schema

```json
{
  "prompt_version": "voice_builder.podcast.v1",
  "source_type": "podcast_transcript",
  "metadata": {
    "source_id": "",
    "title": "",
    "url": "",
    "published_at": "",
    "host": ""
  },
  "core_arcs": [
    {
      "arc_name": "",
      "arc_summary": "",
      "turning_points": [
        ""
      ],
      "language_used": [
        ""
      ],
      "why_it_matters_for_voice": "",
      "confidence": 0.0
    }
  ],
  "inner_life_patterns": [
    {
      "pattern_name": "",
      "description": "",
      "evidence_quotes": [
        ""
      ],
      "confidence": 0.0
    }
  ],
  "belief_hierarchy": {
    "top_beliefs": [],
    "secondary_beliefs": [],
    "tensions": []
  },
  "recurring_metaphors": [
    {
      "metaphor": "",
      "meaning": "",
      "evidence_quotes": [
        ""
      ]
    }
  ],
  "identity_shift_notes": {
    "who_he_was_before": "",
    "who_he_is_now": "",
    "what_caused_the_shift": "",
    "confidence": 0.0
  },
  "era_read": {
    "era_a_signal": 0.0,
    "era_b_signal": 0.0,
    "era_c_signal": 0.0,
    "current_voice_weight": 0.0,
    "notes": ""
  }
}
```

## Quality Bar

- Prefer concrete turning points over vague themes.
- Keep the language psychologically precise but not clinical.
- Avoid flattening the arc into a generic "growth mindset" story.

