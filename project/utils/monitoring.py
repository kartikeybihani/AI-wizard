from __future__ import annotations

import csv
import json
import random
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from utils.apify_client import ApifyClient, extract_username, is_plausible_username, normalize_username

MONITOR_DIR = Path("data/monitor")
MONITOR_DB_PATH = MONITOR_DIR / "monitor.db"
QUEUE_PENDING_STATUS = "pending_comment_generation"
QUEUE_TRANSCRIBING_STATUS = "transcribing"
QUEUE_READY_REVIEW_STATUS = "ready_for_review"
QUEUE_FAILED_STATUS = "generation_failed"
QUEUE_SKIPPED_NON_VIDEO_STATUS = "skipped_non_video"
QUEUE_APPROVED_STATUS = "approved"
QUEUE_REJECTED_STATUS = "rejected"
QUEUE_SUBMITTED_STATUS = "submitted"

POST_ID_URL_PATTERN = re.compile(r"/(?:p|reel|tv)/([^/?#]+)/?")
MEDIA_TYPE_URL_PATTERN = re.compile(r"/(reel|tv|p)/[^/?#]+/?", flags=re.IGNORECASE)


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def chunked(values: Sequence[str], batch_size: int) -> Iterable[List[str]]:
    safe_batch_size = max(1, int(batch_size))
    for index in range(0, len(values), safe_batch_size):
        yield list(values[index : index + safe_batch_size])


def first_present(record: Dict[str, Any], keys: Sequence[str], default: Any = None) -> Any:
    for key in keys:
        value = record.get(key)
        if value is not None and value != "":
            return value
    return default


