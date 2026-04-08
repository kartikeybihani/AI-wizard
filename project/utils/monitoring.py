from __future__ import annotations

import csv
import json
import random
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set

from utils.apify_client import ApifyClient, extract_username, is_plausible_username, normalize_username

MONITOR_DIR = Path("data/monitor")
MONITOR_DB_PATH = MONITOR_DIR / "monitor.db"
QUEUE_PENDING_STATUS = "pending_comment_generation"

POST_ID_URL_PATTERN = re.compile(r"/(?:p|reel|tv)/([^/?#]+)/?")


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

    return {
        "username": username,
        "post_id": post_id,
        "caption": caption,
        "url": url,
        "posted_at": posted_at,
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
                url TEXT
            );

            CREATE TABLE IF NOT EXISTS new_posts_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id TEXT NOT NULL UNIQUE,
                username TEXT NOT NULL,
                caption TEXT,
                url TEXT,
                posted_at TEXT,
                detected_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending_comment_generation'
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
            """
        )
        self.conn.commit()

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
        stamp = detected_at or now_utc_iso()
        inserted_posts: List[Dict[str, str]] = []

        for post in posts:
            username = normalize_username(str(post.get("username", "")))
            post_id = str(post.get("post_id", "")).strip()
            if not username or not post_id:
                continue

            caption = str(post.get("caption", "") or "")
            url = str(post.get("url", "") or "")
            posted_at = str(post.get("posted_at", "") or "")

            cursor = self.conn.execute(
                """
                INSERT OR IGNORE INTO seen_posts (
                    post_id, username, posted_at, first_seen_at, caption, url
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (post_id, username, posted_at, stamp, caption, url),
            )

            if cursor.rowcount != 1:
                continue

            self.conn.execute(
                """
                INSERT OR IGNORE INTO new_posts_queue (
                    post_id, username, caption, url, posted_at, detected_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (post_id, username, caption, url, posted_at, stamp, status),
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
                }
            )

        self.conn.commit()
        return inserted_posts

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
            inserted_posts.extend(store.insert_new_posts(batch_posts))

        if batch_index < len(batches) - 1 and delay_seconds > 0:
            sleep_fn(delay_seconds)

    return {
        "accounts_checked": accounts_checked,
        "failed_accounts": failed_accounts,
        "failed_batches": failed_batches,
        "new_posts": inserted_posts,
        "new_posts_found": len(inserted_posts),
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
                }
            )


def write_run_report(path: Path, report: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)

