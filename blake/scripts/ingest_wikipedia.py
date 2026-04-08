#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
from pathlib import Path
from typing import Dict, Tuple

import requests


USER_AGENT = "BlakeCorpusIngest/1.0 (research-use)"


def clean_text(text: str) -> str:
    text = html.unescape(text or "")
    text = text.replace("\r", "\n")
    lines = []
    for line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()
        if line:
            lines.append(line)
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


def write_document(path: Path, metadata: Dict[str, str], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    for key in sorted(metadata.keys()):
        value = str(metadata[key]).replace("\n", " ").strip()
        lines.append(f"{key}: {value}")
    lines.extend(["---", "", body.strip(), ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def fetch_wikipedia_page(title: str) -> Tuple[Dict[str, object], Dict[str, object]]:
    endpoint = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "format": "json",
        "redirects": "1",
        "prop": "extracts|info|revisions",
        "titles": title,
        "explaintext": "1",
        "exsectionformat": "wiki",
        "inprop": "url|displaytitle",
        "rvprop": "ids|timestamp",
    }
    response = requests.get(
        endpoint,
        params=params,
        timeout=60,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    payload = response.json()
    pages = payload.get("query", {}).get("pages", {})
    if not pages:
        raise RuntimeError("Wikipedia API returned no pages")
    page = next(iter(pages.values()))
    if "missing" in page:
        raise RuntimeError(f"Wikipedia page not found: {title}")
    return page, payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest a Wikipedia page as plain text.")
    parser.add_argument("--title", default="Blake_Mycoskie")
    parser.add_argument("--output-dir", default="blake/self/wikipedia")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    collected_at = dt.datetime.now(dt.timezone.utc).isoformat()
    collected_date = collected_at[:10]

    page, raw_payload = fetch_wikipedia_page(args.title)
    page_title = str(page.get("title", args.title)).strip()
    full_url = str(page.get("fullurl", f"https://en.wikipedia.org/wiki/{args.title}")).strip()
    extract = clean_text(str(page.get("extract", "")))
    if not extract:
        raise RuntimeError("Wikipedia extract was empty")

    slug = re.sub(r"[^a-z0-9]+", "_", page_title.lower()).strip("_") or "wikipedia_page"
    txt_path = output_dir / f"{collected_date}_{slug}.txt"
    json_path = output_dir / f"{collected_date}_{slug}.raw.json"

    metadata = {
        "source_id": f"wikipedia_{slug}",
        "source_type": "wikipedia_article",
        "source_group": "wikipedia",
        "title": page_title,
        "url": full_url,
        "wikipedia_pageid": str(page.get("pageid", "")),
        "wikipedia_lastrevid": str(page.get("lastrevid", "")),
        "wikipedia_touched": str(page.get("touched", "")),
        "collected_at": collected_at,
    }
    write_document(txt_path, metadata, extract)

    json_path.write_text(json.dumps(raw_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    word_count = len(re.findall(r"\b\w+\b", extract))
    print(f"[wikipedia] wrote text -> {txt_path}")
    print(f"[wikipedia] wrote raw json -> {json_path}")
    print(f"[wikipedia] word_count -> {word_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
