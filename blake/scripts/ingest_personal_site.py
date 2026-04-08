#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set


USER_AGENT = "BlakeCorpusIngest/1.0 (research-use)"
PRIMARY_DOMAIN = "blakemycoskie.com"
ALLOWED_NETLOCS = {PRIMARY_DOMAIN, f"www.{PRIMARY_DOMAIN}"}
SITEMAP_URLS = [
    "https://blakemycoskie.com/sitemap.xml",
    "https://blakemycoskie.com/wp-sitemap.xml",
]
SEED_URLS = [
    "https://blakemycoskie.com/",
    "https://blakemycoskie.com/about",
    "https://blakemycoskie.com/enough",
    "https://blakemycoskie.com/speaking",
    "https://blakemycoskie.com/no-magic-pill-pod",
    "https://blakemycoskie.com/connect",
    "https://blakemycoskie.com/news",
]
NOISE_LINES = {
    "your browser does not support the video tag.",
    "next",
    "previous",
}
IGNORED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".svg",
    ".ico",
    ".mp4",
    ".mov",
    ".webm",
    ".pdf",
    ".zip",
    ".xml",
    ".json",
    ".js",
    ".css",
}

HREF_RE = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
TITLE_RE = re.compile(r"(?is)<title[^>]*>(.*?)</title>")
TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"[ \t]+")
BLOCK_BREAK_RE = re.compile(
    r"(?is)</\s*(p|div|li|h1|h2|h3|h4|h5|h6|blockquote|section|article|tr|td|ul|ol|main|header|footer)\s*>"
)


