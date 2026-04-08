from __future__ import annotations

import glob
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

TOPIC_KEYWORDS: Dict[str, Sequence[str]] = {
    "depression": ("depression", "depressed", "hopeless", "suicid", "dark"),
    "anxiety": ("anxiety", "anxious", "panic", "nervous system", "overwhelm"),
    "healing": ("healing", "recovery", "therapy", "trauma", "grief", "inner work"),
    "self_worth": ("enough", "worth", "validation", "self-esteem", "self worth"),
    "burnout": ("burnout", "exhausted", "drained", "overstimulated", "tired"),
    "purpose": ("purpose", "mission", "impact", "service", "meaning"),
    "relationships": ("relationship", "partner", "attachment", "conflict"),
}

TONE_KEYWORDS: Dict[str, Sequence[str]] = {
    "vulnerable": ("i struggled", "i was lost", "i'm scared", "i've been there", "hard season"),
    "reflective": ("i learned", "for me", "looking back", "what changed"),
    "educational": ("tips", "steps", "how to", "framework", "here's"),
    "encouraging": ("you got this", "keep going", "you are not alone", "one day at a time"),
}

WHISPER_MODEL_CACHE: Dict[Tuple[str, str], Any] = {}


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def post_id_to_embed_url(url: str) -> str:
    cleaned = str(url or "").strip()
    reel_match = re.search(r"/reel/([^/?#]+)/?", cleaned)
    if reel_match:
        code = reel_match.group(1).strip()
        return f"https://www.instagram.com/reel/{code}/embed"
    post_match = re.search(r"/p/([^/?#]+)/?", cleaned)
    if post_match:
        code = post_match.group(1).strip()
        return f"https://www.instagram.com/p/{code}/embed"
    return ""


def extract_post_context(caption: str, transcript: str) -> Dict[str, Any]:
    combined = f"{caption or ''}\n{transcript or ''}".strip().lower()
    topic_tags: List[str] = []
    for topic, words in TOPIC_KEYWORDS.items():
        if any(word in combined for word in words):
            topic_tags.append(topic)
    if not topic_tags:
        topic_tags.append("general_mental_health")

    tone_scores: Dict[str, int] = {}
    for tone, words in TONE_KEYWORDS.items():
        tone_scores[tone] = sum(1 for word in words if word in combined)
    tone_guess = max(tone_scores.items(), key=lambda item: item[1])[0] if tone_scores else "reflective"
    if tone_scores.get(tone_guess, 0) == 0:
        tone_guess = "reflective"

    summary_parts = [
        f"Topics: {', '.join(topic_tags)}.",
        f"Tone appears {tone_guess}.",
    ]
    if transcript.strip():
        summary_parts.append("Transcript available and included in grounding.")
    else:
        summary_parts.append("No transcript available; caption-only grounding.")

    return {
        "topic_tags": topic_tags,
        "tone_guess": tone_guess,
        "why_this_post_matters": " ".join(summary_parts),
    }


def infer_blake_bucket(topic_tags: Sequence[str], tone_guess: str) -> str:
    tags = {str(item).strip().lower() for item in topic_tags}
    tone = str(tone_guess or "").strip().lower()

    if tags.intersection({"depression", "anxiety", "burnout", "healing"}):
        return "crisis_and_identity_reset"
    if tags.intersection({"self_worth"}):
        return "enough_era"
    if tags.intersection({"purpose"}):
        return "origin_and_revolution"
    if tags.intersection({"relationships"}):
        return "enough_era"
    if tone in {"vulnerable", "reflective"}:
        return "enough_era"
    return "scale_and_public_impact"


def build_retrieval_snippets(character_bible: Dict[str, Any], bucket: str, max_items: int = 3) -> Dict[str, Any]:
    bucket_examples = character_bible.get("bucket_examples") or {}
    examples = bucket_examples.get(bucket) if isinstance(bucket_examples, dict) else []
    snippets: List[Dict[str, Any]] = []
    for item in list(examples or [])[: max(1, int(max_items))]:
        if isinstance(item, dict):
            snippets.append(
                {
                    "text": str(item.get("example", "")).strip(),
                    "why_it_works": str(item.get("why_it_works", "")).strip(),
                    "context_fit": str(item.get("context_fit", "")).strip(),
                }
            )
        else:
            snippets.append({"text": str(item).strip(), "why_it_works": "", "context_fit": ""})

    return {
        "matched_snippets": snippets,
        "source_family": "blake_character_bible",
        "era_signal": "era_c_enough_current",
        "relevance_reason": f"Matched to bucket '{bucket}' from post topics/tone.",
    }


def _extract_audio_with_ytdlp(post_url: str, post_id: str, temp_dir: Path) -> Path:
    safe_post_id = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(post_id))[:120] or "post"
    out_template = temp_dir / f"engage_{safe_post_id}.%(ext)s"
    command = [
        "yt-dlp",
        "--no-playlist",
        "-f",
        "bestaudio",
        "-o",
        str(out_template),
        str(post_url).strip(),
    ]
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"yt-dlp failed ({proc.returncode}): {(proc.stderr or proc.stdout or '').strip()[:400]}")

    candidates = sorted(glob.glob(str(temp_dir / f"engage_{safe_post_id}.*")))
    if not candidates:
        raise RuntimeError("yt-dlp succeeded but no audio file was found.")
    return Path(candidates[0])


def transcribe_reel_with_whisper(
    post_url: str,
    post_id: str,
    whisper_model: str = "base.en",
    model_cache_dir: str = "/tmp/whisper_models",
    temp_dir: str = "/tmp",
) -> Dict[str, str]:
    temp_dir_path = Path(temp_dir)
    temp_dir_path.mkdir(parents=True, exist_ok=True)
    audio_file = _extract_audio_with_ytdlp(post_url=post_url, post_id=post_id, temp_dir=temp_dir_path)

    try:
        import whisper  # type: ignore
    except Exception as exc:  # pragma: no cover - environment-dependent import branch
        raise RuntimeError("openai-whisper is not installed in the current Python environment.") from exc

    model_key = (str(whisper_model).strip() or "base.en", str(model_cache_dir))
    model = WHISPER_MODEL_CACHE.get(model_key)
    if model is None:
        model = whisper.load_model(model_key[0], download_root=model_key[1])
        WHISPER_MODEL_CACHE[model_key] = model

    result = model.transcribe(str(audio_file))
    transcript = str(result.get("text", "") or "").strip()
    if not transcript:
        raise RuntimeError("Whisper completed but returned an empty transcript.")
    return {
        "transcript_text": transcript,
        "transcript_source": "whisper_local",
        "transcript_model": model_key[0],
    }


def normalize_candidate_comments(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    rows = payload.get("candidate_comments") or []
    out: List[Dict[str, str]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        comment = str(raw.get("comment", "") or "").strip()
        if not comment:
            continue
        out.append(
            {
                "label": str(raw.get("label", "") or "candidate").strip() or "candidate",
                "comment": comment,
                "why_it_works": str(raw.get("why_it_works", "") or "").strip(),
                "risk_level": str(raw.get("risk_level", "") or "").strip() or "low",
            }
        )
    return out


def pick_selected_label(critic_payload: Dict[str, Any], candidates: Sequence[Dict[str, str]]) -> str:
    selected = str(critic_payload.get("selected_comment", "") or "").strip()
    if not selected:
        return str(candidates[0]["label"]) if candidates else ""

    for candidate in candidates:
        if selected == candidate.get("label"):
            return str(candidate["label"])
    for candidate in candidates:
        if selected == candidate.get("comment"):
            return str(candidate["label"])
    return str(candidates[0]["label"]) if candidates else ""

