from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Set

from utils.apify_client import ApifyClient
from utils.monitoring import (
    MONITOR_DB_PATH,
    MONITOR_DIR,
    MonitorStore,
    build_mock_batch_fetcher,
    fetch_live_batch_posts,
    load_mock_posts_fixture,
    now_utc_iso,
    run_monitor_batches,
    write_new_posts_csv,
    write_run_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ongoing post monitoring and queue new posts.")
    parser.add_argument("--mode", choices=["live", "mock"], default="live")
    parser.add_argument("--db-path", default=str(MONITOR_DB_PATH))
    parser.add_argument("--output-dir", default=str(MONITOR_DIR))
    parser.add_argument("--limit-accounts", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--posts-per-account", type=int, default=5)
    parser.add_argument("--delay-seconds", type=float, default=2.5)
    parser.add_argument("--wait-seconds", type=int, default=240)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--retry-base-seconds", type=float, default=2.0)
    parser.add_argument("--retry-jitter-seconds", type=float, default=1.0)
    parser.add_argument("--actor-id", default=os.getenv("APIFY_POST_ACTOR_ID", ""))
    parser.add_argument("--fixture", default="data/monitor/mock_posts.json")
    parser.add_argument(
        "--auto-generate-comments",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Automatically run local reel transcription + comment generation after monitor run.",
    )
    parser.add_argument("--generate-limit", type=int, default=10)
    parser.add_argument("--whisper-model", default=os.getenv("WHISPER_MODEL", "base.en"))
    parser.add_argument("--openrouter-model", default=os.getenv("OPENROUTER_MODEL", ""))
    parser.add_argument("--blake-bible", default="")
    parser.add_argument("--engage-script", default="engage_generate.py")
    parser.add_argument(
        "--mock-fail-usernames",
        default="",
        help="Comma-separated usernames that should fail in mock mode (for failure simulation).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_id = str(uuid.uuid4())
    started_at = now_utc_iso()
    started_epoch = time.time()

    store = MonitorStore(db_path=Path(args.db_path))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    store.create_monitor_run(run_id=run_id, mode=args.mode, started_at=started_at)

    status = "succeeded"
    accounts_checked = 0
    new_posts_found = 0
    failed_accounts = 0
    posts_seen_total = 0
    posts_queued_video = 0
    posts_skipped_non_video = 0
    errors: List[str] = []
    new_posts_rows: List[Dict[str, str]] = []
    generation_summary: Dict[str, Any] = {"enabled": bool(args.auto_generate_comments), "executed": False}

    try:
        limit_accounts = args.limit_accounts if args.limit_accounts and args.limit_accounts > 0 else None
        usernames = store.list_active_usernames(limit=limit_accounts)

        if not usernames:
            print("[monitor_run] no active tracked accounts found")
            monitor_result: Dict[str, Any] = {
                "accounts_checked": 0,
                "failed_accounts": 0,
                "failed_batches": 0,
                "new_posts_found": 0,
                "new_posts": [],
                "errors": [],
                "batches_total": 0,
            }
        else:
            if args.mode == "live":
                token = os.getenv("APIFY_TOKEN", "").strip()
                actor_id = args.actor_id.strip()
                if not token:
                    raise RuntimeError("APIFY_TOKEN is required for --mode live")
                if not actor_id:
                    raise RuntimeError("APIFY_POST_ACTOR_ID (or --actor-id) is required for --mode live")

                client = ApifyClient(token=token)

                def fetch_batch(batch_usernames: List[str]) -> List[Dict[str, str]]:
                    return fetch_live_batch_posts(
                        client=client,
                        actor_id=actor_id,
                        batch_usernames=batch_usernames,
                        posts_per_account=args.posts_per_account,
                        wait_seconds=args.wait_seconds,
                    )

            else:
                fixture_posts = load_mock_posts_fixture(Path(args.fixture))
                failing_usernames: Set[str] = {
                    item.strip().lower()
                    for item in args.mock_fail_usernames.split(",")
                    if item.strip()
                }
                fetch_batch = build_mock_batch_fetcher(
                    fixture_posts_by_user=fixture_posts,
                    posts_per_account=args.posts_per_account,
                    failing_usernames=failing_usernames,
                )

            monitor_result = run_monitor_batches(
                store=store,
                usernames=usernames,
                fetch_batch=fetch_batch,
                batch_size=max(1, min(50, args.batch_size)),
                delay_seconds=max(0.0, args.delay_seconds),
                max_retries=max(0, args.max_retries),
                retry_base_seconds=max(0.0, args.retry_base_seconds),
                retry_jitter_seconds=max(0.0, args.retry_jitter_seconds),
            )

        accounts_checked = int(monitor_result["accounts_checked"])
        failed_accounts = int(monitor_result["failed_accounts"])
        new_posts_rows = list(monitor_result["new_posts"])
        new_posts_found = int(monitor_result["new_posts_found"])
        posts_seen_total = int(monitor_result.get("posts_seen_total", 0))
        posts_queued_video = int(monitor_result.get("posts_queued_video", new_posts_found))
        posts_skipped_non_video = int(monitor_result.get("posts_skipped_non_video", 0))
        errors = list(monitor_result["errors"])

        if status == "succeeded" and args.auto_generate_comments and posts_queued_video > 0:
            generation_summary["executed"] = True
            generation_script = str(args.engage_script or "engage_generate.py").strip()
            generation_cmd = [
                sys.executable,
                generation_script,
                "--db-path",
                str(args.db_path),
                "--limit",
                str(max(1, int(args.generate_limit))),
                "--whisper-model",
                str(args.whisper_model).strip() or "base.en",
            ]
            if str(args.openrouter_model).strip():
                generation_cmd.extend(["--model", str(args.openrouter_model).strip()])
            if str(args.blake_bible).strip():
                generation_cmd.extend(["--character-bible", str(args.blake_bible).strip()])

            try:
                proc = subprocess.run(
                    generation_cmd,
                    cwd=str(Path(__file__).resolve().parent),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                generation_summary.update(
                    {
                        "exit_code": int(proc.returncode),
                        "command": " ".join(generation_cmd),
                        "stdout": (proc.stdout or "").strip()[-4000:],
                        "stderr": (proc.stderr or "").strip()[-4000:],
                    }
                )
                if proc.returncode != 0:
                    errors.append(
                        f"engage generation failed with exit code {proc.returncode}"
                    )
            except Exception as exc:  # pragma: no cover - runtime safety
                errors.append(f"engage generation launch failed: {exc}")
                generation_summary.update(
                    {
                        "exit_code": 1,
                        "command": " ".join(generation_cmd),
                        "stderr": str(exc),
                    }
                )

    except Exception as exc:
        status = "failed"
        errors = [str(exc)]

    ended_at = now_utc_iso()
    duration_seconds = round(max(0.0, time.time() - started_epoch), 3)
    error_summary = "; ".join(errors[:5])

    new_posts_path = output_dir / f"new_posts_{run_id}.csv"
    write_new_posts_csv(new_posts_path, new_posts_rows)

    report = {
        "run_id": run_id,
        "mode": args.mode,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_seconds": duration_seconds,
        "status": status,
        "accounts_checked": accounts_checked,
        "new_posts_found": new_posts_found,
        "failed_accounts": failed_accounts,
        "posts_seen_total": posts_seen_total,
        "posts_queued_video": posts_queued_video,
        "posts_skipped_non_video": posts_skipped_non_video,
        "batch_size": max(1, min(50, args.batch_size)),
        "posts_per_account": max(1, args.posts_per_account),
        "max_retries": max(0, args.max_retries),
        "retry_base_seconds": max(0.0, args.retry_base_seconds),
        "retry_jitter_seconds": max(0.0, args.retry_jitter_seconds),
        "auto_generate_comments": bool(args.auto_generate_comments),
        "generate_limit": max(1, int(args.generate_limit)),
        "whisper_model": str(args.whisper_model).strip() or "base.en",
        "errors": errors,
        "generation": generation_summary,
        "artifacts": {
            "new_posts_csv": str(new_posts_path),
        },
    }
    report_path = output_dir / f"run_report_{run_id}.json"
    write_run_report(report_path, report)

    store.finalize_monitor_run(
        run_id=run_id,
        status=status,
        ended_at=ended_at,
        accounts_checked=accounts_checked,
        new_posts_found=new_posts_found,
        failed_accounts=failed_accounts,
        error_summary=error_summary,
    )
    store.close()

    print(
        "[monitor_run] completed "
        f"(status={status}, checked={accounts_checked}, new_posts={new_posts_found}, "
        f"failed_accounts={failed_accounts}, seen_total={posts_seen_total}, "
        f"queued_video={posts_queued_video}, skipped_non_video={posts_skipped_non_video})"
    )
    print(f"[monitor_run] new posts -> {new_posts_path}")
    print(f"[monitor_run] report -> {report_path}")

    if status != "succeeded":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
