#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = REPO_ROOT / "project"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.apify_client import ApifyClient, ApifyError, extract_username, normalize_username  # noqa: E402


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def first_present(record: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
    for key in keys:
        value = record.get(key)
        if value is not None and value != "":
            return value
    return default


def to_number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower().replace(",", "")
    if not text:
        return None

    multiplier = 1.0
    if text.endswith("k"):
        multiplier = 1000.0
        text = text[:-1]
    elif text.endswith("m"):
        multiplier = 1_000_000.0
        text = text[:-1]
    try:
        return float(text) * multiplier
    except ValueError:
        return None


def to_int(value: Any, default: int = 0) -> int:
    num = to_number(value)
    return int(num) if num is not None else default


def write_document(path: Path, metadata: Dict[str, str], body_lines: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    for key in sorted(metadata.keys()):
        value = str(metadata[key]).replace("\n", " ").strip()
        lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")
    lines.extend(body_lines)
    if not lines[-1].endswith("\n"):
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def run_actor_items(
    client: ApifyClient,
    actor_id: str,
    actor_input: Dict[str, Any],
    wait_seconds: int,
    dataset_limit: int,
) -> List[Dict[str, Any]]:
    return client.run_actor_and_fetch_items(
        actor_id=actor_id,
        actor_input=actor_input,
        wait_for_finish_seconds=wait_seconds,
        dataset_limit=dataset_limit,
    )


def fetch_profile_items(
    client: ApifyClient,
    actor_id: str,
    username: str,
    wait_seconds: int,
) -> List[Dict[str, Any]]:
    attempts = [
        {"usernames": [username], "resultsLimit": 1},
        {"username": [username], "resultsLimit": 1},
        {"username": username, "resultsLimit": 1},
    ]
    last_err: Optional[Exception] = None
    for actor_input in attempts:
        try:
            return run_actor_items(client, actor_id, actor_input, wait_seconds, dataset_limit=20)
        except Exception as exc:  # noqa: BLE001
            last_err = exc
    raise RuntimeError(f"Unable to fetch profile for @{username}") from last_err


def fetch_post_items(
    client: ApifyClient,
    actor_id: str,
    username: str,
    wait_seconds: int,
    results_limit: int,
) -> List[Dict[str, Any]]:
    attempts = [
        {
            "username": [username],
            "resultsLimit": results_limit,
            "dataDetailLevel": "detailedData",
        },
        {
            "usernames": [username],
            "resultsLimit": results_limit,
            "dataDetailLevel": "detailedData",
        },
        {
            "username": username,
            "resultsLimit": results_limit,
            "dataDetailLevel": "detailedData",
        },
    ]
    last_err: Optional[Exception] = None
    for actor_input in attempts:
        try:
            return run_actor_items(
                client,
                actor_id,
                actor_input,
                wait_seconds,
                dataset_limit=max(500, results_limit * 4),
            )
        except Exception as exc:  # noqa: BLE001
            last_err = exc
    raise RuntimeError(f"Unable to fetch posts for @{username}") from last_err


def parse_profile(profile_items: List[Dict[str, Any]], target_username: str) -> Dict[str, Any]:
    fallback = {
        "username": target_username,
        "bio": "",
        "full_name": "",
        "followers": 0,
        "following": 0,
        "external_url": "",
        "category": "",
        "is_verified": False,
    }
    if not profile_items:
        return fallback

    for item in profile_items:
        record = item.get("profile") if isinstance(item.get("profile"), dict) else item
        username = normalize_username(
            extract_username(item) or extract_username(record) or target_username
        )
        if username != target_username:
            continue
        return {
            "username": username,
            "bio": str(
                first_present(
                    record,
                    ["bio", "biography", "description", "about"],
                    default="",
                )
                or ""
            ),
            "full_name": str(
                first_present(record, ["fullName", "full_name", "name"], default="") or ""
            ),
            "followers": to_int(
                first_present(
                    record,
                    ["followers", "followersCount", "followerCount", "edge_followed_by"],
                ),
                default=0,
            ),
            "following": to_int(
                first_present(record, ["following", "followingCount", "followsCount"]),
                default=0,
            ),
            "external_url": str(
                first_present(record, ["externalUrl", "external_url", "website"], default="")
                or ""
            ),
            "category": str(
                first_present(
                    record,
                    ["categoryName", "businessCategoryName", "category"],
                    default="",
                )
                or ""
            ),
            "is_verified": bool(
                first_present(record, ["verified", "isVerified"], default=False) or False
            ),
        }
    return fallback


def parse_post_record(record: Dict[str, Any], fallback_username: str) -> Optional[Dict[str, Any]]:
    username = normalize_username(extract_username(record) or fallback_username)
    if not username:
        return None
    caption = str(first_present(record, ["caption", "text", "description", "title"], default="") or "").strip()
    return {
        "username": username,
        "post_id": str(first_present(record, ["postId", "id", "shortCode", "shortcode"], default="") or "").strip(),
        "url": str(first_present(record, ["url", "postUrl", "displayUrl"], default="") or "").strip(),
        "timestamp": str(
            first_present(
                record,
                ["timestamp", "createdAt", "takenAtTimestamp", "taken_at", "publishedAt"],
                default="",
            )
            or ""
        ).strip(),
        "likes": to_int(first_present(record, ["likesCount", "likes", "likeCount"], default=0), default=0),
        "comments_count": to_int(
            first_present(record, ["commentsCount", "comments", "commentCount"], default=0),
            default=0,
        ),
        "caption": caption,
    }


def extract_posts(post_items: List[Dict[str, Any]], target_username: str) -> List[Dict[str, Any]]:
    posts: List[Dict[str, Any]] = []
    for item in post_items:
        owner = normalize_username(extract_username(item) or target_username)
        nested_posts = item.get("posts")
        if isinstance(nested_posts, list):
            for raw_post in nested_posts:
                if not isinstance(raw_post, dict):
                    continue
                parsed = parse_post_record(raw_post, fallback_username=owner)
                if parsed and parsed["username"] == target_username:
                    posts.append(parsed)
            continue

        if isinstance(item, dict):
            parsed = parse_post_record(item, fallback_username=owner)
            if parsed and parsed["username"] == target_username:
                posts.append(parsed)

    deduped: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for post in posts:
        key_parts = [post.get("post_id", ""), post.get("url", ""), post.get("caption", "")]
        key = "||".join(part.strip() for part in key_parts if part and str(part).strip())
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        deduped.append(post)

    deduped.sort(key=lambda p: (p.get("timestamp", ""), p.get("post_id", "")), reverse=True)
    return deduped


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scrape Blake Instagram profile + captions via Apify."
    )
    parser.add_argument("--username", default="blakemycoskie")
    parser.add_argument("--output-dir", default="blake/instagram")
    parser.add_argument("--results-limit", type=int, default=2000)
    parser.add_argument("--wait-seconds", type=int, default=300)
    args = parser.parse_args()

    # Load credentials from project/.env if caller didn't export env vars.
    load_env_file(PROJECT_ROOT / ".env")

    token = os.getenv("APIFY_TOKEN", "").strip()
    profile_actor_id = os.getenv("APIFY_PROFILE_ACTOR_ID", "").strip()
    post_actor_id = os.getenv("APIFY_POST_ACTOR_ID", "").strip()
    if not token:
        raise RuntimeError("APIFY_TOKEN is required")
    if not profile_actor_id:
        raise RuntimeError("APIFY_PROFILE_ACTOR_ID is required")
    if not post_actor_id:
        raise RuntimeError("APIFY_POST_ACTOR_ID is required")

    username = normalize_username(args.username)
    if not username:
        raise RuntimeError("Instagram username is required")

    output_dir = Path(args.output_dir)
    raw_dir = output_dir / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    collected_at = dt.datetime.now(dt.timezone.utc).isoformat()
    collected_stamp = collected_at.replace(":", "").replace("-", "")

    client = ApifyClient(token=token)

    profile_items = fetch_profile_items(client, profile_actor_id, username, wait_seconds=args.wait_seconds)
    profile = parse_profile(profile_items, target_username=username)

    post_items = fetch_post_items(
        client,
        post_actor_id,
        username,
        wait_seconds=args.wait_seconds,
        results_limit=max(50, args.results_limit),
    )
    posts = extract_posts(post_items, target_username=username)
    captions = [post for post in posts if str(post.get("caption", "")).strip()]

    # Write raw payloads for traceability.
    profile_raw_path = raw_dir / f"{collected_stamp}_{username}_profile_items.json"
    posts_raw_path = raw_dir / f"{collected_stamp}_{username}_post_items.json"
    profile_raw_path.write_text(json.dumps(profile_items, indent=2, ensure_ascii=False), encoding="utf-8")
    posts_raw_path.write_text(json.dumps(post_items, indent=2, ensure_ascii=False), encoding="utf-8")

    profile_path = output_dir / "profile.json"
    profile_enriched = {
        **profile,
        "collected_at": collected_at,
        "source_url": f"https://www.instagram.com/{username}/",
    }
    profile_path.write_text(json.dumps(profile_enriched, indent=2, ensure_ascii=False), encoding="utf-8")

    captions_csv_path = output_dir / "captions.csv"
    with captions_csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "username",
                "post_id",
                "timestamp",
                "url",
                "likes",
                "comments_count",
                "caption",
            ],
        )
        writer.writeheader()
        for row in captions:
            writer.writerow(
                {
                    "username": row.get("username", ""),
                    "post_id": row.get("post_id", ""),
                    "timestamp": row.get("timestamp", ""),
                    "url": row.get("url", ""),
                    "likes": row.get("likes", 0),
                    "comments_count": row.get("comments_count", 0),
                    "caption": row.get("caption", ""),
                }
            )

    captions_txt_path = output_dir / "captions.txt"
    body_lines: List[str] = []
    for index, row in enumerate(captions, start=1):
        body_lines.append(
            f"[{index}] post_id={row.get('post_id','')} timestamp={row.get('timestamp','')} url={row.get('url','')}"
        )
        body_lines.append(str(row.get("caption", "")).strip())
        body_lines.append("")

    write_document(
        captions_txt_path,
        {
            "source_id": f"instagram_{username}_captions",
            "source_type": "instagram_captions",
            "source_group": "instagram",
            "username": username,
            "url": f"https://www.instagram.com/{username}/",
            "collected_at": collected_at,
            "caption_count": str(len(captions)),
            "post_record_count": str(len(posts)),
            "results_limit_requested": str(max(50, args.results_limit)),
        },
        body_lines,
    )

    summary_path = output_dir / "run_summary.json"
    summary = {
        "username": username,
        "collected_at": collected_at,
        "profile_actor_id": profile_actor_id,
        "post_actor_id": post_actor_id,
        "profile_items_count": len(profile_items),
        "post_items_count": len(post_items),
        "post_records_extracted": len(posts),
        "captions_count": len(captions),
        "outputs": {
            "profile_json": str(profile_path),
            "captions_csv": str(captions_csv_path),
            "captions_txt": str(captions_txt_path),
            "profile_raw": str(profile_raw_path),
            "posts_raw": str(posts_raw_path),
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[instagram] username -> @{username}")
    print(f"[instagram] profile followers -> {profile_enriched.get('followers', 0)}")
    print(f"[instagram] captions saved -> {len(captions)}")
    print(f"[instagram] profile -> {profile_path}")
    print(f"[instagram] captions csv -> {captions_csv_path}")
    print(f"[instagram] captions txt -> {captions_txt_path}")
    print(f"[instagram] summary -> {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
