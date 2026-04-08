from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, Optional
from unittest import mock

import monitor_run


class _FakeStore:
    last_instance: Optional["_FakeStore"] = None

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.finalized: Dict[str, Any] = {}
        _FakeStore.last_instance = self

    def create_monitor_run(self, **_kwargs: Any) -> None:
        return None

    def list_active_usernames(self, limit: Optional[int] = None):
        _ = limit
        return ["acct_a", "acct_b"]

    def finalize_monitor_run(self, **kwargs: Any) -> None:
        self.finalized = dict(kwargs)

    def close(self) -> None:
        return None


class MonitorRunTests(unittest.TestCase):
    def test_all_monitor_batches_failed_helper(self) -> None:
        self.assertTrue(
            monitor_run.all_monitor_batches_failed({"failed_batches": 2, "batches_total": 2})
        )
        self.assertFalse(
            monitor_run.all_monitor_batches_failed({"failed_batches": 1, "batches_total": 2})
        )
        self.assertFalse(
            monitor_run.all_monitor_batches_failed({"failed_batches": 0, "batches_total": 0})
        )

    def test_main_marks_run_failed_when_every_batch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_root = Path(tmpdir)
            db_path = temp_root / "monitor.db"
            output_dir = temp_root / "monitor_artifacts"
            captured: Dict[str, Any] = {}

            args = argparse.Namespace(
                mode="mock",
                db_path=str(db_path),
                output_dir=str(output_dir),
                limit_accounts=0,
                batch_size=25,
                posts_per_account=5,
                delay_seconds=0.0,
                wait_seconds=1,
                max_retries=0,
                retry_base_seconds=0.0,
                retry_jitter_seconds=0.0,
                actor_id="",
                fixture="data/monitor/mock_posts.json",
                auto_generate_comments=False,
                generate_limit=10,
                generate_drain_pending=False,
                generate_max_batches=20,
                whisper_model="base.en",
                openrouter_model="",
                blake_bible="",
                engage_script="engage_generate.py",
                mock_fail_usernames="",
            )

            monitor_result = {
                "accounts_checked": 2,
                "failed_accounts": 2,
                "failed_batches": 1,
                "new_posts": [],
                "new_posts_found": 0,
                "posts_seen_total": 0,
                "posts_queued_video": 0,
                "posts_skipped_non_video": 0,
                "errors": [],
                "batches_total": 1,
            }

            with (
                mock.patch.object(monitor_run, "parse_args", return_value=args),
                mock.patch.object(monitor_run, "MonitorStore", _FakeStore),
                mock.patch.object(monitor_run, "load_mock_posts_fixture", return_value={}),
                mock.patch.object(monitor_run, "build_mock_batch_fetcher", return_value=lambda _batch: []),
                mock.patch.object(monitor_run, "run_monitor_batches", return_value=monitor_result),
                mock.patch.object(monitor_run, "write_new_posts_csv"),
                mock.patch.object(
                    monitor_run,
                    "write_run_report",
                    side_effect=lambda _path, report: captured.setdefault("report", report),
                ),
            ):
                with self.assertRaises(SystemExit) as raised:
                    monitor_run.main()

            self.assertEqual(1, raised.exception.code)
            report = captured.get("report")
            self.assertIsInstance(report, dict)
            self.assertEqual("failed", report.get("status"))
            self.assertEqual(1, int(report.get("failed_batches", 0)))
            self.assertEqual(1, int(report.get("batches_total", 0)))
            self.assertIn("all monitor batches failed", "; ".join(report.get("errors", [])))

            store = _FakeStore.last_instance
            self.assertIsNotNone(store)
            self.assertEqual("failed", (store.finalized or {}).get("status"))


if __name__ == "__main__":
    unittest.main()