def fetch_text(url: str, retries: int = 3, delay_seconds: float = 1.5) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xml,text/xml,*/*",
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


def normalize_url(url: str) -> Optional[str]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.netloc.lower() not in ALLOWED_NETLOCS:
        return None

    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    lower_path = path.lower()

    if lower_path.startswith("/wp-admin") or lower_path.startswith("/wp-content"):
        return None
    if lower_path.startswith("/wp-json"):
        return None

    suffix = Path(lower_path).suffix
    if suffix in IGNORED_EXTENSIONS:
        return None

    return urllib.parse.urlunparse(("https", PRIMARY_DOMAIN, path, "", "", ""))


def extract_links(raw_html: str, base_url: str) -> Set[str]:
    links: Set[str] = set()
    for match in HREF_RE.finditer(raw_html):
        href = match.group(1).strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        absolute = urllib.parse.urljoin(base_url, href)
        normalized = normalize_url(absolute)
        if normalized:
            links.add(normalized)
    return links


def extract_title(raw_html: str, fallback: str) -> str:
    match = TITLE_RE.search(raw_html)
    if not match:
        return fallback
    title = html.unescape(match.group(1))
    title = WHITESPACE_RE.sub(" ", title).strip()
    return title or fallback


def clean_html_to_text(raw_html: str) -> str:
    text = raw_html
    text = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", text)
    text = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", text)
    text = BLOCK_BREAK_RE.sub("\n", text)
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = text.replace("\r", "\n")

    seen: Set[str] = set()
    lines: List[str] = []
    for line in text.split("\n"):
        line = WHITESPACE_RE.sub(" ", line).strip()
        if not line:
            continue
        lowered = line.lower()
        if lowered in NOISE_LINES:
            continue
        # The site renders mobile/desktop copies; keep only first occurrence.
        if lowered in seen:
            continue
        seen.add(lowered)
        lines.append(line)

    return "\n".join(lines).strip()


def slugify(value: str, max_len: int = 80) -> str:
    cleaned = value.strip().lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", cleaned)
    cleaned = cleaned.strip("-")
    if not cleaned:
        return "untitled"
    return cleaned[:max_len].rstrip("-")


def source_slug_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.strip("/")
    if not path:
        return "home"
    return slugify(path.replace("/", "-"), max_len=70)


def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def write_document(path: Path, metadata: Dict[str, str], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    for key in sorted(metadata.keys()):
        value = metadata[key].replace("\n", " ").strip()
        lines.append(f"{key}: {value}")
    lines.extend(["---", "", body.strip(), ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def discover_sitemap_urls(max_urls: int) -> List[str]:
    discovered: Set[str] = set()
    visited_maps: Set[str] = set()
    queue: List[str] = list(SITEMAP_URLS)

    while queue and len(discovered) < max_urls:
        sitemap_url = queue.pop(0)
        if sitemap_url in visited_maps:
            continue
        visited_maps.add(sitemap_url)

        try:
            xml_text = fetch_text(sitemap_url)
            root = ET.fromstring(xml_text)
        except (RuntimeError, ET.ParseError, urllib.error.URLError):
            continue

        for node in root.findall(".//{*}loc"):
            loc = (node.text or "").strip()
            if not loc:
                continue

            loc_lower = loc.lower()
            if loc_lower.endswith(".xml") and "sitemap" in loc_lower:
                if loc not in visited_maps:
                    queue.append(loc)
                continue

            normalized = normalize_url(loc)
            if normalized:
                discovered.add(normalized)
                if len(discovered) >= max_urls:
                    break

    return sorted(discovered)


def discover_site_urls(max_urls: int) -> List[str]:
    seeds = {u for u in (normalize_url(url) for url in SEED_URLS) if u}
    from_sitemaps = set(discover_sitemap_urls(max_urls=max_urls))
    queue: List[str] = sorted(seeds | from_sitemaps)
    visited: Set[str] = set()
    discovered: Set[str] = set(queue)

    while queue and len(discovered) < max_urls:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)

        try:
            raw_html = fetch_text(url)
        except RuntimeError:
            continue

        for link in extract_links(raw_html, url):
            if link in discovered:
                continue
            discovered.add(link)
            if len(discovered) >= max_urls:
                break
            queue.append(link)

    # Keep this corpus focused on personal-site content pages.
    final_urls: List[str] = []
    for url in sorted(discovered):
        path = urllib.parse.urlparse(url).path.lower()
        if path.startswith("/tag/"):
            continue
        final_urls.append(url)
    return final_urls


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


def ingest_personal_site(root: Path, output_dir: Path, collected_at: str, max_pages: int, min_words: int) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    collected_date = collected_at[:10]
    urls = discover_site_urls(max_urls=max_pages)

    for url in urls:
        slug = source_slug_from_url(url)
        source_id = f"personal_site_{slug}"
        try:
            raw_html = fetch_text(url)
            title = extract_title(raw_html, fallback=slug.replace("-", " ").title())
            text = clean_html_to_text(raw_html)
            wc = word_count(text)
            if wc < min_words:
                rows.append(
                    {
                        "source_id": source_id,
                        "bucket": "self",
                        "source_group": "personal_site",
                        "title": title,
                        "url": url,
                        "published_at": "",
                        "collected_at": collected_at,
                        "file_path": "",
                        "word_count": str(wc),
                        "status": "skipped",
                        "notes": f"word_count<{min_words}",
                    }
                )
                continue

            filename = f"{collected_date}_{slug}.txt"
            relative_path = Path("blake") / "self" / "personal_site" / filename
            absolute_path = output_dir / filename

            write_document(
                absolute_path,
                {
                    "source_id": source_id,
                    "source_type": "personal_site_page",
                    "source_group": "personal_site",
                    "title": title,
                    "url": url,
                    "collected_at": collected_at,
                },
                text,
            )

            rows.append(
                {
                    "source_id": source_id,
                    "bucket": "self",
                    "source_group": "personal_site",
                    "title": title,
                    "url": url,
                    "published_at": "",
                    "collected_at": collected_at,
                    "file_path": str(relative_path),
                    "word_count": str(wc),
                    "status": "ok",
                    "notes": "",
                }
            )
        except Exception as exc:  # noqa: BLE001
            rows.append(
                {
                    "source_id": source_id,
                    "bucket": "self",
                    "source_group": "personal_site",
                    "title": slug.replace("-", " ").title(),
                    "url": url,
                    "published_at": "",
                    "collected_at": collected_at,
                    "file_path": "",
                    "word_count": "0",
                    "status": "error",
                    "notes": str(exc),
                }
            )

    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest Blake personal-site pages into text corpus.")
    parser.add_argument("--root", default="blake")
    parser.add_argument("--output-dir", default="blake/self/personal_site")
    parser.add_argument("--manifest-path", default="blake/manifest/personal_site_sources.csv")
    parser.add_argument("--max-pages", type=int, default=40)
    parser.add_argument("--min-words", type=int, default=120)
    args = parser.parse_args()

    root = Path(args.root)
    root.mkdir(parents=True, exist_ok=True)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = Path(args.manifest_path)

    collected_at = dt.datetime.now(dt.timezone.utc).isoformat()

    rows = ingest_personal_site(
        root=root,
        output_dir=output_dir,
        collected_at=collected_at,
        max_pages=args.max_pages,
        min_words=args.min_words,
    )

    write_manifest(rows, manifest_path)
    ok_count = sum(1 for row in rows if row["status"] == "ok")
    skipped_count = sum(1 for row in rows if row["status"] == "skipped")
    err_count = sum(1 for row in rows if row["status"] == "error")

    print(f"[personal_site] wrote manifest -> {manifest_path}")
    print(f"[personal_site] discovered rows -> {len(rows)}")
    print(f"[personal_site] ok={ok_count} skipped={skipped_count} error={err_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
