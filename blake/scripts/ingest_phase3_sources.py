#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


USER_AGENT = "Mozilla/5.0 (compatible; BlakeCorpusIngest/1.0; +https://example.com)"

TIM_TRANSCRIPTS: List[Dict[str, str]] = [
    {
        "source_id": "tim_ferriss_249",
        "slug": "the-tim-ferriss-show-transcripts-blake-mycoskie",
        "url": "https://tim.blog/2018/06/01/the-tim-ferriss-show-transcripts-blake-mycoskie/",
    },
    {
        "source_id": "tim_ferriss_446",
        "slug": "blake-mycoskie-2-transcript",
        "url": "https://tim.blog/2020/07/17/blake-mycoskie-2-transcript/",
    },
    {
        "source_id": "tim_ferriss_551",
        "slug": "blake-mycoskie-3-transcript",
        "url": "https://tim.blog/2021/12/05/blake-mycoskie-3-transcript/",
    },
]

YOUTUBE_URLS: List[str] = [
    "https://www.youtube.com/watch?v=hoA68-gXIto",
    "https://youtu.be/dH0a_GPUiSU?si=wYLTfZAAMwhYX8mW",
    "https://youtu.be/onZC4N1_hWk?si=uBSTW3UC1H01HI7p",
    "https://youtu.be/gbWj33Ej3rA?si=bNEEUmWp7mvubUcp",
    "https://youtu.be/oDGJcf00fpg?si=eETZ7RNKzc4dnE7Y",
    "https://youtu.be/jpM7pbgLK_k?si=sN0cSbk9UTRQ5s0r",
    "https://youtu.be/7-uqMDtPAcM?si=Uj56wAYiq9MYHUY3",
    "https://youtu.be/UOFLZ8hePRk?si=cXs2-i7_U9IWMCHY",
    "https://youtu.be/s6msveTjZXQ?si=Zve6APw9VXddJ5Nw",
    "https://www.youtube.com/live/FeWkjl_Mync?si=yqAHpExWmTirESIu",
    "https://youtu.be/domK3ylcmQ4?si=Oph_W7vx95ITUhuZ",
    "https://youtu.be/vhNarj7nqgs?si=d3MBZLCgModux47c",
    "https://youtu.be/Jtbyxv34TMw?si=72WMZyi_v-NCPcqE",
    "https://youtu.be/wjGV9pdE-vU?si=i8sA7XWkUSvffajs",
    "https://youtu.be/hoA68-gXIto?si=Nnju_0YvISCrTVbo",
    "https://youtu.be/F_TfO2IN98c?si=BEqD6ltconGt0IM2",
    "https://youtu.be/wjGV9pdE-vU?si=PBDTA54XYIHtr67D",
    "https://youtu.be/NLHaru4iPt0?si=oj-Qedxlgan5QZKV",
]

SUBSTACK_FEED_URL = "https://nomagicpills.substack.com/feed"


VIDEO_ID_PATTERNS = [
    re.compile(r"[?&]v=([A-Za-z0-9_-]{11})"),
    re.compile(r"youtu\.be/([A-Za-z0-9_-]{11})"),
    re.compile(r"youtube\.com/live/([A-Za-z0-9_-]{11})"),
]

SRT_TIMESTAMP_RE = re.compile(r"^\d{2}:\d{2}:\d{2},\d{3}\s+-->\s+\d{2}:\d{2}:\d{2},\d{3}$")
TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"[ \t]+")
PARA_RE = re.compile(r"\n{3,}")


