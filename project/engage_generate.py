from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Sequence

from utils.engage import (
    build_retrieval_snippets,
    extract_post_context,
    infer_blake_bucket,
    load_json,
    normalize_candidate_comments,
    pick_selected_label,
    transcribe_reel_with_whisper,
)
from utils.llm import LLMError, OpenRouterClient
from utils.monitoring import (
    MONITOR_DB_PATH,
    MonitorStore,
    QUEUE_FAILED_STATUS,
    QUEUE_PENDING_STATUS,
    QUEUE_READY_REVIEW_STATUS,
    QUEUE_TRANSCRIBING_STATUS,
    now_utc_iso,
)


def default_character_bible_path() -> str:
    repo_root = Path(__file__).resolve().parents[1]
    return str(repo_root / "blake" / "voice_builder" / "runs" / "blake_v1" / "07_character_bible.json")


def default_prompt_path(filename: str) -> str:
    repo_root = Path(__file__).resolve().parents[1]
    return str(repo_root / "blake" / "prompts" / "voice_builder" / filename)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Blake-style comment suggestions from queued reel posts.")
    parser.add_argument("--db-path", default=str(MONITOR_DB_PATH))
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--post-ids", default="", help="Optional comma-separated post_ids to regenerate.")
    parser.add_argument(
        "--force",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Include already processed posts for regeneration.",
    )
    parser.add_argument("--whisper-model", default=os.getenv("WHISPER_MODEL", "base.en"))
    parser.add_argument("--whisper-cache-dir", default=os.getenv("WHISPER_CACHE_DIR", "/tmp/whisper_models"))
    parser.add_argument("--character-bible", default=default_character_bible_path())
    parser.add_argument("--comment-prompt", default=default_prompt_path("06_comment_generation.md"))
    parser.add_argument("--critic-prompt", default=default_prompt_path("07_comment_critic.md"))
    parser.add_argument("--model", default=os.getenv("OPENROUTER_MODEL", "mistralai/mixtral-8x7b-instruct"))
    parser.add_argument("--max-tokens-generate", type=int, default=1800)
    parser.add_argument("--max-tokens-critic", type=int, default=1200)
    parser.add_argument("--retries", type=int, default=2)
    return parser.parse_args()


def llm_json_with_retry(
    client: OpenRouterClient,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
    retries: int,
) -> Dict[str, Any]:
    last_error: Exception | None = None
    current_tokens = max(300, int(max_tokens))
    for attempt in range(1, max(1, retries) + 1):
        try:
            return client.chat_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=current_tokens,
            )
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            message = str(exc).lower()
            if "truncated" in message or "length" in message:
                current_tokens = min(current_tokens + 500, 3200)
            if attempt < retries:
                time.sleep(1.2 * attempt)
    raise RuntimeError(f"LLM call failed after {retries} attempts: {last_error}") from last_error


def build_prompt_input(
    post_row: Dict[str, Any],
    transcript_text: str,
    post_context: Dict[str, Any],
    retrieval_context: Dict[str, Any],
    character_bible: Dict[str, Any],
) -> Dict[str, Any]:
    trimmed_bible = {
        "voice_positioning": character_bible.get("voice_positioning", {}),
        "who_blake_is": character_bible.get("who_blake_is", {}),
        "identity_core": character_bible.get("identity_core", {}),
        "voice_rules": character_bible.get("voice_rules", {}),
        "anti_patterns": character_bible.get("anti_patterns", []),
        "bucket_examples": character_bible.get("bucket_examples", {}),
        "generation_policy": character_bible.get("generation_policy", {}),
        "comment_generation_checklist": character_bible.get("comment_generation_checklist", []),
    }
    post_json = {
        "post_id": str(post_row.get("post_id", "")),
        "author_username": str(post_row.get("username", "")),
        "post_text": transcript_text,
        "post_caption": str(post_row.get("caption", "") or ""),
        "post_url": str(post_row.get("url", "") or ""),
        "post_timestamp": str(post_row.get("posted_at", "") or ""),
        "topic_tags": post_context.get("topic_tags", []),
        "engagement_context": {
            "tone_guess": post_context.get("tone_guess", "reflective"),
            "why_this_post_matters": post_context.get("why_this_post_matters", ""),
        },
    }
    return {
        "post_json": post_json,
        "retrieved_voice_snippets_json": retrieval_context,
        "character_bible_json": trimmed_bible,
    }


