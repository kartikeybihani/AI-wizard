#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import time
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple
from urllib.parse import urlparse, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from dateutil import parser as date_parser


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

DEFAULT_URLS: List[str] = [
    "https://en.wikipedia.org/wiki/Blake_Mycoskie",
    "https://www.entrepreneur.com/business-news/who-is-blake-mycoskie-how-he-created-toms-shoes-brand/220350",
    "https://tomsaustralia.com.au/pages/blakes-bio",
    "https://newsletter.storytellingforentrepreneurs.com/p/the-625m-brand-built-on-one-simple-story",
    "https://newsroom.haas.berkeley.edu/toms-founder-blake-mycoskie-on-leading-with-authenticity/",
    "https://www.businessoffashion.com/people/blake-mycoskie/",
    "https://cagspeakers.com/blake-mycoskie/",
    "https://people.com/toms-founder-blake-mycoskie-shares-depression-struggle-enough-bracelet-charity-11879137",
    "https://www.youtube.com/watch?v=jpM7pbgLK_k",
    "https://www.cbs.com/shows/video/6_ptThvqilzPRCAIRSy55doDsxX91KwG/",
    "https://www.edmylett.com/podcast/blake-mycoskie-the-business-of-changing-lives",
    "https://lifestylesmagazine.com/latest-news/100-million-commitment-to-psychedelic-research-for-mental-health-treatments-by-46-year-old-entrepreneur-blake-mycoskie/",
    "https://blakemycoskie.com",
    "https://finance.yahoo.com/news/toms-founder-blake-mycoskie-launches-140000049.html",
    "https://weareenough.co/blogs/stories/enough-on-wwd",
    "https://www.modernluxury.com/blake-mycoskie-toms/",
    "https://publicaffairs.missouristate.edu/Convocation/BlakeMycoskie.htm",
    "https://abc.com/shows/shark-tank/cast/blake-mycoskie",
    "https://www.linkedin.com/in/blakemycoskie",
]

IGNORE_TAGS = {
    "script",
    "style",
    "noscript",
    "svg",
    "canvas",
    "iframe",
    "form",
    "button",
    "input",
    "textarea",
    "select",
    "header",
    "footer",
    "nav",
    "aside",
}

NOISE_PATTERNS = [
    re.compile(r"^(subscribe|sign in|log in|menu)$", re.IGNORECASE),
    re.compile(r"^(share|print|next|previous)$", re.IGNORECASE),
    re.compile(r"^cookie", re.IGNORECASE),
]

DATE_KEYS = {
    "article:published_time",
    "og:published_time",
    "published_time",
    "publish-date",
    "pubdate",
    "date",
    "dc.date",
    "dc.date.issued",
    "sailthru.date",
    "parsely-pub-date",
    "article.published",
    "article:modified_time",
    "lastmod",
}

WORD_RE = re.compile(r"\b\w+\b")
WS_RE = re.compile(r"[ \t]+")
MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


def slugify(value: str, max_len: int = 80) -> str:
    cleaned = value.strip().lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", cleaned)
    cleaned = cleaned.strip("-")
    if not cleaned:
        return "untitled"
    return cleaned[:max_len].rstrip("-")


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = parts.scheme or "https"
    netloc = parts.netloc.lower()
    path = parts.path or "/"
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def normalize_domain(host: str) -> str:
    host = host.lower().strip()
    if host.startswith("www."):
        host = host[4:]
    return host


def word_count(text: str) -> int:
    return len(WORD_RE.findall(text))


def clean_text_lines(text: str) -> str:
    lines: List[str] = []
    seen_recent: Set[str] = set()
    for raw_line in text.replace("\r", "\n").split("\n"):
        line = WS_RE.sub(" ", raw_line).strip()
        if not line:
            continue
        lowered = line.lower()
        if any(pattern.search(line) for pattern in NOISE_PATTERNS):
            continue
        if len(line) < 2:
            continue
        if lowered in seen_recent:
            continue
        lines.append(line)
        seen_recent.add(lowered)
        if len(seen_recent) > 3000:
            seen_recent.clear()
    cleaned = "\n".join(lines).strip()
    cleaned = MULTI_NEWLINE_RE.sub("\n\n", cleaned)
    return cleaned


