from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.apify_client import ApifyClient, ApifyError, chunked, extract_username, normalize_username


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enrich influencer handles with profiles/posts/comments")
    parser.add_argument("--input", default="data/raw_handles.csv")
    parser.add_argument("--output", default="data/enriched.json")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--delay-seconds", type=float, default=2.5)
    parser.add_argument("--wait-seconds", type=int, default=240)
    parser.add_argument("--min-followers-for-posts", type=int, default=5000)
    parser.add_argument("--max-post-accounts", type=int, default=150)
    parser.add_argument("--max-comment-accounts", type=int, default=80)
    parser.add_argument("--posts-per-account", type=int, default=40)
    parser.add_argument("--comments-per-account", type=int, default=120)
    parser.add_argument("--comments-per-post", type=int, default=8)
    return parser.parse_args()


def read_handles(path: Path) -> List[str]:
    if not path.exists():
        raise FileNotFoundError(f"input file not found: {path}")

    usernames: List[str] = []
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            username = normalize_username(row.get("username", ""))
            if username:
                usernames.append(username)

    # Preserve order while deduplicating.
    return list(dict.fromkeys(usernames))


def first_present(record: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
    for key in keys:
        value = record.get(key)
        if value is not None and value != "":
            return value
    return default


def to_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().lower().replace(",", "")
    if not text:
        return None

    multiplier = 1.0
    if text.endswith("k"):
        multiplier = 1_000.0
        text = text[:-1]
    elif text.endswith("m"):
        multiplier = 1_000_000.0
        text = text[:-1]

    try:
        return float(text) * multiplier
    except ValueError:
        return None


def to_int(value: Any, default: int = 0) -> int:
    number = to_number(value)
    return int(number) if number is not None else default


def parse_profile_record(record: Dict[str, Any]) -> Dict[str, Any]:
    profile = record.get("profile") if isinstance(record.get("profile"), dict) else record

    return {
        "bio": str(
            first_present(
                profile,
                ["bio", "biography", "description", "about", "fullName"],
                default="",
            )
            or ""
        ),
        "followers": to_int(
            first_present(
                profile,
                ["followers", "followersCount", "followerCount", "edge_followed_by"],
            ),
            default=0,
        ),
        "following": to_int(
            first_present(profile, ["following", "followingCount", "followsCount"]),
            default=0,
        ),
        "avg_likes": float(
            to_number(first_present(profile, ["avgLikes", "averageLikes", "avg_likes"]))
            or 0.0
        ),
        "avg_comments": float(
            to_number(
                first_present(profile, ["avgComments", "averageComments", "avg_comments"])
            )
            or 0.0
        ),
    }


def parse_post_record(record: Dict[str, Any], fallback_username: str = "") -> Optional[Tuple[str, Dict[str, Any]]]:
    username = extract_username(record) or fallback_username
    username = normalize_username(username)
    if not username:
        return None

    caption = str(
        first_present(record, ["caption", "text", "description", "title"], default="") or ""
    )
    likes = to_int(first_present(record, ["likesCount", "likes", "likeCount"]))
    comments_count = to_int(first_present(record, ["commentsCount", "comments", "commentCount"]))

    embedded_comments: List[Dict[str, Any]] = []
    for key in ["comments", "topComments", "latestComments", "recentComments"]:
        raw_value = record.get(key)
        if isinstance(raw_value, list):
            embedded_comments = [item for item in raw_value if isinstance(item, dict)]
            if embedded_comments:
                break

    parsed = {
        "post_id": str(
            first_present(record, ["id", "shortCode", "shortcode", "postId"], default="")
            or ""
        ),
        "url": str(first_present(record, ["url", "postUrl", "displayUrl"], default="") or ""),
        "caption": caption,
        "likes": likes,
        "comments": comments_count,
        "embedded_comments": embedded_comments,
        "timestamp": str(
            first_present(record, ["timestamp", "createdAt", "takenAtTimestamp"], default="")
            or ""
        ),
    }
    return username, parsed


def parse_comment_record(
    record: Dict[str, Any],
    fallback_username: str = "",
    fallback_post_id: str = "",
) -> Optional[Tuple[str, Dict[str, Any]]]:
    owner = normalize_username(
        fallback_username
        or extract_username(record.get("post") if isinstance(record.get("post"), dict) else {})
        or extract_username(record)
    )
    text = str(first_present(record, ["text", "comment", "content", "body"], default="") or "").strip()

    if not owner or not text:
        return None

    parsed = {
        "post_id": str(first_present(record, ["postId", "mediaId", "id"], default=fallback_post_id) or ""),
        "text": text,
        "likes": to_int(first_present(record, ["likesCount", "likes", "likeCount"]), default=0),
    }
    return owner, parsed


def median_engagement_rate(posts: List[Dict[str, Any]], followers: int) -> float:
    if followers <= 0 or not posts:
        return 0.0
    rates: List[float] = []
    for post in posts:
        likes = to_int(post.get("likes"), default=0)
        comments = to_int(post.get("comments"), default=0)
        rates.append((likes + comments) / followers)
    return statistics.median(rates) if rates else 0.0


def fetch_profiles(
    client: ApifyClient,
    actor_id: str,
    usernames: List[str],
    batch_size: int,
    delay_seconds: float,
    wait_seconds: int,
) -> Dict[str, Dict[str, Any]]:
    profiles: Dict[str, Dict[str, Any]] = {}

    for batch in chunked(usernames, batch_size):
        actor_input = {
            "usernames": batch,
            "resultsLimit": len(batch),
        }
        try:
            items = client.run_actor_and_fetch_items(
                actor_id=actor_id,
                actor_input=actor_input,
                wait_for_finish_seconds=wait_seconds,
                dataset_limit=max(100, len(batch) * 3),
            )
        except ApifyError as exc:
            print(f"[enrich] profile batch failed ({len(batch)} handles): {exc}")
            time.sleep(max(0.0, delay_seconds))
            continue

        for item in items:
            username = normalize_username(extract_username(item))
            if not username:
                continue
            parsed = parse_profile_record(item)
            existing = profiles.get(username, {})
            profiles[username] = {
                "bio": parsed["bio"] or existing.get("bio", ""),
                "followers": max(parsed["followers"], int(existing.get("followers", 0) or 0)),
                "following": parsed["following"] or int(existing.get("following", 0) or 0),
                "avg_likes": parsed["avg_likes"] or float(existing.get("avg_likes", 0.0) or 0.0),
                "avg_comments": parsed["avg_comments"]
                or float(existing.get("avg_comments", 0.0) or 0.0),
            }

        time.sleep(max(0.0, delay_seconds))

    return profiles


def fetch_posts(
    client: ApifyClient,
    actor_id: str,
    usernames: List[str],
    batch_size: int,
    delay_seconds: float,
    wait_seconds: int,
    posts_per_account: int,
) -> Dict[str, List[Dict[str, Any]]]:
    posts_by_user: Dict[str, List[Dict[str, Any]]] = {username: [] for username in usernames}

    for batch in chunked(usernames, batch_size):
        actor_input = {
            "username": batch,
            "resultsLimit": posts_per_account,
            "dataDetailLevel": "detailedData",
        }

        try:
            items = client.run_actor_and_fetch_items(
                actor_id=actor_id,
                actor_input=actor_input,
                wait_for_finish_seconds=wait_seconds,
                dataset_limit=max(200, len(batch) * posts_per_account),
            )
        except ApifyError as exc:
            print(f"[enrich] post batch failed ({len(batch)} handles): {exc}")
            time.sleep(max(0.0, delay_seconds))
            continue

        for item in items:
            owner = normalize_username(extract_username(item))
            nested_posts = item.get("posts") if isinstance(item, dict) else None
            if isinstance(nested_posts, list):
                for raw_post in nested_posts:
                    if not isinstance(raw_post, dict):
                        continue
                    parsed = parse_post_record(raw_post, fallback_username=owner)
                    if not parsed:
                        continue
                    username, post = parsed
                    posts_by_user.setdefault(username, []).append(post)
                continue

            if isinstance(item, dict):
                parsed = parse_post_record(item, fallback_username=owner)
                if parsed:
                    username, post = parsed
                    posts_by_user.setdefault(username, []).append(post)

        time.sleep(max(0.0, delay_seconds))

    for username in list(posts_by_user.keys()):
        posts_by_user[username] = posts_by_user[username][:posts_per_account]

    return posts_by_user


def extract_comments_from_posts(posts_by_user: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
    # This extracts comments only when the post actor embedded comment text payloads.
    extracted: Dict[str, List[Dict[str, Any]]] = {}

    for username, posts in posts_by_user.items():
        for post in posts:
            raw_comments = post.get("embedded_comments")
            if not isinstance(raw_comments, list):
                continue
            for raw_comment in raw_comments:
                if not isinstance(raw_comment, dict):
                    continue
                parsed = parse_comment_record(
                    raw_comment,
                    fallback_username=username,
                    fallback_post_id=str(post.get("post_id", "")),
                )
                if not parsed:
                    continue
                owner, comment = parsed
                extracted.setdefault(owner, []).append(comment)

    return extracted


def fetch_comments(
    client: ApifyClient,
    actor_id: str,
    usernames: List[str],
    batch_size: int,
    delay_seconds: float,
    wait_seconds: int,
    comments_per_account: int,
    comments_per_post: int,
) -> Dict[str, List[Dict[str, Any]]]:
    comments_by_user: Dict[str, List[Dict[str, Any]]] = {username: [] for username in usernames}

    for batch in chunked(usernames, batch_size):
        actor_input = {
            "username": batch,
            "resultsLimit": comments_per_account,
            "maxCommentsPerPost": comments_per_post,
            "dataDetailLevel": "detailedData",
        }

        try:
            items = client.run_actor_and_fetch_items(
                actor_id=actor_id,
                actor_input=actor_input,
                wait_for_finish_seconds=wait_seconds,
                dataset_limit=max(200, len(batch) * comments_per_account),
            )
        except ApifyError as exc:
            print(f"[enrich] comment batch failed ({len(batch)} handles): {exc}")
            time.sleep(max(0.0, delay_seconds))
            continue

        for item in items:
            owner = normalize_username(extract_username(item))

            nested_comments = item.get("comments") if isinstance(item, dict) else None
            if isinstance(nested_comments, list):
                for raw_comment in nested_comments:
                    if not isinstance(raw_comment, dict):
                        continue
                    parsed = parse_comment_record(raw_comment, fallback_username=owner)
                    if parsed:
                        username, comment = parsed
                        comments_by_user.setdefault(username, []).append(comment)
                continue

            if isinstance(item, dict):
                parsed = parse_comment_record(item, fallback_username=owner)
                if parsed:
                    username, comment = parsed
                    comments_by_user.setdefault(username, []).append(comment)

        time.sleep(max(0.0, delay_seconds))

    for username in list(comments_by_user.keys()):
        dedup = {}
        for comment in comments_by_user[username]:
            key = (comment.get("post_id", ""), comment.get("text", ""))
            if key not in dedup:
                dedup[key] = comment
        comments_by_user[username] = list(dedup.values())[:comments_per_account]

    return comments_by_user


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)

    usernames = read_handles(input_path)
    print(f"[enrich] loaded {len(usernames)} handles from {input_path}")

    token = os.getenv("APIFY_TOKEN", "").strip()
    profile_actor_id = os.getenv("APIFY_PROFILE_ACTOR_ID", "").strip()
    post_actor_id = os.getenv("APIFY_POST_ACTOR_ID", "").strip()
    comment_actor_id = os.getenv("APIFY_COMMENT_ACTOR_ID", "").strip()

    profiles: Dict[str, Dict[str, Any]] = {}
    posts_by_user: Dict[str, List[Dict[str, Any]]] = {username: [] for username in usernames}
    comments_by_user: Dict[str, List[Dict[str, Any]]] = {username: [] for username in usernames}

    client: Optional[ApifyClient] = None
    if token:
        client = ApifyClient(token=token)

    if client and profile_actor_id:
        profiles = fetch_profiles(
            client=client,
            actor_id=profile_actor_id,
            usernames=usernames,
            batch_size=args.batch_size,
            delay_seconds=args.delay_seconds,
            wait_seconds=args.wait_seconds,
        )
    else:
        print("[enrich] profile scrape skipped (missing APIFY_TOKEN/APIFY_PROFILE_ACTOR_ID)")

    for username in usernames:
        profiles.setdefault(
            username,
            {
                "bio": "",
                "followers": 0,
                "following": 0,
                "avg_likes": 0.0,
                "avg_comments": 0.0,
            },
        )

    post_candidates = [
        username
        for username in sorted(usernames, key=lambda u: profiles[u].get("followers", 0), reverse=True)
        if int(profiles[username].get("followers", 0) or 0) >= args.min_followers_for_posts
    ][: args.max_post_accounts]

    if client and post_actor_id and post_candidates:
        posts_by_user.update(
            fetch_posts(
                client=client,
                actor_id=post_actor_id,
                usernames=post_candidates,
                batch_size=args.batch_size,
                delay_seconds=args.delay_seconds,
                wait_seconds=args.wait_seconds,
                posts_per_account=args.posts_per_account,
            )
        )
    else:
        print("[enrich] post scrape skipped (missing APIFY_POST_ACTOR_ID or no eligible accounts)")

    embedded_comments = extract_comments_from_posts(posts_by_user)
    for username, comments in embedded_comments.items():
        comments_by_user.setdefault(username, []).extend(comments)

    def comment_potential_score(username: str) -> float:
        followers = int(profiles[username].get("followers", 0) or 0)
        med_er = median_engagement_rate(posts_by_user.get(username, []), followers)
        return (followers * 0.00001) + (med_er * 100.0)

    comment_candidates = sorted(post_candidates, key=comment_potential_score, reverse=True)[
        : args.max_comment_accounts
    ]

    if client and comment_actor_id and comment_candidates:
        # If comment actor is the same as post actor, use comments embedded in post data
        # to avoid redundant runs and schema mismatches.
        if comment_actor_id == post_actor_id:
            print(
                "[enrich] comment actor equals post actor, "
                "using embedded comments from post scrape"
            )
        else:
            fetched_comments = fetch_comments(
                client=client,
                actor_id=comment_actor_id,
                usernames=comment_candidates,
                batch_size=args.batch_size,
                delay_seconds=args.delay_seconds,
                wait_seconds=args.wait_seconds,
                comments_per_account=args.comments_per_account,
                comments_per_post=args.comments_per_post,
            )
            for username, comments in fetched_comments.items():
                comments_by_user.setdefault(username, []).extend(comments)
    else:
        print(
            "[enrich] comment scrape skipped "
            "(missing APIFY_COMMENT_ACTOR_ID or no comment candidates)"
        )

    enriched: List[Dict[str, Any]] = []
    for username in usernames:
        dedup_comments: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for comment in comments_by_user.get(username, []):
            key = (str(comment.get("post_id", "")), str(comment.get("text", "")))
            dedup_comments.setdefault(key, comment)

        account = {
            "username": username,
            "profile": profiles.get(username, {}),
            "posts": posts_by_user.get(username, [])[: args.posts_per_account],
            "comments": list(dedup_comments.values())[: args.comments_per_account],
        }
        enriched.append(account)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "accounts": enriched,
                "meta": {
                    "input_count": len(usernames),
                    "post_candidates": len(post_candidates),
                    "comment_candidates": len(comment_candidates),
                },
            },
            handle,
            ensure_ascii=False,
            indent=2,
        )

    print(f"[enrich] wrote {len(enriched)} enriched accounts -> {output_path}")


if __name__ == "__main__":
    main()