def normalize_timestamp(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric > 1e12:
            numeric = numeric / 1000.0
        try:
            return datetime.fromtimestamp(numeric, tz=timezone.utc).isoformat()
        except (ValueError, OSError, OverflowError):
            return ""

    text = str(value).strip()
    if not text:
        return ""

    if text.isdigit():
        return normalize_timestamp(int(text))

    return text


def derive_post_id_from_url(url: str) -> str:
    if not url:
        return ""
    match = POST_ID_URL_PATTERN.search(url)
    return match.group(1).strip() if match else ""


def _to_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(int(value))
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def infer_media_type(record: Dict[str, Any], url: str) -> str:
    url_text = str(url or "").strip().lower()
    match = MEDIA_TYPE_URL_PATTERN.search(url_text)
    if match:
        token = match.group(1).lower()
        if token in {"reel", "tv", "p"}:
            return token

    explicit = first_present(
        record,
        [
            "media_type",
            "mediaType",
            "__typename",
            "type",
            "postType",
            "productType",
        ],
        default="",
    )
    explicit_text = str(explicit or "").strip().lower()
    if explicit_text:
        if "reel" in explicit_text:
            return "reel"
        if "video" in explicit_text:
            return "video"
        if "image" in explicit_text or "photo" in explicit_text:
            return "image"
        if "carousel" in explicit_text or "sidecar" in explicit_text:
            return "carousel"

    video_like_keys = (
        "videoUrl",
        "video_url",
        "video_url_hd",
        "videoPlayCount",
        "video_view_count",
        "videoDuration",
        "video_versions",
        "videoVersions",
    )
    if any(record.get(key) not in (None, "", []) for key in video_like_keys):
        return "video"
    return "unknown"


def infer_is_video(record: Dict[str, Any], url: str, media_type: str) -> bool:
    url_text = str(url or "").strip().lower()
    if "/reel/" in url_text or "/tv/" in url_text:
        return True

    if media_type in {"reel", "tv", "video"}:
        return True

    signal_keys = (
        "isVideo",
        "is_video",
        "video",
        "hasVideo",
        "has_video",
    )
    for key in signal_keys:
        raw = record.get(key)
        parsed = _to_bool(raw)
        if parsed is not None:
            return parsed

    if any(
        record.get(key) not in (None, "", [])
        for key in (
            "videoUrl",
            "video_url",
            "video_url_hd",
            "videoPlayCount",
            "video_view_count",
            "videoDuration",
            "video_versions",
            "videoVersions",
        )
    ):
        return True
    return False


def normalize_post_record(record: Dict[str, Any], fallback_username: str = "") -> Optional[Dict[str, str]]:
    username = normalize_username(fallback_username or extract_username(record))
    if not username:
        return None

    url = str(first_present(record, ["url", "postUrl", "displayUrl"], default="") or "").strip()
    post_id = str(
        first_present(
            record,
            ["post_id", "postId", "id", "shortCode", "shortcode", "code"],
            default="",
        )
        or ""
    ).strip()
    if not post_id:
        post_id = derive_post_id_from_url(url)
    if not post_id:
        return None

    caption = str(first_present(record, ["caption", "text", "description", "title"], default="") or "")
    posted_at = normalize_timestamp(
        first_present(
            record,
            ["timestamp", "createdAt", "takenAtTimestamp", "taken_at", "publishedAt"],
            default="",
        )
    )
    media_type = infer_media_type(record=record, url=url)
    is_video = infer_is_video(record=record, url=url, media_type=media_type)

    return {
        "username": username,
        "post_id": post_id,
        "caption": caption,
        "url": url,
        "posted_at": posted_at,
        "is_video": "1" if is_video else "0",
        "media_type": media_type,
    }


def _append_post(posts_by_user: Dict[str, List[Dict[str, str]]], post: Dict[str, str], posts_per_account: int) -> None:
    username = post["username"]
    bucket = posts_by_user.setdefault(username, [])

    if any(existing.get("post_id") == post.get("post_id") for existing in bucket):
        return

    bucket.append(post)
    if len(bucket) > posts_per_account:
        del bucket[posts_per_account:]


def extract_posts_for_batch(
    items: Sequence[Dict[str, Any]],
    batch_usernames: Sequence[str],
    posts_per_account: int,
) -> List[Dict[str, str]]:
    allowed: Set[str] = {normalize_username(username) for username in batch_usernames if normalize_username(username)}
    posts_by_user: Dict[str, List[Dict[str, str]]] = {username: [] for username in allowed}
    capped_posts_per_account = max(1, int(posts_per_account))

    for item in items:
        if not isinstance(item, dict):
            continue

        owner = normalize_username(extract_username(item))

        nested_posts = item.get("posts")
        if isinstance(nested_posts, list):
            for raw_post in nested_posts:
                if not isinstance(raw_post, dict):
                    continue
                post = normalize_post_record(raw_post, fallback_username=owner)
                if not post or post["username"] not in allowed:
                    continue
                _append_post(posts_by_user, post, capped_posts_per_account)
            continue

        post = normalize_post_record(item, fallback_username=owner)
        if not post or post["username"] not in allowed:
            continue
        _append_post(posts_by_user, post, capped_posts_per_account)

    flattened: List[Dict[str, str]] = []
    for username in sorted(posts_by_user.keys()):
        flattened.extend(posts_by_user[username][:capped_posts_per_account])
    return flattened


def read_ranked_accounts_csv(path: Path, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"ranked accounts file not found: {path}")

    parsed_rows: List[Dict[str, Any]] = []
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            username = normalize_username(row.get("username", ""))
            if not username or not is_plausible_username(username):
                continue

            raw_final_score = str(row.get("final_score", "")).strip()
            try:
                final_score = float(raw_final_score) if raw_final_score else None
            except ValueError:
                final_score = None

            raw_rank = str(row.get("overall_rank", "")).strip()
            try:
                overall_rank = int(float(raw_rank)) if raw_rank else 10_000_000
            except ValueError:
                overall_rank = 10_000_000

            parsed_rows.append(
                {
                    "username": username,
                    "tier": str(row.get("tier", "") or "").strip().lower(),
                    "final_score": final_score,
                    "overall_rank": overall_rank,
                }
            )

    parsed_rows.sort(
        key=lambda row: (
            row.get("overall_rank", 10_000_000),
            -(row.get("final_score") if row.get("final_score") is not None else -1.0),
            row.get("username", ""),
        )
    )

    deduped: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for row in parsed_rows:
        username = row["username"]
        if username in seen:
            continue
        seen.add(username)
        deduped.append(
            {
                "username": username,
                "tier": row.get("tier", ""),
                "final_score": row.get("final_score"),
            }
        )

    if limit is not None and limit > 0:
        return deduped[:limit]
    return deduped


def load_mock_posts_fixture(path: Path) -> Dict[str, List[Dict[str, str]]]:
    if not path.exists():
        raise FileNotFoundError(f"mock fixture not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    posts_by_user: Dict[str, List[Dict[str, str]]] = {}

    if isinstance(payload, dict) and isinstance(payload.get("accounts"), list):
        for account in payload["accounts"]:
            if not isinstance(account, dict):
                continue
            username = normalize_username(account.get("username", ""))
            raw_posts = account.get("posts")
            if not username or not isinstance(raw_posts, list):
                continue
            for raw_post in raw_posts:
                if not isinstance(raw_post, dict):
                    continue
                post = normalize_post_record(raw_post, fallback_username=username)
                if post:
                    posts_by_user.setdefault(username, []).append(post)
    elif isinstance(payload, dict):
        for raw_username, raw_posts in payload.items():
            username = normalize_username(str(raw_username))
            if not username or not isinstance(raw_posts, list):
                continue
            for raw_post in raw_posts:
                if not isinstance(raw_post, dict):
                    continue
                post = normalize_post_record(raw_post, fallback_username=username)
                if post:
                    posts_by_user.setdefault(username, []).append(post)
    elif isinstance(payload, list):
        for raw_post in payload:
            if not isinstance(raw_post, dict):
                continue
            post = normalize_post_record(raw_post)
            if post:
                posts_by_user.setdefault(post["username"], []).append(post)
    else:
        raise ValueError("mock fixture must be object or list")

    for username in list(posts_by_user.keys()):
        dedup: Dict[str, Dict[str, str]] = {}
        for post in posts_by_user[username]:
            dedup.setdefault(post["post_id"], post)
        posts_by_user[username] = list(dedup.values())

    return posts_by_user


class MonitorStore:
    def __init__(self, db_path: Path = MONITOR_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.ensure_schema()

    def close(self) -> None:
        self.conn.close()

    def ensure_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tracked_accounts (
                username TEXT PRIMARY KEY,
                tier TEXT,
                final_score REAL,
                active INTEGER NOT NULL DEFAULT 1,
                source_run_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS seen_posts (
                post_id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                posted_at TEXT,
                first_seen_at TEXT NOT NULL,
                caption TEXT,
                url TEXT,
                is_video INTEGER NOT NULL DEFAULT 0,
                media_type TEXT NOT NULL DEFAULT 'unknown'
            );

            CREATE TABLE IF NOT EXISTS new_posts_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id TEXT NOT NULL UNIQUE,
                username TEXT NOT NULL,
                caption TEXT,
                url TEXT,
                posted_at TEXT,
                detected_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending_comment_generation',
                is_video INTEGER NOT NULL DEFAULT 0,
                media_type TEXT NOT NULL DEFAULT 'unknown'
            );

            CREATE TABLE IF NOT EXISTS monitor_runs (
                run_id TEXT PRIMARY KEY,
                mode TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                accounts_checked INTEGER NOT NULL DEFAULT 0,
                new_posts_found INTEGER NOT NULL DEFAULT 0,
                failed_accounts INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                error_summary TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_tracked_accounts_active
            ON tracked_accounts(active);

            CREATE INDEX IF NOT EXISTS idx_seen_posts_username
            ON seen_posts(username);

            CREATE INDEX IF NOT EXISTS idx_new_posts_queue_status_detected
            ON new_posts_queue(status, detected_at DESC);

            CREATE INDEX IF NOT EXISTS idx_monitor_runs_started
            ON monitor_runs(started_at DESC);

            CREATE TABLE IF NOT EXISTS post_processing (
                post_id TEXT PRIMARY KEY,
                queue_id INTEGER,
                status TEXT NOT NULL,
                transcript_text TEXT,
                transcript_source TEXT,
                transcript_model TEXT,
                post_context_json TEXT,
                generation_json TEXT,
                critic_json TEXT,
                selected_suggestion_id INTEGER,
                error_message TEXT,
                processing_started_at TEXT,
                processing_finished_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_post_processing_status
            ON post_processing(status, updated_at DESC);

            CREATE TABLE IF NOT EXISTS comment_suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id TEXT NOT NULL,
                label TEXT NOT NULL,
                comment TEXT NOT NULL,
                why_it_works TEXT,
                risk_level TEXT,
                critic_score REAL,
                critic_json TEXT,
                decision_status TEXT NOT NULL DEFAULT 'pending',
                edited_comment TEXT,
                final_comment TEXT,
                decision_reason TEXT,
                decision_at TEXT,
                submitted_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(post_id, label)
            );

            CREATE INDEX IF NOT EXISTS idx_comment_suggestions_post
            ON comment_suggestions(post_id, decision_status, updated_at DESC);
            """
        )
        self._ensure_column("seen_posts", "is_video", "is_video INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("seen_posts", "media_type", "media_type TEXT NOT NULL DEFAULT 'unknown'")
        self._ensure_column("new_posts_queue", "is_video", "is_video INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("new_posts_queue", "media_type", "media_type TEXT NOT NULL DEFAULT 'unknown'")
        self.conn.commit()

    def _ensure_column(self, table_name: str, column_name: str, ddl_fragment: str) -> None:
        rows = self.conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        existing = {str(row["name"]) for row in rows}
        if column_name in existing:
            return
        self.conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {ddl_fragment}")

    def upsert_tracked_accounts(
        self, accounts: Sequence[Dict[str, Any]], source_run_id: Optional[str] = None
    ) -> Dict[str, int]:
        now = now_utc_iso()
        existing_rows = self.conn.execute("SELECT username FROM tracked_accounts").fetchall()
        existing = {str(row["username"]) for row in existing_rows}

        inserted = 0
        updated = 0
        skipped = 0

        for account in accounts:
            username = normalize_username(str(account.get("username", "")))
            if not username or not is_plausible_username(username):
                skipped += 1
                continue

            raw_final_score = account.get("final_score")
            try:
                final_score = float(raw_final_score) if raw_final_score is not None else None
            except (TypeError, ValueError):
                final_score = None

            tier = str(account.get("tier", "") or "").strip().lower()
            self.conn.execute(
                """
                INSERT INTO tracked_accounts (
                    username, tier, final_score, active, source_run_id, created_at, updated_at
                ) VALUES (?, ?, ?, 1, ?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    tier = excluded.tier,
                    final_score = excluded.final_score,
                    source_run_id = COALESCE(excluded.source_run_id, tracked_accounts.source_run_id),
                    updated_at = excluded.updated_at
                """,
                (username, tier, final_score, source_run_id, now, now),
            )

            if username in existing:
                updated += 1
            else:
                inserted += 1
                existing.add(username)

        self.conn.commit()
        return {"inserted": inserted, "updated": updated, "skipped": skipped}

    def set_tracked_account_active(self, username: str, active: bool) -> None:
        now = now_utc_iso()
        self.conn.execute(
            """
            UPDATE tracked_accounts
            SET active = ?, updated_at = ?
            WHERE username = ?
            """,
            (1 if active else 0, now, normalize_username(username)),
        )
        self.conn.commit()

    def get_tracked_account(self, username: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            """
            SELECT username, tier, final_score, active, source_run_id, created_at, updated_at
            FROM tracked_accounts
            WHERE username = ?
            """,
            (normalize_username(username),),
        ).fetchone()
        if not row:
            return None
        return dict(row)

    def list_active_usernames(self, limit: Optional[int] = None) -> List[str]:
        query = """
            SELECT username
            FROM tracked_accounts
            WHERE active = 1
            ORDER BY COALESCE(final_score, -1) DESC, username ASC
        """
        params: List[Any] = []
        if limit is not None and limit > 0:
            query += " LIMIT ?"
            params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        return [str(row["username"]) for row in rows]

    def insert_new_posts(
        self,
        posts: Sequence[Dict[str, str]],
        detected_at: Optional[str] = None,
        status: str = QUEUE_PENDING_STATUS,
    ) -> List[Dict[str, str]]:
        metrics = self.insert_new_posts_with_metrics(posts=posts, detected_at=detected_at, status=status)
        return list(metrics["queued_posts"])

    def insert_new_posts_with_metrics(
        self,
        posts: Sequence[Dict[str, str]],
        detected_at: Optional[str] = None,
        status: str = QUEUE_PENDING_STATUS,
    ) -> Dict[str, Any]:
        stamp = detected_at or now_utc_iso()
        inserted_posts: List[Dict[str, str]] = []
        posts_seen_total = 0
        posts_queued_video = 0
        posts_skipped_non_video = 0

        for post in posts:
            username = normalize_username(str(post.get("username", "")))
            post_id = str(post.get("post_id", "")).strip()
            if not username or not post_id:
                continue

            caption = str(post.get("caption", "") or "")
            url = str(post.get("url", "") or "")
            posted_at = str(post.get("posted_at", "") or "")
            media_type = str(post.get("media_type", "") or "unknown").strip().lower() or "unknown"
            is_video_raw = post.get("is_video", "")
            is_video = _to_bool(is_video_raw)
            if is_video is None:
                is_video = infer_is_video(record=post, url=url, media_type=media_type)

            cursor = self.conn.execute(
                """
                INSERT OR IGNORE INTO seen_posts (
                    post_id, username, posted_at, first_seen_at, caption, url, is_video, media_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (post_id, username, posted_at, stamp, caption, url, 1 if is_video else 0, media_type),
            )

            if cursor.rowcount != 1:
                continue

            posts_seen_total += 1
            if not is_video:
                posts_skipped_non_video += 1
                continue

            self.conn.execute(
                """
                INSERT OR IGNORE INTO new_posts_queue (
                    post_id, username, caption, url, posted_at, detected_at, status, is_video, media_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (post_id, username, caption, url, posted_at, stamp, status, 1 if is_video else 0, media_type),
            )
            inserted_posts.append(
                {
                    "username": username,
                    "post_id": post_id,
                    "caption": caption,
                    "url": url,
                    "posted_at": posted_at,
                    "detected_at": stamp,
                    "status": status,
                    "is_video": "1" if is_video else "0",
                    "media_type": media_type,
                }
            )
            posts_queued_video += 1

        self.conn.commit()
        return {
            "queued_posts": inserted_posts,
            "posts_seen_total": posts_seen_total,
            "posts_queued_video": posts_queued_video,
            "posts_skipped_non_video": posts_skipped_non_video,
        }

    def update_queue_status(self, post_id: str, status: str) -> None:
        self.conn.execute(
            """
            UPDATE new_posts_queue
            SET status = ?
            WHERE post_id = ?
            """,
            (status, str(post_id).strip()),
        )
        self.conn.commit()

    def list_queue_posts_for_generation(
        self,
        limit: int = 10,
        statuses: Optional[Sequence[str]] = None,
        post_ids: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, int(limit))
        filter_statuses = list(statuses or [QUEUE_PENDING_STATUS, QUEUE_FAILED_STATUS])
        where_parts = ["is_video = 1"]
        params: List[Any] = []

        if filter_statuses:
            placeholders = ",".join("?" for _ in filter_statuses)
            where_parts.append(f"status IN ({placeholders})")
            params.extend(filter_statuses)

        if post_ids:
            cleaned_ids = [str(item).strip() for item in post_ids if str(item).strip()]
            if cleaned_ids:
                placeholders = ",".join("?" for _ in cleaned_ids)
                where_parts.append(f"post_id IN ({placeholders})")
                params.extend(cleaned_ids)

        query = f"""
            SELECT id, post_id, username, caption, url, posted_at, detected_at, status, is_video, media_type
            FROM new_posts_queue
            WHERE {" AND ".join(where_parts)}
            ORDER BY detected_at DESC
            LIMIT ?
        """
        params.append(safe_limit)
        rows = self.conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def upsert_post_processing(
        self,
        post_id: str,
        queue_id: Optional[int],
        status: str,
        transcript_text: str = "",
        transcript_source: str = "",
        transcript_model: str = "",
        post_context_json: str = "",
        generation_json: str = "",
        critic_json: str = "",
        selected_suggestion_id: Optional[int] = None,
        error_message: str = "",
        processing_started_at: str = "",
        processing_finished_at: str = "",
    ) -> None:
        now = now_utc_iso()
        self.conn.execute(
            """
            INSERT INTO post_processing (
                post_id, queue_id, status, transcript_text, transcript_source, transcript_model,
                post_context_json, generation_json, critic_json, selected_suggestion_id,
                error_message, processing_started_at, processing_finished_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(post_id) DO UPDATE SET
                queue_id = COALESCE(excluded.queue_id, post_processing.queue_id),
                status = excluded.status,
                transcript_text = excluded.transcript_text,
                transcript_source = excluded.transcript_source,
                transcript_model = excluded.transcript_model,
                post_context_json = excluded.post_context_json,
                generation_json = excluded.generation_json,
                critic_json = excluded.critic_json,
                selected_suggestion_id = COALESCE(excluded.selected_suggestion_id, post_processing.selected_suggestion_id),
                error_message = excluded.error_message,
                processing_started_at = excluded.processing_started_at,
                processing_finished_at = excluded.processing_finished_at,
                updated_at = excluded.updated_at
            """,
            (
                str(post_id).strip(),
                int(queue_id) if queue_id is not None else None,
                status,
                transcript_text,
                transcript_source,
                transcript_model,
                post_context_json,
                generation_json,
                critic_json,
                int(selected_suggestion_id) if selected_suggestion_id is not None else None,
                error_message,
                processing_started_at,
                processing_finished_at,
                now,
                now,
            ),
        )
        self.conn.commit()

    def replace_comment_suggestions(
        self,
        post_id: str,
        suggestions: Sequence[Dict[str, Any]],
        selected_label: str = "",
        critic_json: str = "",
        critic_score: Optional[float] = None,
    ) -> Optional[int]:
        now = now_utc_iso()
        cleaned_post_id = str(post_id).strip()
        self.conn.execute("DELETE FROM comment_suggestions WHERE post_id = ?", (cleaned_post_id,))
        selected_id: Optional[int] = None
        for suggestion in suggestions:
            label = str(suggestion.get("label", "") or "").strip() or "candidate"
            comment = str(suggestion.get("comment", "") or "").strip()
            if not comment:
                continue
            why_it_works = str(suggestion.get("why_it_works", "") or "").strip()
            risk_level = str(suggestion.get("risk_level", "") or "").strip()
            cursor = self.conn.execute(
                """
                INSERT INTO comment_suggestions (
                    post_id, label, comment, why_it_works, risk_level,
                    critic_score, critic_json, decision_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    cleaned_post_id,
                    label,
                    comment,
                    why_it_works,
                    risk_level,
                    critic_score,
                    critic_json,
                    now,
                    now,
                ),
            )
            inserted_id = int(cursor.lastrowid)
            if selected_label and label == selected_label:
                selected_id = inserted_id
        self.conn.commit()
        return selected_id

    def create_monitor_run(self, run_id: str, mode: str, started_at: Optional[str] = None) -> None:
        self.conn.execute(
            """
            INSERT INTO monitor_runs (
                run_id, mode, started_at, status
            ) VALUES (?, ?, ?, ?)
            """,
            (run_id, mode, started_at or now_utc_iso(), "running"),
        )
        self.conn.commit()

    def finalize_monitor_run(
        self,
        run_id: str,
        status: str,
        ended_at: Optional[str],
        accounts_checked: int,
        new_posts_found: int,
        failed_accounts: int,
        error_summary: str = "",
    ) -> None:
        self.conn.execute(
            """
            UPDATE monitor_runs
            SET status = ?,
                ended_at = ?,
                accounts_checked = ?,
                new_posts_found = ?,
                failed_accounts = ?,
                error_summary = ?
            WHERE run_id = ?
            """,
            (
                status,
                ended_at or now_utc_iso(),
                max(0, int(accounts_checked)),
                max(0, int(new_posts_found)),
                max(0, int(failed_accounts)),
                error_summary.strip(),
                run_id,
            ),
        )
        self.conn.commit()

    def count_rows(self, table_name: str) -> int:
        if table_name not in {"tracked_accounts", "seen_posts", "new_posts_queue", "monitor_runs"}:
            raise ValueError(f"unsupported table name: {table_name}")
        row = self.conn.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
        return int(row["count"] if row else 0)


def compute_retry_delay(
    attempt_index: int,
    retry_base_seconds: float,
    retry_jitter_seconds: float,
    rng: Optional[random.Random] = None,
) -> float:
    random_generator = rng or random
    base = max(0.0, float(retry_base_seconds)) * (2**max(0, attempt_index))
    jitter = random_generator.uniform(0.0, max(0.0, float(retry_jitter_seconds)))
    return base + jitter


def fetch_live_batch_posts(
    client: ApifyClient,
    actor_id: str,
    batch_usernames: Sequence[str],
    posts_per_account: int,
    wait_seconds: int,
) -> List[Dict[str, str]]:
    actor_input = {
        "username": list(batch_usernames),
        "resultsLimit": max(1, int(posts_per_account)),
        "dataDetailLevel": "detailedData",
    }
    dataset_limit = max(200, len(batch_usernames) * max(1, int(posts_per_account)) * 4)
    items = client.run_actor_and_fetch_items(
        actor_id=actor_id,
        actor_input=actor_input,
        wait_for_finish_seconds=max(1, int(wait_seconds)),
        dataset_limit=dataset_limit,
    )
    return extract_posts_for_batch(items, batch_usernames, posts_per_account=posts_per_account)


def build_mock_batch_fetcher(
    fixture_posts_by_user: Dict[str, List[Dict[str, str]]],
    posts_per_account: int,
    failing_usernames: Optional[Set[str]] = None,
) -> Callable[[Sequence[str]], List[Dict[str, str]]]:
    fail_set = {normalize_username(username) for username in (failing_usernames or set())}
    safe_posts_per_account = max(1, int(posts_per_account))

    def fetch(batch_usernames: Sequence[str]) -> List[Dict[str, str]]:
        normalized_batch = [normalize_username(username) for username in batch_usernames]
        for username in normalized_batch:
            if username in fail_set:
                raise RuntimeError(f"simulated batch failure for username '{username}'")

        posts: List[Dict[str, str]] = []
        for username in normalized_batch:
            for post in fixture_posts_by_user.get(username, [])[:safe_posts_per_account]:
                posts.append(post)
        return posts

    return fetch


def run_monitor_batches(
    store: MonitorStore,
    usernames: Sequence[str],
    fetch_batch: Callable[[Sequence[str]], Sequence[Dict[str, str]]],
    batch_size: int = 25,
    delay_seconds: float = 2.5,
    max_retries: int = 2,
    retry_base_seconds: float = 2.0,
    retry_jitter_seconds: float = 1.0,
    sleep_fn: Callable[[float], None] = time.sleep,
    rng: Optional[random.Random] = None,
) -> Dict[str, Any]:
    safe_batch_size = max(1, min(50, int(batch_size)))
    batches = list(chunked(list(usernames), safe_batch_size))

    accounts_checked = 0
    failed_accounts = 0
    failed_batches = 0
    errors: List[str] = []
    inserted_posts: List[Dict[str, str]] = []
    posts_seen_total = 0
    posts_queued_video = 0
    posts_skipped_non_video = 0

    for batch_index, batch in enumerate(batches):
        accounts_checked += len(batch)

        batch_posts: Sequence[Dict[str, str]] = []
        batch_success = False
        last_error = ""

        for attempt_index in range(max(0, int(max_retries)) + 1):
            try:
                batch_posts = fetch_batch(batch)
                batch_success = True
                break
            except Exception as exc:  # pragma: no cover - explicit runtime safety branch
                last_error = str(exc)
                if attempt_index >= max_retries:
                    break
                sleep_seconds = compute_retry_delay(
                    attempt_index=attempt_index,
                    retry_base_seconds=retry_base_seconds,
                    retry_jitter_seconds=retry_jitter_seconds,
                    rng=rng,
                )
                if sleep_seconds > 0:
                    sleep_fn(sleep_seconds)

        if not batch_success:
            failed_batches += 1
            failed_accounts += len(batch)
            errors.append(
                f"batch {batch_index + 1}/{len(batches)} failed ({len(batch)} accounts): {last_error}"
            )
        else:
            metrics = store.insert_new_posts_with_metrics(batch_posts)
            inserted_posts.extend(list(metrics["queued_posts"]))
            posts_seen_total += int(metrics["posts_seen_total"])
            posts_queued_video += int(metrics["posts_queued_video"])
            posts_skipped_non_video += int(metrics["posts_skipped_non_video"])

        if batch_index < len(batches) - 1 and delay_seconds > 0:
            sleep_fn(delay_seconds)

    return {
        "accounts_checked": accounts_checked,
        "failed_accounts": failed_accounts,
        "failed_batches": failed_batches,
        "new_posts": inserted_posts,
        "new_posts_found": len(inserted_posts),
        "posts_seen_total": posts_seen_total,
        "posts_queued_video": posts_queued_video,
        "posts_skipped_non_video": posts_skipped_non_video,
        "errors": errors,
        "batches_total": len(batches),
    }


def write_new_posts_csv(path: Path, rows: Sequence[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "username",
                "post_id",
                "caption",
                "url",
                "posted_at",
                "detected_at",
                "status",
                "is_video",
                "media_type",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "username": str(row.get("username", "")),
                    "post_id": str(row.get("post_id", "")),
                    "caption": str(row.get("caption", "")),
                    "url": str(row.get("url", "")),
                    "posted_at": str(row.get("posted_at", "")),
                    "detected_at": str(row.get("detected_at", "")),
                    "status": str(row.get("status", "")),
                    "is_video": str(row.get("is_video", "")),
                    "media_type": str(row.get("media_type", "")),
                }
            )


def write_run_report(path: Path, report: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
