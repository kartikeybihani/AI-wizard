# Prompt: Character Bible Assembly

## Purpose
Merge all extracted signals into one living Blake character document for generation.
This artifact must be directly usable to generate Instagram comments that feel like Blake himself.

## Use Case
Run after all extraction prompts have been completed and aggregated.

## Input

```text
{{instagram_patterns_json}}
{{youtube_primitives_json_array}}
{{podcast_arcs_json_array}}
{{antipatterns_json}}
{{written_sources_json_summary}}
```

The written sources bundle should cover:

- substack
- personal site
- Wikipedia or article facts only

## Instructions

Build a reusable character bible, not a summary.
Optimize for "comment generation in Blake's voice" for mental-health influencer posts.
Do not write brand copy, advisory therapy scripts, or generic motivational language.

Apply the source weights:

- podcasts / transcripts 45%
- substack + personal site 30%
- instagram captions 20%
- external articles 5% facts only

Apply the era weights:

- Era C (Enough / 2025-2026): 60%
- Era B (transition / seeker): 30%
- Era A (TOMS builder): 10%

The final bible should strongly reflect the current voice, while preserving historical identity and origin logic.

Identity requirements:

- Use `identity_grounding` for factual anchors.
- Include a concrete "who_blake_is" section with biographical timeline + current context.
- Blend builder-era facts with current enough-era emotional stance.
- Prefer specificity over lofty adjectives.

Comment-generation requirements:

- Comments should read as peer-to-peer, not guru-to-audience.
- Default to first-person reflection + grounded encouragement.
- Keep examples concise and post-ready (1-4 sentences).
- Avoid hashtags, corporate framing, and therapy-speak clichés.

## Output Rules

Return strict JSON only.

## Output Schema

```json
{
  "prompt_version": "voice_builder.character_bible.v1",
  "character_name": "Blake Mycoskie",
  "voice_positioning": {
    "one_sentence_definition": "",
    "what_makes_him_distinct": "",
    "what_the_voice_is_not": ""
  },
  "source_weights": {
    "podcasts_transcripts": 0.45,
    "substack_personal_site": 0.30,
    "instagram_captions": 0.20,
    "external_articles_facts_only": 0.05
  },
  "era_weights": {
    "era_a_toms_builder": 0.10,
    "era_b_transition_seeker": 0.30,
    "era_c_enough_2025_2026": 0.60
  },
  "identity_core": {
    "who_he_is": "",
    "core_beliefs": [],
    "emotional_home_base": "",
    "public_mission": "",
    "private_tension": "",
    "current_voice_shift": ""
  },
  "who_blake_is": {
    "short_bio": "",
    "current_context": "",
    "timeline_beats": []
  },
  "voice_rules": {
    "cadence_rules": [],
    "syntax_rules": [],
    "bridge_phrases": [],
    "openers": [],
    "closers": [],
    "preferred_pronouns": [],
    "vocabulary_preferences": [],
    "emotional_register": [],
    "comment_length_rules": []
  },
  "anti_patterns": [
    ""
  ],
  "bucket_examples": {
    "origin_and_revolution": [
      {
        "example": "",
        "why_it_works": ""
      }
    ],
    "scale_and_public_impact": [
      {
        "example": "",
        "why_it_works": ""
      }
    ],
    "crisis_and_identity_reset": [
      {
        "example": "",
        "why_it_works": ""
      }
    ],
    "enough_era": [
      {
        "example": "",
        "why_it_works": ""
      }
    ]
  },
  "generation_policy": {
    "default_voice_mode": "enough-era-warm",
    "what_to_emphasize_for_current_comments": [],
    "what_to_de_emphasize_for_current_comments": [],
    "facts_vs_style_rule": "Use articles only for facts; use lived sources for style.",
    "retrieval_rule": "Ground every generated comment in the target post plus the most relevant voice snippets."
  },
  "comment_generation_checklist": [],
  "confidence": 0.0,
  "evidence_trace": [
    {
      "source_family": "",
      "key_finding": "",
      "supporting_note": ""
    }
  ]
}
```

## Quality Bar

- The result should be usable as a long-lived prompt artifact.
- The bible should make current voice generation easy.
- Bucket examples must be usable as ready-to-edit comment prototypes.
- Keep the wording crisp and operational.
