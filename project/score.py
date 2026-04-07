from __future__ import annotations

import argparse
import json
import os
import statistics
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

from utils.llm import LLMError, OpenRouterClient, coerce_score

SYSTEM_PROMPT = """
You are an analyst scoring Instagram accounts for a mental-health influencer pipeline.
Return strict JSON only.

Definitions:
- Mental health content = lived experience, therapy, evidence-based education, coping guidance.
- Not mental-health primary = generic motivation quotes, broad lifestyle/fitness pages, brand/product-heavy pages.

Scoring rubric (0 to 1):
- relevance_score: how clearly the account is primarily mental-health focused.
- content_depth_score: how insightful/specific/original the captions are vs generic advice.
- audience_intent_score: how strongly comments show help-seeking, emotional sharing, trust.

Output keys exactly:
{
  "relevance_score": number,
  "content_depth_score": number,
  "audience_intent_score": number,
  "relevance_reason": "short reason",
  "content_depth_reason": "short reason",
  "audience_intent_reason": "short reason",
  "selected_comment_examples": ["comment 1", "comment 2"]
}
""".strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score enriched influencer accounts")
    parser.add_argument("--input", default="data/enriched.json")
    parser.add_argument("--output", default="data/scored.csv")
    parser.add_argument("--model", default=os.getenv("OPENROUTER_MODEL", "mistralai/mixtral-8x7b-instruct"))
    parser.add_argument("--max-captions", type=int, default=12)
    parser.add_argument("--max-comments", type=int, default=20)
    parser.add_argument("--min-captions", type=int, default=2)
    parser.add_argument("--min-comments", type=int, default=4)
    return parser.parse_args()


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def tier_from_followers(followers: int) -> str:
    if followers >= 1_500_000:
        return "major"
    if followers >= 500_000:
        return "macro"
    if followers >= 50_000:
        return "mid"
    if followers >= 5_000:
        return "micro"
    return "nano"


def text_confidence_score(bio: str, captions: List[str]) -> float:
    bio_len_factor = clamp01(len((bio or "").strip()) / 100.0)
    caption_count_factor = clamp01(len(captions) / 8.0)
    avg_caption_len = statistics.mean([len(c) for c in captions]) if captions else 0.0
    caption_len_factor = clamp01(avg_caption_len / 220.0)
    return clamp01(
        (0.25 * bio_len_factor)
        + (0.40 * caption_count_factor)
        + (0.35 * caption_len_factor)
    )


def comment_confidence_score(comments: List[str]) -> float:
    return clamp01(len(comments) / 20.0)


def post_confidence_score(posts: List[Dict[str, Any]]) -> float:
    return clamp01(len(posts) / 20.0)


def confidence_grade(confidence: float) -> str:
    if confidence >= 0.75:
        return "high"
    if confidence >= 0.45:
        return "medium"
    return "low"