def run_generation(args: argparse.Namespace) -> int:
    token = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not token:
        raise RuntimeError("OPENROUTER_API_KEY is required.")

    comment_prompt_path = Path(args.comment_prompt)
    critic_prompt_path = Path(args.critic_prompt)
    character_bible_path = Path(args.character_bible)
    if not comment_prompt_path.exists():
        raise FileNotFoundError(f"comment prompt not found: {comment_prompt_path}")
    if not critic_prompt_path.exists():
        raise FileNotFoundError(f"critic prompt not found: {critic_prompt_path}")
    if not character_bible_path.exists():
        raise FileNotFoundError(f"character bible not found: {character_bible_path}")

    comment_system_prompt = comment_prompt_path.read_text(encoding="utf-8", errors="replace").strip()
    critic_system_prompt = critic_prompt_path.read_text(encoding="utf-8", errors="replace").strip()
    character_bible = load_json(character_bible_path)
    client = OpenRouterClient(api_key=token, model=str(args.model).strip(), app_name="Blake Engage Generator")
    store = MonitorStore(db_path=Path(args.db_path))

    try:
        post_ids = [item.strip() for item in str(args.post_ids).split(",") if item.strip()]
        statuses: Sequence[str] = (
            [QUEUE_PENDING_STATUS, QUEUE_FAILED_STATUS]
            if not args.force
            else [
                QUEUE_PENDING_STATUS,
                QUEUE_FAILED_STATUS,
                QUEUE_READY_REVIEW_STATUS,
            ]
        )
        queue_rows = store.list_queue_posts_for_generation(
            limit=max(1, int(args.limit)),
            statuses=statuses,
            post_ids=post_ids or None,
        )

        success_count = 0
        failed_count = 0
        processed_post_ids: List[str] = []
        for row in queue_rows:
            post_id = str(row.get("post_id", "")).strip()
            queue_id = int(row.get("id"))
            started_at = now_utc_iso()
            processed_post_ids.append(post_id)
            try:
                store.update_queue_status(post_id=post_id, status=QUEUE_TRANSCRIBING_STATUS)
                store.upsert_post_processing(
                    post_id=post_id,
                    queue_id=queue_id,
                    status=QUEUE_TRANSCRIBING_STATUS,
                    processing_started_at=started_at,
                )

                transcript = transcribe_reel_with_whisper(
                    post_url=str(row.get("url", "") or ""),
                    post_id=post_id,
                    whisper_model=str(args.whisper_model).strip() or "base.en",
                    model_cache_dir=str(args.whisper_cache_dir).strip() or "/tmp/whisper_models",
                )
                transcript_text = transcript["transcript_text"]
                post_context = extract_post_context(
                    caption=str(row.get("caption", "") or ""),
                    transcript=transcript_text,
                )
                bucket = infer_blake_bucket(
                    topic_tags=list(post_context.get("topic_tags") or []),
                    tone_guess=str(post_context.get("tone_guess", "reflective")),
                )
                retrieval_context = build_retrieval_snippets(character_bible=character_bible, bucket=bucket, max_items=3)
                prompt_inputs = build_prompt_input(
                    post_row=row,
                    transcript_text=transcript_text,
                    post_context=post_context,
                    retrieval_context=retrieval_context,
                    character_bible=character_bible,
                )

                gen_user_prompt = (
                    "Generate Blake-style comment suggestions for this post.\n"
                    "Return strict JSON only.\n\n"
                    f"{json.dumps(prompt_inputs, ensure_ascii=False)}"
                )
                generated = llm_json_with_retry(
                    client=client,
                    system_prompt=comment_system_prompt,
                    user_prompt=gen_user_prompt,
                    temperature=0.0,
                    max_tokens=max(600, int(args.max_tokens_generate)),
                    retries=max(1, int(args.retries)),
                )
                candidates = normalize_candidate_comments(generated)
                if not candidates:
                    raise RuntimeError("Generator returned no candidate comments.")

                critic_user_prompt = (
                    "Critique generated comments and select the best candidate.\n"
                    "Return strict JSON only.\n\n"
                    f"{json.dumps({'post_json': prompt_inputs['post_json'], 'generated_comments_json': generated, 'character_bible_json': prompt_inputs['character_bible_json']}, ensure_ascii=False)}"
                )
                critic = llm_json_with_retry(
                    client=client,
                    system_prompt=critic_system_prompt,
                    user_prompt=critic_user_prompt,
                    temperature=0.0,
                    max_tokens=max(500, int(args.max_tokens_critic)),
                    retries=max(1, int(args.retries)),
                )

                selected_label = pick_selected_label(critic_payload=critic, candidates=candidates)
                critic_scores = critic.get("scores") if isinstance(critic.get("scores"), dict) else {}
                try:
                    critic_overall = float(critic_scores.get("overall")) if critic_scores else None
                except (TypeError, ValueError):
                    critic_overall = None

                selected_suggestion_id = store.replace_comment_suggestions(
                    post_id=post_id,
                    suggestions=candidates,
                    selected_label=selected_label,
                    critic_json=json.dumps(critic, ensure_ascii=False),
                    critic_score=critic_overall,
                )

                store.upsert_post_processing(
                    post_id=post_id,
                    queue_id=queue_id,
                    status=QUEUE_READY_REVIEW_STATUS,
                    transcript_text=transcript_text,
                    transcript_source=transcript.get("transcript_source", "whisper_local"),
                    transcript_model=transcript.get("transcript_model", str(args.whisper_model)),
                    post_context_json=json.dumps(post_context, ensure_ascii=False),
                    generation_json=json.dumps(generated, ensure_ascii=False),
                    critic_json=json.dumps(critic, ensure_ascii=False),
                    selected_suggestion_id=selected_suggestion_id,
                    error_message="",
                    processing_started_at=started_at,
                    processing_finished_at=now_utc_iso(),
                )
                store.update_queue_status(post_id=post_id, status=QUEUE_READY_REVIEW_STATUS)
                success_count += 1
                print(f"[engage_generate] ready_for_review post_id={post_id} username={row.get('username')}")
            except Exception as exc:  # noqa: BLE001
                failed_count += 1
                error_text = str(exc)
                store.upsert_post_processing(
                    post_id=post_id,
                    queue_id=queue_id,
                    status=QUEUE_FAILED_STATUS,
                    error_message=error_text,
                    processing_started_at=started_at,
                    processing_finished_at=now_utc_iso(),
                )
                store.update_queue_status(post_id=post_id, status=QUEUE_FAILED_STATUS)
                print(f"[engage_generate] generation_failed post_id={post_id} error={error_text}")

        print(
            "[engage_generate] completed "
            f"processed={len(processed_post_ids)} success={success_count} failed={failed_count}"
        )
        return 0 if failed_count == 0 else 1
    finally:
        store.close()


def main() -> int:
    args = parse_args()
    return run_generation(args)


if __name__ == "__main__":
    raise SystemExit(main())