def looks_like_content_tag(tag) -> bool:  # type: ignore[no-untyped-def]
    if tag is None:
        return False
    if tag.name not in {"article", "main", "section", "div"}:
        return False
    attrs = " ".join(tag.get("class", [])) + " " + str(tag.get("id", ""))
    attrs = attrs.lower()
    signals = (
        "article",
        "content",
        "entry",
        "post",
        "story",
        "body",
        "main",
    )
    return any(signal in attrs for signal in signals)


def best_content_node(soup: BeautifulSoup):
    body = soup.body or soup
    candidates = []

    for node in soup.find_all(["article", "main"]):
        text = clean_text_lines(node.get_text("\n", strip=True))
        wc = word_count(text)
        if wc > 0:
            candidates.append((wc, node))

    for node in soup.find_all(looks_like_content_tag):
        text = clean_text_lines(node.get_text("\n", strip=True))
        wc = word_count(text)
        if wc > 0:
            candidates.append((wc, node))

    if not candidates:
        return body
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def extract_title(soup: BeautifulSoup, fallback: str) -> str:
    meta_props = [
        ("property", "og:title"),
        ("name", "twitter:title"),
        ("name", "title"),
    ]
    for key, value in meta_props:
        node = soup.find("meta", attrs={key: value})
        if node and node.get("content"):
            text = WS_RE.sub(" ", str(node["content"])).strip()
            if text:
                return text
    if soup.title and soup.title.text:
        text = WS_RE.sub(" ", soup.title.text).strip()
        if text:
            return text
    return fallback


