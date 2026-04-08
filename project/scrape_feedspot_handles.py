from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from typing import Dict, Iterable, List, Set

import requests


DEFAULT_URL = "https://influencers.feedspot.com/mental_health_instagram_influencers/"
DEFAULT_OUTPUT = "data/feedspot_handles.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape candidate Instagram handles from Feedspot mental-health influencer page."
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout-seconds", type=float, default=25.0)
    return parser.parse_args()


def normalize_handle(raw: str) -> str:
    handle = raw.strip().lower()
    if handle.startswith("@"):
        handle = handle[1:]
    handle = handle.strip("/ ")
    if not re.fullmatch(r"[a-z0-9._]+", handle):
        return ""
    if len(handle) < 2:
        return ""
    return handle


def extract_handles_from_text(text: str) -> Set[str]:
    handles: Set[str] = set()

    # Pattern 1: explicit Instagram URLs
    for match in re.finditer(
        r"https?://(?:www\.)?instagram\.com/([a-zA-Z0-9._]+)/?",
        text,
        flags=re.IGNORECASE,
    ):
        handle = normalize_handle(match.group(1))
        if handle:
            handles.add(handle)

    # Pattern 2: @handle tokens in page text
    for match in re.finditer(r"@([a-zA-Z0-9._]{2,40})", text):
        handle = normalize_handle(match.group(1))
        if handle:
            handles.add(handle)

    return handles


def build_rows(handles: Iterable[str], source_url: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for handle in sorted(set(handles)):
        rows.append(
            {
                "username": handle,
                "source": "feedspot_scrape",
                "detail": source_url,
            }
        )
    return rows


def write_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["username", "source", "detail"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()

    response = requests.get(
        str(args.url).strip(),
        timeout=max(5.0, float(args.timeout_seconds)),
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        },
    )
    response.raise_for_status()

    handles = extract_handles_from_text(response.text)
    rows = build_rows(handles, str(args.url).strip())
    output_path = Path(str(args.output).strip())
    write_csv(output_path, rows)
    print(f"[feedspot_scrape] wrote {len(rows)} handles -> {output_path}")


if __name__ == "__main__":
    main()
