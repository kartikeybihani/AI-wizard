from __future__ import annotations

import argparse
import csv
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set

from utils.apify_client import ApifyClient, ApifyError, extract_username, normalize_username

MANUAL_SEED_HANDLES = [
    "the.holistic.psychologist",
    "nedratawwab",
    "sitwithwhit",
    "drjennywang",
    "therapyjeff",
    "theanxietyhealer",
    "selfcareisforeveryone",
    "mentalhealthamerica",
    "mindcharity",
    "active_minds",
    "theblurtfoundation",
    "iamleahbowers",
    "drjuliesmith",
    "the.happybroadcast",
    "drleaf",
    "mindfulmft",
    "thedepressionproject",
    "tinybuddhaofficial",
    "anxietyjosh",
    "kwikbrain",
    "headspace",
    "calm",
    "psychologytoday",
    "projectsemicolon",
    "nami_communicate",
    "talkspace",
    "betterhelp",
    "mantherapy",
    "letstalkmenhealth",
    "theocdproject",
]

AGGREGATOR_SEED_HANDLES = [
    "mindsettherapy",
    "mentalhealthmatch",
    "mindful__living",
    "thegoodquote",
    "therapyforwomen",
    "therapynotebooks",
    "thementalhealthspot",
    "mytherapistsays",
    "anxiety_wellness",
    "mindful__mamas",
    "emotionalwellnessco",
    "anxietysupportdaily",
    "mentalhealthawarness",
    "dearmentalhealth",
    "mindmattersdaily",
    "yourdiagnonsense",
    "traumatherapyhub",
    "depressionlookslikeme",
    "cptsdwarriors",
    "thesadgirlsclub",
    "thefriendlinessproject",
    "weareallhuman",
    "mindfulmoments_ig",
    "selfcaredepot",
    "livewellmindfully",
    "therapyinsider",
    "thementalhealthcoach",
    "safeplaceformentalhealth",
    "mindgrowthcollective",
    "talkyourfeelings",
]

DEFAULT_HASHTAGS = [
    "#mentalhealth",
    "#anxietyhelp",
    "#therapy",
    "#mentalhealthadvocate",
    "#mentalhealthawareness",
    "#enoughmovement",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed influencer handles")
    parser.add_argument("--output", default="data/raw_handles.csv")
    parser.add_argument("--delay-seconds", type=float, default=2.5)
    parser.add_argument("--manual-count", type=int, default=30)
    parser.add_argument("--aggregator-count", type=int, default=30)
    parser.add_argument("--hashtag-limit-per-tag", type=int, default=60)
    parser.add_argument("--skip-apify", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--wait-seconds", type=int, default=240)
    return parser.parse_args()


def collect_usernames(payload: Any, found: Set[str]) -> None:
    username = extract_username(payload)
    if username:
        found.add(username)

    if isinstance(payload, dict):
        for value in payload.values():
            collect_usernames(value, found)
    elif isinstance(payload, list):
        for item in payload:
            collect_usernames(item, found)


def merge_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    merged: Dict[str, Dict[str, str]] = {}

    for row in rows:
        username = normalize_username(row.get("username", ""))
        if not username:
            continue
        source = row.get("source", "unknown").strip() or "unknown"
        discovered_at = row.get("discovered_at", "")

        if username not in merged:
            merged[username] = {
                "username": username,
                "source": source,
                "discovered_at": discovered_at,
            }
            continue

        current_sources = set(filter(None, merged[username]["source"].split(";")))
        current_sources.add(source)
        merged[username]["source"] = ";".join(sorted(current_sources))
        if discovered_at and (
            not merged[username]["discovered_at"]
            or discovered_at < merged[username]["discovered_at"]
        ):
            merged[username]["discovered_at"] = discovered_at

    return sorted(merged.values(), key=lambda row: row["username"])


def read_existing_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [
            {
                "username": row.get("username", ""),
                "source": row.get("source", ""),
                "discovered_at": row.get("discovered_at", ""),
            }
            for row in reader
        ]


def write_rows(path: Path, rows: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["username", "source", "discovered_at"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    output_path = Path(args.output)
    timestamp = datetime.now(timezone.utc).isoformat()

    rows: List[Dict[str, str]] = []

    for handle in MANUAL_SEED_HANDLES[: args.manual_count]:
        rows.append(
            {
                "username": normalize_username(handle),
                "source": "manual_seed",
                "discovered_at": timestamp,
            }
        )

    for handle in AGGREGATOR_SEED_HANDLES[: args.aggregator_count]:
        rows.append(
            {
                "username": normalize_username(handle),
                "source": "aggregator_seed",
                "discovered_at": timestamp,
            }
        )

    token = os.getenv("APIFY_TOKEN", "").strip()
    hashtag_actor_id = os.getenv("APIFY_HASHTAG_ACTOR_ID", "").strip()

    if not args.skip_apify and token and hashtag_actor_id:
        client = ApifyClient(token=token)
        for hashtag in DEFAULT_HASHTAGS:
            actor_input = {
                "hashtags": [hashtag.lstrip("#")],
                "resultsLimit": args.hashtag_limit_per_tag,
            }
            try:
                items = client.run_actor_and_fetch_items(
                    actor_id=hashtag_actor_id,
                    actor_input=actor_input,
                    wait_for_finish_seconds=args.wait_seconds,
                    dataset_limit=args.hashtag_limit_per_tag * 5,
                )
            except ApifyError as exc:
                print(f"[seed] hashtag scrape failed for {hashtag}: {exc}")
                continue

            discovered: Set[str] = set()
            for item in items:
                collect_usernames(item, discovered)

            count = 0
            for username in sorted(discovered):
                rows.append(
                    {
                        "username": username,
                        "source": f"apify_hashtag:{hashtag}",
                        "discovered_at": timestamp,
                    }
                )
                count += 1
                if count >= args.hashtag_limit_per_tag:
                    break

            time.sleep(max(0.0, args.delay_seconds))
    else:
        print(
            "[seed] skipping Apify hashtag discovery "
            "(missing APIFY_TOKEN/APIFY_HASHTAG_ACTOR_ID or --skip-apify)"
        )

    if output_path.exists() and not args.overwrite:
        rows.extend(read_existing_rows(output_path))

    merged_rows = merge_rows(rows)
    write_rows(output_path, merged_rows)

    print(f"[seed] wrote {len(merged_rows)} deduplicated handles -> {output_path}")


if __name__ == "__main__":
    main()