def fetch_text(url: str, retries: int = 3, delay_seconds: float = 1.5) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/json,application/xml,text/xml,*/*",
        },
    )
    last_err: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read().decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            if attempt < retries:
                time.sleep(delay_seconds * attempt)
    raise RuntimeError(f"Failed to fetch URL after {retries} attempts: {url}") from last_err


def slugify(value: str, max_len: int = 80) -> str:
    cleaned = value.strip().lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", cleaned)
    cleaned = cleaned.strip("-")
    if not cleaned:
        return "untitled"
    return cleaned[:max_len].rstrip("-")


def normalize_date(date_text: str) -> str:
    if not date_text:
        return "unknown-date"
    date_text = date_text.strip()
    if re.fullmatch(r"\d{8}", date_text):
        return f"{date_text[0:4]}-{date_text[4:6]}-{date_text[6:8]}"
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            parsed = dt.datetime.strptime(date_text, fmt)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue
    if "T" in date_text:
        return date_text.split("T", 1)[0]
    return date_text[:10]


def clean_html_to_text(raw_html: str) -> str:
    text = raw_html
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
    text = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", text)
    text = re.sub(r"(?i)</\s*(p|div|li|h1|h2|h3|h4|h5|h6|blockquote)\s*>", "\n", text)
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = text.replace("\r", "\n")
    lines = []
    for line in text.split("\n"):
        line = WHITESPACE_RE.sub(" ", line).strip()
        lines.append(line)
    text = "\n".join(lines)
    text = PARA_RE.sub("\n\n", text).strip()
    return text


def parse_video_id(url: str) -> Optional[str]:
    for pattern in VIDEO_ID_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    return None


def dedupe_video_urls(urls: Iterable[str]) -> List[Tuple[str, str]]:
    deduped: Dict[str, str] = {}
    for url in urls:
        video_id = parse_video_id(url)
        if not video_id:
            continue
        deduped.setdefault(video_id, url)
    return [(video_id, deduped[video_id]) for video_id in sorted(deduped.keys())]


def run_yt_dlp_json(video_id: str, retries: int = 3) -> Dict[str, object]:
    url = f"https://www.youtube.com/watch?v={video_id}"
    cmd = [
        "yt-dlp",
        "--ignore-config",
        "--skip-download",
        "--no-warnings",
        "--dump-single-json",
        url,
    ]
    last_err: Optional[Exception] = None

    for attempt in range(1, retries + 1):
        try:
            proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr.strip() or f"yt-dlp exit code {proc.returncode}")
            payload = json.loads(proc.stdout)
            if not isinstance(payload, dict) or payload.get("id") != video_id:
                raise RuntimeError("yt-dlp returned malformed metadata")
            return payload
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            if attempt < retries:
                time.sleep(1.5 * attempt)

    raise RuntimeError(f"Failed yt-dlp metadata pull for {video_id}") from last_err


def download_youtube_subtitles(video_id: str, output_dir: Path, retries: int = 3) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    canonical_url = f"https://www.youtube.com/watch?v={video_id}"
    output_template = str(output_dir / f"{video_id}.%(ext)s")
    cmd = [
        "yt-dlp",
        "--ignore-config",
        "--skip-download",
        "--write-auto-subs",
        "--sub-langs",
        "en.*,en",
        "--convert-subs",
        "srt",
        "--output",
        output_template,
        canonical_url,
    ]

    last_err: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr.strip() or f"yt-dlp exit code {proc.returncode}")
            break
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            if attempt < retries:
                time.sleep(1.5 * attempt)
    else:
        raise RuntimeError(f"Failed subtitle download for {video_id}") from last_err

    preferred = [
        output_dir / f"{video_id}.en-orig.srt",
        output_dir / f"{video_id}.en.srt",
    ]
    for path in preferred:
        if path.exists() and path.stat().st_size > 0:
            return path

    candidates = sorted(output_dir.glob(f"{video_id}*.srt"))
    if not candidates:
        raise FileNotFoundError(f"No SRT transcript generated for {video_id}")
    return candidates[0]


def srt_to_text(srt_content: str) -> str:
    blocks = re.split(r"\n\s*\n", srt_content.replace("\r\n", "\n").replace("\r", "\n"))
    pieces: List[str] = []

    for block in blocks:
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        text_lines: List[str] = []
        for line in lines:
            if line.isdigit():
                continue
            if SRT_TIMESTAMP_RE.match(line):
                continue
            cleaned = TAG_RE.sub("", line).strip()
            if cleaned:
                text_lines.append(cleaned)
        if text_lines:
            merged = " ".join(text_lines)
            if not pieces or pieces[-1] != merged:
                pieces.append(merged)

    return "\n".join(pieces).strip()


def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def write_document(path: Path, metadata: Dict[str, str], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    for key in sorted(metadata.keys()):
        value = metadata[key].replace("\n", " ").strip()
        lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")
    lines.append(body.strip())
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def ingest_tim_transcripts(root: Path, collected_at: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    output_dir = root / "podcasts" / "tim_ferriss"

    for item in TIM_TRANSCRIPTS:
        slug = item["slug"]
        api_url = f"https://tim.blog/wp-json/wp/v2/posts?slug={urllib.parse.quote(slug)}"
        payload = fetch_text(api_url)
        parsed = json.loads(payload)
        if not parsed:
            raise RuntimeError(f"No Tim transcript found for slug={slug}")
        post = parsed[0]

        title = str(post.get("title", {}).get("rendered", "")).strip() or slug
        link = str(post.get("link", item["url"])).strip()
        published_raw = str(post.get("date", "")).strip()
        published_date = normalize_date(published_raw)
        content_html = str(post.get("content", {}).get("rendered", ""))
        text = clean_html_to_text(content_html)

        filename = f"{published_date}_{item['source_id']}.txt"
        relative_path = Path("blake") / "podcasts" / "tim_ferriss" / filename
        absolute_path = output_dir / filename

        write_document(
            absolute_path,
            {
                "source_id": item["source_id"],
                "source_type": "podcast_transcript",
                "source_group": "tim_ferriss",
                "title": title,
                "url": link,
                "published_at": published_raw,
                "collected_at": collected_at,
            },
            text,
        )

        rows.append(
            {
                "source_id": item["source_id"],
                "bucket": "podcasts",
                "source_group": "tim_ferriss",
                "title": title,
                "url": link,
                "published_at": published_raw,
                "collected_at": collected_at,
                "file_path": str(relative_path),
                "word_count": str(word_count(text)),
                "status": "ok",
                "notes": "",
            }
        )

    return rows


def ingest_youtube_transcripts(root: Path, collected_at: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    output_dir = root / "podcasts" / "youtube"
    raw_dir = output_dir / "_raw_srt"
    deduped = dedupe_video_urls(YOUTUBE_URLS)

    for video_id, source_url in deduped:
        canonical_url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            metadata = run_yt_dlp_json(video_id)
            title = str(metadata.get("title", "")).strip() or video_id
            channel = str(metadata.get("channel", "")).strip()
            uploader = str(metadata.get("uploader", "")).strip()
            upload_raw = str(metadata.get("upload_date", "")).strip()
            published_date = normalize_date(upload_raw)

            srt_path = download_youtube_subtitles(video_id, raw_dir)
            srt_text = srt_path.read_text(encoding="utf-8", errors="replace")
            transcript_text = srt_to_text(srt_text)
            if not transcript_text:
                raise RuntimeError(f"Transcript is empty for {video_id}")

            safe_title = slugify(title, max_len=60)
            filename = f"{published_date}_{video_id}_{safe_title}.txt"
            relative_path = Path("blake") / "podcasts" / "youtube" / filename
            absolute_path = output_dir / filename

            write_document(
                absolute_path,
                {
                    "source_id": f"youtube_{video_id}",
                    "source_type": "youtube_auto_caption",
                    "source_group": "youtube",
                    "title": title,
                    "url": canonical_url,
                    "original_input_url": source_url,
                    "channel": channel,
                    "uploader": uploader,
                    "published_at": upload_raw,
                    "collected_at": collected_at,
                },
                transcript_text,
            )

            rows.append(
                {
                    "source_id": f"youtube_{video_id}",
                    "bucket": "podcasts",
                    "source_group": "youtube",
                    "title": title,
                    "url": canonical_url,
                    "published_at": upload_raw,
                    "collected_at": collected_at,
                    "file_path": str(relative_path),
                    "word_count": str(word_count(transcript_text)),
                    "status": "ok",
                    "notes": f"channel={channel}; uploader={uploader}",
                }
            )
        except Exception as exc:  # noqa: BLE001
            rows.append(
                {
                    "source_id": f"youtube_{video_id}",
                    "bucket": "podcasts",
                    "source_group": "youtube",
                    "title": video_id,
                    "url": canonical_url,
                    "published_at": "",
                    "collected_at": collected_at,
                    "file_path": "",
                    "word_count": "0",
                    "status": "error",
                    "notes": str(exc),
                }
            )

    return rows


def ingest_substack(root: Path, collected_at: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    output_dir = root / "self" / "substack"

    xml_text = fetch_text(SUBSTACK_FEED_URL)
    root_xml = ET.fromstring(xml_text)

    for item in root_xml.findall("./channel/item"):
        title = (item.findtext("title") or "").strip() or "untitled"
        link = (item.findtext("link") or "").strip()
        pub_date_raw = (item.findtext("pubDate") or "").strip()
        pub_date = normalize_date(pub_date_raw)

        encoded_node = None
        for child in list(item):
            if child.tag.endswith("encoded"):
                encoded_node = child
                break
        encoded_html = (encoded_node.text if encoded_node is not None and encoded_node.text else "").strip()
        text = clean_html_to_text(encoded_html)

        slug = "post"
        match = re.search(r"/p/([a-z0-9-]+)", link)
        if match:
            slug = match.group(1)
        safe_slug = slugify(slug, max_len=70)
        source_id = f"substack_{safe_slug}"
        filename = f"{pub_date}_{safe_slug}.txt"
        relative_path = Path("blake") / "self" / "substack" / filename
        absolute_path = output_dir / filename

        write_document(
            absolute_path,
            {
                "source_id": source_id,
                "source_type": "substack_post",
                "source_group": "substack",
                "title": title,
                "url": link,
                "published_at": pub_date_raw,
                "collected_at": collected_at,
            },
            text,
        )

        rows.append(
            {
                "source_id": source_id,
                "bucket": "self",
                "source_group": "substack",
                "title": title,
                "url": link,
                "published_at": pub_date_raw,
                "collected_at": collected_at,
                "file_path": str(relative_path),
                "word_count": str(word_count(text)),
                "status": "ok",
                "notes": "",
            }
        )

    return rows


def write_manifest(rows: List[Dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "source_id",
        "bucket",
        "source_group",
        "title",
        "url",
        "published_at",
        "collected_at",
        "file_path",
        "word_count",
        "status",
        "notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest Blake Part 3 research sources.")
    parser.add_argument(
        "--root",
        default="blake",
        help="Root directory for Blake corpus (default: blake).",
    )
    args = parser.parse_args()

    root = Path(args.root)
    root.mkdir(parents=True, exist_ok=True)
    collected_at = dt.datetime.now(dt.timezone.utc).isoformat()

    rows: List[Dict[str, str]] = []

    print("[ingest] Tim Ferriss transcripts...")
    rows.extend(ingest_tim_transcripts(root, collected_at))

    print("[ingest] YouTube transcripts...")
    rows.extend(ingest_youtube_transcripts(root, collected_at))

    print("[ingest] Substack posts...")
    rows.extend(ingest_substack(root, collected_at))

    manifest_path = root / "manifest" / "sources.csv"
    write_manifest(rows, manifest_path)

    print(f"[ingest] wrote manifest -> {manifest_path}")
    print(f"[ingest] total sources: {len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