def _iter_json_nodes(obj):  # type: ignore[no-untyped-def]
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _iter_json_nodes(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_json_nodes(item)


def extract_published_at(soup: BeautifulSoup) -> str:
    for meta in soup.find_all("meta"):
        key = (meta.get("property") or meta.get("name") or "").strip().lower()
        if key in DATE_KEYS and meta.get("content"):
            value = str(meta.get("content", "")).strip()
            if value:
                return value

    time_node = soup.find("time")
    if time_node and time_node.get("datetime"):
        value = str(time_node.get("datetime", "")).strip()
        if value:
            return value

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text(strip=True)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception:  # noqa: BLE001
            continue
        for node in _iter_json_nodes(payload):
            for key in ("datePublished", "dateCreated", "uploadDate", "dateModified"):
                value = node.get(key) if isinstance(node, dict) else None
                if isinstance(value, str) and value.strip():
                    return value.strip()

    return ""


def to_date_key(value: str) -> str:
    if not value:
        return "unknown-date"
    value = value.strip()
    if re.fullmatch(r"\d{8}", value):
        return f"{value[0:4]}-{value[4:6]}-{value[6:8]}"
    try:
        parsed = date_parser.parse(value)
        return parsed.strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        pass
    if "T" in value:
        return value.split("T", 1)[0][:10]
    return value[:10] if len(value) >= 10 else "unknown-date"


def write_document(path: Path, metadata: Dict[str, str], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    for key in sorted(metadata.keys()):
        value = str(metadata[key]).replace("\n", " ").strip()
        lines.append(f"{key}: {value}")
    lines.extend(["---", "", body.strip(), ""])
    path.write_text("\n".join(lines), encoding="utf-8")


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


def load_urls(urls_file: Optional[str]) -> List[str]:
    if not urls_file:
        return list(DEFAULT_URLS)
    path = Path(urls_file)
    urls: List[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        candidate = line.strip()
        if not candidate or candidate.startswith("#"):
            continue
        urls.append(candidate)
    return urls


def fetch_html(url: str, retries: int = 3, delay_seconds: float = 1.5) -> Tuple[str, str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    last_exc: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=60) as response:
                final_url = response.geturl()
                content = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
                html = content.decode(charset, errors="replace")
                return final_url, html
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < retries:
                time.sleep(delay_seconds * attempt)
    raise RuntimeError(f"Failed to fetch URL after {retries} attempts: {url}") from last_exc


def ingest_articles(
    output_dir: Path,
    collected_at: str,
    urls: Sequence[str],
    min_words: int,
) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    used_source_ids: Set[str] = set()

    deduped_urls: List[str] = []
    seen_urls: Set[str] = set()
    for raw_url in urls:
        normalized = normalize_url(raw_url)
        if normalized in seen_urls:
            continue
        seen_urls.add(normalized)
        deduped_urls.append(normalized)

    for url in deduped_urls:
        parsed = urlparse(url)
        domain = normalize_domain(parsed.netloc)
        group = slugify(domain.replace(".", "-"), max_len=50)
        fallback_slug = slugify(parsed.path.strip("/").replace("/", "-"), max_len=70) or "home"
        fallback_title = fallback_slug.replace("-", " ").title()

        try:
            final_url, html = fetch_html(url)

            soup = BeautifulSoup(html, "html.parser")

            for node in soup.find_all(IGNORE_TAGS):
                node.decompose()

            for node in soup.select("[aria-hidden='true']"):
                node.decompose()

            content_node = best_content_node(soup)
            body_text = clean_text_lines(content_node.get_text("\n", strip=True))
            wc = word_count(body_text)

            title = extract_title(soup, fallback=fallback_title)
            published_at = extract_published_at(soup)
            date_key = to_date_key(published_at)
            page_slug = slugify(title, max_len=70) or fallback_slug

            base_source_id = f"article_{group}_{page_slug}"
            source_id = base_source_id
            if source_id in used_source_ids:
                suffix = hashlib.sha1(final_url.encode("utf-8")).hexdigest()[:8]
                source_id = f"{base_source_id}_{suffix}"
            used_source_ids.add(source_id)

            if wc < min_words:
                rows.append(
                    {
                        "source_id": source_id,
                        "bucket": "articles",
                        "source_group": group,
                        "title": title,
                        "url": final_url,
                        "published_at": published_at,
                        "collected_at": collected_at,
                        "file_path": "",
                        "word_count": str(wc),
                        "status": "skipped",
                        "notes": f"word_count<{min_words}",
                    }
                )
                continue

            filename = f"{date_key}_{group}_{page_slug}.txt"
            relative_path = Path("blake") / "articles" / filename
            absolute_path = output_dir / filename

            write_document(
                absolute_path,
                {
                    "source_id": source_id,
                    "source_type": "web_article",
                    "source_group": group,
                    "title": title,
                    "url": final_url,
                    "published_at": published_at,
                    "collected_at": collected_at,
                },
                body_text,
            )

            rows.append(
                {
                    "source_id": source_id,
                    "bucket": "articles",
                    "source_group": group,
                    "title": title,
                    "url": final_url,
                    "published_at": published_at,
                    "collected_at": collected_at,
                    "file_path": str(relative_path),
                    "word_count": str(wc),
                    "status": "ok",
                    "notes": "",
                }
            )
        except Exception as exc:  # noqa: BLE001
            source_id = f"article_{group}_{fallback_slug}"
            if source_id in used_source_ids:
                suffix = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
                source_id = f"{source_id}_{suffix}"
            used_source_ids.add(source_id)

            rows.append(
                {
                    "source_id": source_id,
                    "bucket": "articles",
                    "source_group": group,
                    "title": fallback_title,
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
    parser = argparse.ArgumentParser(description="Ingest Blake article links into blake/articles.")
    parser.add_argument("--output-dir", default="blake/articles")
    parser.add_argument("--manifest-path", default="blake/manifest/articles_sources.csv")
    parser.add_argument("--urls-file", default="")
    parser.add_argument("--min-words", type=int, default=40)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = Path(args.manifest_path)
    collected_at = dt.datetime.now(dt.timezone.utc).isoformat()

    urls = load_urls(args.urls_file or None)
    rows = ingest_articles(
        output_dir=output_dir,
        collected_at=collected_at,
        urls=urls,
        min_words=args.min_words,
    )
    write_manifest(rows, manifest_path)

    ok_count = sum(1 for row in rows if row["status"] == "ok")
    skipped_count = sum(1 for row in rows if row["status"] == "skipped")
    err_count = sum(1 for row in rows if row["status"] == "error")

    print(f"[articles] wrote manifest -> {manifest_path}")
    print(f"[articles] total URLs -> {len(rows)}")
    print(f"[articles] ok={ok_count} skipped={skipped_count} error={err_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
