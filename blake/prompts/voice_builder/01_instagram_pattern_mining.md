# Prompt: Instagram Pattern Mining

## Purpose
Extract the short-form, comment-ready voice patterns Blake uses in Instagram captions.

## Use Case
Run this on one batch of 50-100 captions at a time. The goal is not a summary of the batch. The goal is to identify stable caption structures, emotional units, and language habits.

## Input

```text
{{caption_batch_json}}
```

The input JSON should include, when available:

- `username`
- `captions`
- `captions[].text`
- `captions[].timestamp`
- `captions[].likes`
- `captions[].comments`
- `captions[].url`

## Instructions

Analyze the batch as short-form public voice.

Prioritize:

- sentence length
- spacing / line breaks
- first-person emotional framing
- how he opens a thought
- how he lands a point
- whether he advises, observes, or invites
- recurring structural templates
- recurring word choices
- what he does not do

When the input spans multiple eras, weight toward the most recent captions if you are identifying current style.

Apply the global synthesis weights conceptually:

- podcasts / transcripts 45%
- substack + personal site 30%
- instagram captions 20%
- external articles 5% facts only

For this prompt, focus on Instagram only, but keep the eventual synthesis hierarchy in mind.

## Output Rules

Return strict JSON only. No markdown, no commentary.

## Output Schema

```json
{
  "prompt_version": "voice_builder.instagram.v1",
  "source_type": "instagram_captions_batch",
  "batch_summary": {
    "username": "",
    "total_captions": 0,
    "date_range": {
      "start": "",
      "end": ""
    },
    "era_mix": {
      "era_a_count": 0,
      "era_b_count": 0,
      "era_c_count": 0
    }
  },
  "top_patterns": [
    {
      "pattern_name": "",
      "description": "",
      "structure_template": "",
      "when_it_appears": "",
      "example_quotes": [
        ""
      ],
      "frequency_estimate": "high",
      "confidence": 0.0
    }
  ],
  "archetypal_structures": [
    {
      "structure_name": "",
      "formula": "",
      "emotional_job": "",
      "example_quotes": [
        ""
      ],
      "confidence": 0.0
    }
  ],
  "language_habits": {
    "openers": [],
    "closers": [],
    "bridge_phrases": [],
    "favorite_verbs": [],
    "favorite_nouns": [],
    "sentence_length_profile": "",
    "line_break_style": ""
  },
  "voice_tells": [
    {
      "tell": "",
      "why_it_matters": "",
      "example_quotes": [
        ""
      ]
    }
  ],
  "anti_patterns": [
    ""
  ],
  "synthesis_notes": {
    "what_this_batch_says_about_current_voice": "",
    "what_changed_vs_older_voice": "",
    "confidence": 0.0
  }
}
```

## Quality Bar

- Prefer exact examples from the captions.
- Do not invent polish that is not present.
- Do not generalize too early.
- Keep the result specific enough to be reusable in later synthesis.