def load_accounts(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"input file not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("accounts"), list):
        return payload["accounts"]
    raise ValueError("enriched input must be a list or an object with an 'accounts' list")


def collect_captions(posts: List[Dict[str, Any]], max_items: int) -> List[str]:
    captions: List[str] = []
    for post in posts:
        text = str(post.get("caption", "") or "").strip()
        if text:
            captions.append(text)
        if len(captions) >= max_items:
            break
    return captions


def collect_comments(comments: List[Dict[str, Any]], max_items: int) -> List[str]:
    texts: List[str] = []
    for comment in comments:
        text = str(comment.get("text", "") or "").strip()
        if text:
            texts.append(text)
        if len(texts) >= max_items:
            break
    return texts


def topic_signal_score(bio: str, captions: List[str], comments: List[str]) -> float:
    content_blob = (f"{bio}\n" + "\n".join(captions)).lower()
    comment_blob = "\n".join(comments).lower()
    combined_blob = f"{content_blob}\n{comment_blob}"

    mental_terms = [
        "mental health",
        "anxiety",
        "depression",
        "therapy",
        "therapist",
        "trauma",
        "panic",
        "ocd",
        "ptsd",
        "healing",
        "coping",
        "nervous system",
    ]
    off_topic_terms = [
        "motivation",
        "hustle",
        "success",
        "entrepreneur",
        "fitness challenge",
        "discount",
        "shop now",
        "link in bio",
    ]
    support_terms = [
        "this helped",
        "i needed this",
        "thank you",
        "i am struggling",
        "i struggle",
        "this is me",
        "felt seen",
        "needed to hear this",
    ]

    mental_hits = sum(1 for term in mental_terms if term in combined_blob)
    off_topic_hits = sum(1 for term in off_topic_terms if term in combined_blob)
    support_hits = sum(1 for term in support_terms if term in comment_blob)

    score = (mental_hits / 8.0) + (support_hits / 6.0) - (off_topic_hits / 10.0)
    return clamp01(score)


def adjusted_relevance_score(
    relevance_text_score: float,
    topic_signal: float,
    audience_intent: float,
    text_confidence: float,
) -> float:
    if text_confidence >= 0.55:
        return clamp01((0.75 * relevance_text_score) + (0.25 * topic_signal))
    if text_confidence >= 0.30:
        return clamp01(
            (0.60 * relevance_text_score)
            + (0.25 * topic_signal)
            + (0.15 * audience_intent)
        )
    return clamp01(
        (0.40 * relevance_text_score) + (0.35 * topic_signal) + (0.25 * audience_intent)
    )


def dynamic_weights(text_confidence: float, comment_confidence: float) -> Dict[str, float]:
    weights = {
        "relevance": 0.35,
        "audience_intent": 0.30,
        "engagement_quality": 0.20,
        "content_depth": 0.15,
    }

    # If text is sparse, rely more on behavior.
    if text_confidence < 0.40:
        shortage = (0.40 - text_confidence) / 0.40
        weights["relevance"] -= 0.10 * shortage
        weights["content_depth"] -= 0.10 * shortage
        weights["audience_intent"] += 0.12 * shortage
        weights["engagement_quality"] += 0.08 * shortage

    # If comments are sparse, reduce audience-intent dependence.
    if comment_confidence < 0.30:
        shortage = (0.30 - comment_confidence) / 0.30
        weights["audience_intent"] -= 0.10 * shortage
        weights["engagement_quality"] += 0.05 * shortage
        weights["relevance"] += 0.03 * shortage
        weights["content_depth"] += 0.02 * shortage

    for key in list(weights.keys()):
        weights[key] = max(0.0, weights[key])

    total = sum(weights.values()) or 1.0
    return {key: value / total for key, value in weights.items()}


def engagement_quality_score(
    followers: int,
    following: int,
    posts: List[Dict[str, Any]],
    avg_likes: float,
    avg_comments: float,
) -> Tuple[float, float]:
    if followers <= 0:
        return 0.0, 0.0

    rates: List[float] = []
    for post in posts:
        likes = float(post.get("likes", 0) or 0)
        comments = float(post.get("comments", 0) or 0)
        rates.append((likes + comments) / followers)

    if not rates:
        fallback_rate = (avg_likes + avg_comments) / followers if followers > 0 else 0.0
        if fallback_rate > 0:
            rates = [fallback_rate]

    if not rates:
        return 0.0, 0.0

    med_rate = statistics.median(rates)
    dispersion = statistics.pstdev(rates) if len(rates) > 1 else 0.0

    rate_norm = clamp01(med_rate / 0.06)  # 6% median engagement ~= strong baseline
    consistency = clamp01(1.0 - (dispersion / (med_rate + 1e-6)))

    penalty = 0.0
    if following > 0:
        ratio = followers / max(following, 1)
        if ratio < 0.3:
            penalty = 0.15
        elif ratio < 0.6:
            penalty = 0.08

    score = clamp01((0.7 * rate_norm) + (0.3 * consistency) - penalty)
    return score, med_rate


def heuristic_scores(bio: str, captions: List[str], comments: List[str]) -> Dict[str, Any]:
    text_blob = f"{bio}\n" + "\n".join(captions)
    lower_blob = text_blob.lower()

    relevance_terms = [
        "mental health",
        "anxiety",
        "depression",
        "therapy",
        "trauma",
        "panic",
        "ocd",
        "ptsd",
        "therapist",
        "healing",
    ]
    generic_terms = ["motivation", "hustle", "mindset", "success", "quote"]

    rel_hits = sum(1 for term in relevance_terms if term in lower_blob)
    generic_hits = sum(1 for term in generic_terms if term in lower_blob)
    relevance = clamp01((rel_hits / 6.0) - (generic_hits * 0.05))

    avg_caption_len = statistics.mean([len(c) for c in captions]) if captions else 0.0
    specificity_markers = [":", "because", "example", "steps", "practice", "session", "client"]
    specific_hits = sum(1 for marker in specificity_markers if marker in lower_blob)
    content_depth = clamp01((avg_caption_len / 500.0) + (specific_hits / 8.0))

    comment_blob = "\n".join(comments).lower()
    intent_terms = [
        "i needed this",
        "thank you",
        "this helped",
        "i struggle",
        "i am struggling",
        "help",
        "panic",
        "anxious",
        "depressed",
        "therapy",
    ]
    intent_hits = sum(1 for term in intent_terms if term in comment_blob)
    audience_intent = clamp01(intent_hits / 8.0)

    examples = comments[:2]
    return {
        "relevance_score": relevance,
        "content_depth_score": content_depth,
        "audience_intent_score": audience_intent,
        "relevance_reason": "heuristic fallback based on bio/caption topical language",
        "content_depth_reason": "heuristic fallback based on caption specificity and length",
        "audience_intent_reason": "heuristic fallback from comment help-seeking language",
        "selected_comment_examples": examples,
    }


def llm_scores(
    client: OpenRouterClient,
    bio: str,
    captions: List[str],
    comments: List[str],
) -> Dict[str, Any]:
    caption_block = "\n".join(f"- {caption[:400]}" for caption in captions)
    comment_block = "\n".join(f"- {comment[:300]}" for comment in comments)

    user_prompt = (
        "Evaluate this account and score it.\n\n"
        f"Bio:\n{bio[:1200] or '[empty]'}\n\n"
        f"Caption samples:\n{caption_block or '[none]'}\n\n"
        f"Comment samples:\n{comment_block or '[none]'}"
    )

    response = client.chat_json(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.1,
        max_tokens=600,
    )

    return {
        "relevance_score": coerce_score(response.get("relevance_score")),
        "content_depth_score": coerce_score(response.get("content_depth_score")),
        "audience_intent_score": coerce_score(response.get("audience_intent_score")),
        "relevance_reason": str(response.get("relevance_reason", "")).strip(),
        "content_depth_reason": str(response.get("content_depth_reason", "")).strip(),
        "audience_intent_reason": str(response.get("audience_intent_reason", "")).strip(),
        "selected_comment_examples": [
            str(item).strip()
            for item in (response.get("selected_comment_examples") or [])
            if str(item).strip()
        ][:2],
    }


def reason_or_default(value: str, fallback: str) -> str:
    value = value.strip()
    return value if value else fallback


def build_why(
    relevance: float,
    audience_intent: float,
    content_depth: float,
    engagement_quality: float,
    median_er: float,
    post_count: int,
    confidence: float,
    confidence_label: str,
) -> str:
    return (
        f"Relevance {relevance:.2f}, audience intent {audience_intent:.2f}, "
        f"content depth {content_depth:.2f}, engagement quality {engagement_quality:.2f}. "
        f"Median engagement rate {median_er:.2%} across {post_count} posts. "
        f"Confidence {confidence_label} ({confidence:.2f})."
    )


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)

    accounts = load_accounts(input_path)
    print(f"[score] loaded {len(accounts)} accounts from {input_path}")

    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    llm_client = OpenRouterClient(openrouter_key, model=args.model) if openrouter_key else None

    rows: List[Dict[str, Any]] = []
    for account in accounts:
        username = str(account.get("username", "") or "").strip().lower()
        if not username:
            continue

        profile = account.get("profile") or {}
        posts = account.get("posts") or []
        comments = account.get("comments") or []

        followers = int(profile.get("followers", 0) or 0)
        following = int(profile.get("following", 0) or 0)
        avg_likes = float(profile.get("avg_likes", 0.0) or 0.0)
        avg_comments = float(profile.get("avg_comments", 0.0) or 0.0)
        bio = str(profile.get("bio", "") or "")

        caption_samples = collect_captions(posts, max_items=args.max_captions)
        comment_samples = collect_comments(comments, max_items=args.max_comments)

        if llm_client and (caption_samples or bio):
            try:
                llm = llm_scores(llm_client, bio=bio, captions=caption_samples, comments=comment_samples)
            except (LLMError, Exception) as exc:
                print(f"[score] llm scoring failed for {username}: {exc}")
                llm = heuristic_scores(bio, caption_samples, comment_samples)
        else:
            llm = heuristic_scores(bio, caption_samples, comment_samples)

        relevance_text = coerce_score(llm.get("relevance_score"))
        content_depth = coerce_score(llm.get("content_depth_score"))
        audience_intent = coerce_score(llm.get("audience_intent_score"))

        topic_signal = topic_signal_score(bio=bio, captions=caption_samples, comments=comment_samples)

        text_conf = text_confidence_score(bio=bio, captions=caption_samples)
        comment_conf = comment_confidence_score(comment_samples)
        post_conf = post_confidence_score(posts)
        confidence = clamp01((0.45 * text_conf) + (0.35 * comment_conf) + (0.20 * post_conf))
        confidence_label = confidence_grade(confidence)

        relevance = adjusted_relevance_score(
            relevance_text_score=relevance_text,
            topic_signal=topic_signal,
            audience_intent=audience_intent,
            text_confidence=text_conf,
        )

        engagement_quality, median_er = engagement_quality_score(
            followers=followers,
            following=following,
            posts=posts,
            avg_likes=avg_likes,
            avg_comments=avg_comments,
        )

        weights = dynamic_weights(text_confidence=text_conf, comment_confidence=comment_conf)
        final_score = (
            (weights["relevance"] * relevance)
            + (weights["audience_intent"] * audience_intent)
            + (weights["engagement_quality"] * engagement_quality)
            + (weights["content_depth"] * content_depth)
        )

        needs_review = (
            confidence_label == "low"
            and (
                final_score >= 0.55
                or (engagement_quality >= 0.55 and audience_intent >= 0.45)
            )
        )
        review_reason = (
            "Low data confidence, but behavioral signals are strong; manual review recommended."
            if needs_review
            else ""
        )

        selected_examples = [
            str(example).strip()
            for example in (llm.get("selected_comment_examples") or [])
            if str(example).strip()
        ][:2]
        if len(selected_examples) < 2:
            for comment in comment_samples:
                if comment not in selected_examples:
                    selected_examples.append(comment)
                if len(selected_examples) == 2:
                    break
        while len(selected_examples) < 2:
            selected_examples.append("")

        row = {
            "username": username,
            "followers": followers,
            "following": following,
            "tier": tier_from_followers(followers),
            "relevance_text_score": round(relevance_text, 4),
            "relevance_score": round(relevance, 4),
            "audience_intent_score": round(audience_intent, 4),
            "content_depth_score": round(content_depth, 4),
            "engagement_quality_score": round(engagement_quality, 4),
            "topic_signal_score": round(topic_signal, 4),
            "final_score": round(final_score, 4),
            "weight_relevance": round(weights["relevance"], 4),
            "weight_audience_intent": round(weights["audience_intent"], 4),
            "weight_engagement_quality": round(weights["engagement_quality"], 4),
            "weight_content_depth": round(weights["content_depth"], 4),
            "text_confidence": round(text_conf, 4),
            "comment_confidence": round(comment_conf, 4),
            "post_confidence": round(post_conf, 4),
            "confidence_score": round(confidence, 4),
            "confidence_grade": confidence_label,
            "needs_review": needs_review,
            "review_reason": review_reason,
            "relevance_reason": reason_or_default(
                str(llm.get("relevance_reason", "")),
                "Based on account bio and caption focus.",
            ),
            "audience_intent_reason": reason_or_default(
                str(llm.get("audience_intent_reason", "")),
                "Based on help-seeking or emotionally engaged comments.",
            ),
            "content_depth_reason": reason_or_default(
                str(llm.get("content_depth_reason", "")),
                "Based on caption specificity and practical depth.",
            ),
            "why_selected": build_why(
                relevance=relevance,
                audience_intent=audience_intent,
                content_depth=content_depth,
                engagement_quality=engagement_quality,
                median_er=median_er,
                post_count=len(posts),
                confidence=confidence,
                confidence_label=confidence_label,
            ),
            "sample_caption": caption_samples[0][:350] if caption_samples else "",
            "sample_comment_1": selected_examples[0][:280],
            "sample_comment_2": selected_examples[1][:280],
            "post_count": len(posts),
            "comment_count": len(comments),
            "median_engagement_rate": round(median_er, 6),
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(by="final_score", ascending=False).reset_index(drop=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"[score] wrote {len(df)} scored accounts -> {output_path}")


if __name__ == "__main__":
    main()
