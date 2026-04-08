# Prompt: YouTube Voice Primitives

## Purpose
Extract Blake's conversational behavior from a single transcript.

## Use Case
Run once per transcript. This is the most important extraction step for how he thinks out loud.

## Input

```text
{{youtube_transcript_json}}
```

The input JSON should include:

- `video_id`
- `title`
- `url`
- `published_at`
- `channel`
- `transcript_text`

## Instructions

Focus on behavioral voice patterns, not topic summary.

Extract:

- sentence rhythm
- interruption patterns
- restarts and self-corrections
- bridge words such as "it's like"
- how he opens a thought
- how he lands a thought
- how he handles uncertainty
- what he uses as anchors
- how vulnerability shows up
- what phrases feel signature-like

Temporal rule:

- If the transcript is from 2025-2026, treat it as a stronger signal for current voice than older content.
- If the transcript is older, keep it as historical evidence, not default style.

Synthesis context:

- podcasts / transcripts 45%
- substack + personal site 30%
- instagram captions 20%
- external articles 5% facts only

## Output Rules

Return strict JSON only. No markdown, no explanation.

## Output Schema

```json
{
  "prompt_version": "voice_builder.youtube.v1",
  "source_type": "youtube_transcript",
  "metadata": {
    "video_id": "",
    "title": "",
    "url": "",
    "published_at": "",
    "channel": ""
  },
  "transcript_read": {
    "word_count": 0,
    "speaker_mix_notes": "",
    "audio_noise_notes": ""
  },
  "voice_primitives": [
    {
      "primitive_name": "",
      "description": "",
      "evidence_quotes": [
        ""
      ],
      "why_it_matters": "",
      "confidence": 0.0
    }
  ],
  "rhythm_analysis": {
    "opening_moves": [],
    "bridge_words": [],
    "self_corrections": [],
    "sentence_length_profile": "",
    "closing_moves": []
  },
  "thought_process_patterns": [
    {
      "pattern_name": "",
      "description": "",
      "evidence_quotes": [
        ""
      ],
      "confidence": 0.0
    }
  ],
  "vulnerability_signals": [
    {
      "signal": "",
      "evidence_quotes": [
        ""
      ],
      "interpretation": ""
    }
  ],
  "signature_language": {
    "repeated_words": [],
    "repeated_phrases": [],
    "metaphor_anchors": [],
    "emotional_register": ""
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

- Quote exact wording when possible.
- Prefer repeated patterns over one-off lines.
- Keep the analysis grounded in the transcript, not the episode title.

