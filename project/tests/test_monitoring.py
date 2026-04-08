from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import List

from utils.monitoring import (
    MonitorStore,
    build_mock_batch_fetcher,
    extract_posts_for_batch,
    infer_is_video,
    infer_media_type,
    load_mock_posts_fixture,
    read_ranked_accounts_csv,
    run_monitor_batches,
)


class MonitoringTests(unittest.TestCase):
    def test_extract_posts_for_batch_handles_nested_and_flat_payloads(self) -> None:
        items = [
            {
                "username": "mindcharity",
                "posts": [
                    {
                        "shortCode": "POST_NESTED_1",
                        "url": "https://www.instagram.com/p/POST_NESTED_1/",
                        "caption": "nested sample",
                        "takenAtTimestamp": 1775602800,
                    }
                ],
            },
            {
                "author": {"username": "mindcharity"},
                "id": "POST_FLAT_2",
                "url": "https://www.instagram.com/p/POST_FLAT_2/",
                "caption": "flat sample",
                "timestamp": "2026-04-07T12:00:00Z",
            },
            {
                "username": "otheraccount",
                "id": "SHOULD_BE_FILTERED",
                "caption": "ignore me",
            },
        ]

        posts = extract_posts_for_batch(
            items=items,
            batch_usernames=["mindcharity"],
            posts_per_account=5,
        )

        self.assertEqual(2, len(posts))
        post_ids = {post["post_id"] for post in posts}
        self.assertEqual({"POST_NESTED_1", "POST_FLAT_2"}, post_ids)
        self.assertTrue(all(post["username"] == "mindcharity" for post in posts))
        self.assertTrue(all("is_video" in post for post in posts))
        self.assertTrue(all("media_type" in post for post in posts))

    def test_media_type_and_video_signal_inference(self) -> None:
        record_a = {"url": "https://www.instagram.com/reel/ABC123/"}
        media_type_a = infer_media_type(record_a, record_a["url"])
        self.assertEqual("reel", media_type_a)
        self.assertTrue(infer_is_video(record_a, record_a["url"], media_type_a))

        # Apify reel scraper often returns clips as /p/ URLs with productType/type video hints.
        record_b = {
            "url": "https://www.instagram.com/p/XYZ999/",
            "productType": "clips",
            "type": "Video",
            "videoUrl": "https://cdn.example/video.mp4",
        }
        media_type_b = infer_media_type(record_b, record_b["url"])
        self.assertEqual("reel", media_type_b)
        self.assertTrue(infer_is_video(record_b, record_b["url"], media_type_b))

        # Generic /p/ + isVideo=true should still be eligible as video.
        record_c = {"url": "https://www.instagram.com/p/VID001/", "isVideo": True}
        media_type_c = infer_media_type(record_c, record_c["url"])
        self.assertEqual("video", media_type_c)
        self.assertTrue(infer_is_video(record_c, record_c["url"], media_type_c))

        record_d = {"url": "https://www.instagram.com/p/IMG001/", "__typename": "GraphImage"}
        media_type_d = infer_media_type(record_d, record_d["url"])
        self.assertEqual("image", media_type_d)
        self.assertFalse(infer_is_video(record_d, record_d["url"], media_type_d))

    def test_insert_new_posts_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "monitor.db"
            store = MonitorStore(db_path=db_path)
            try:
                post = {
                    "username": "mindcharity",
                    "post_id": "UNIQUE_POST_1",
                    "caption": "first post",
                    "url": "https://www.instagram.com/reel/UNIQUE_POST_1/",
                    "posted_at": "2026-04-07T20:00:00Z",
                }
                first = store.insert_new_posts([post], detected_at="2026-04-07T21:00:00Z")
                second = store.insert_new_posts([post], detected_at="2026-04-07T22:00:00Z")

                self.assertEqual(1, len(first))
                self.assertEqual(0, len(second))
                self.assertEqual(1, store.count_rows("seen_posts"))
                self.assertEqual(1, store.count_rows("new_posts_queue"))
            finally:
                store.close()

    def test_non_video_posts_are_deduped_in_seen_but_not_queued(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "monitor.db"
            store = MonitorStore(db_path=db_path)
            try:
                image_post = {
                    "username": "mindcharity",
                    "post_id": "IMAGE_ONLY_1",
                    "caption": "image only",
                    "url": "https://www.instagram.com/p/IMAGE_ONLY_1/",
                    "posted_at": "2026-04-07T20:00:00Z",
                    "is_video": "0",
                    "media_type": "p",
                }
                video_post = {
                    "username": "mindcharity",
                    "post_id": "REEL_1",
                    "caption": "video",
                    "url": "https://www.instagram.com/reel/REEL_1/",
                    "posted_at": "2026-04-07T20:00:00Z",
                    "is_video": "1",
                    "media_type": "reel",
                }
                metrics = store.insert_new_posts_with_metrics(
                    [image_post, video_post],
                    detected_at="2026-04-07T21:00:00Z",
                )
                self.assertEqual(2, int(metrics["posts_seen_total"]))
                self.assertEqual(1, int(metrics["posts_queued_video"]))
                self.assertEqual(1, int(metrics["posts_skipped_non_video"]))
                self.assertEqual(1, len(metrics["queued_posts"]))
                self.assertEqual(2, store.count_rows("seen_posts"))
                self.assertEqual(1, store.count_rows("new_posts_queue"))
            finally:
                store.close()

    def test_run_monitor_batches_retries_and_continues_after_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "monitor.db"
            store = MonitorStore(db_path=db_path)
            try:
                usernames = ["acct1", "acct2", "acct3"]

                def fetch_batch(batch_usernames: List[str]):
                    if "acct1" in batch_usernames:
                        raise RuntimeError("simulated upstream timeout")
                    return [
                        {
                            "username": "acct3",
                            "post_id": "POST_3",
                            "caption": "third account",
                            "url": "https://www.instagram.com/reel/POST_3/",
                            "posted_at": "2026-04-07T23:00:00Z",
                        }
                    ]

                result = run_monitor_batches(
                    store=store,
                    usernames=usernames,
                    fetch_batch=fetch_batch,
                    batch_size=2,
                    delay_seconds=0.0,
                    max_retries=2,
                    retry_base_seconds=0.0,
                    retry_jitter_seconds=0.0,
                    sleep_fn=lambda _: None,
                )

                self.assertEqual(3, result["accounts_checked"])
                self.assertEqual(2, result["failed_accounts"])
                self.assertEqual(1, result["new_posts_found"])
                self.assertEqual(1, result["failed_batches"])
                self.assertEqual(1, len(result["errors"]))
                self.assertEqual(1, store.count_rows("new_posts_queue"))
                self.assertEqual(1, int(result["posts_seen_total"]))
                self.assertEqual(1, int(result["posts_queued_video"]))
                self.assertEqual(0, int(result["posts_skipped_non_video"]))
            finally:
                store.close()

    def test_bootstrap_upsert_preserves_manual_inactive(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_dir = Path(tmpdir)
            db_path = temp_dir / "monitor.db"
            ranked_csv = temp_dir / "final_ranked.csv"

            ranked_csv.write_text(
                (
                    "username,tier,final_score,overall_rank\n"
                    "mindcharity,macro,0.70,2\n"
                    "therapyjeff,major,0.65,1\n"
                ),
                encoding="utf-8",
            )

            store = MonitorStore(db_path=db_path)
            try:
                store.upsert_tracked_accounts(
                    [{"username": "mindcharity", "tier": "macro", "final_score": 0.5}],
                    source_run_id="run-old",
                )
                store.set_tracked_account_active("mindcharity", active=False)

                accounts = read_ranked_accounts_csv(ranked_csv)
                stats = store.upsert_tracked_accounts(accounts, source_run_id="run-new")

                self.assertEqual(1, stats["inserted"])
                self.assertEqual(1, stats["updated"])
                self.assertEqual(0, stats["skipped"])

                existing = store.get_tracked_account("mindcharity")
                added = store.get_tracked_account("therapyjeff")
                self.assertIsNotNone(existing)
                self.assertIsNotNone(added)
                self.assertEqual(0, int(existing["active"]))
                self.assertEqual(1, int(added["active"]))
            finally:
                store.close()

    def test_mock_fixture_rerun_produces_no_duplicate_queue_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_dir = Path(tmpdir)
            db_path = temp_dir / "monitor.db"
            fixture_path = temp_dir / "mock_fixture.json"

            fixture_path.write_text(
                json.dumps(
                    {
                        "accounts": [
                            {
                                "username": "mindcharity",
                                "posts": [
                                    {
                                        "id": "P_A",
                                        "url": "https://www.instagram.com/reel/P_A/",
                                        "caption": "a",
                                        "timestamp": "2026-04-07T10:00:00Z",
                                    }
                                ],
                            },
                            {
                                "username": "therapyjeff",
                                "posts": [
                                    {
                                        "shortCode": "P_B",
                                        "url": "https://www.instagram.com/reel/P_B/",
                                        "caption": "b",
                                        "timestamp": "2026-04-07T11:00:00Z",
                                    }
                                ],
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            store = MonitorStore(db_path=db_path)
            try:
                store.upsert_tracked_accounts(
                    [
                        {"username": "mindcharity", "tier": "macro", "final_score": 0.7},
                        {"username": "therapyjeff", "tier": "major", "final_score": 0.6},
                    ]
                )
                usernames = store.list_active_usernames()
                fixture_posts = load_mock_posts_fixture(fixture_path)
                fetch_batch = build_mock_batch_fetcher(fixture_posts, posts_per_account=5)

                first = run_monitor_batches(
                    store=store,
                    usernames=usernames,
                    fetch_batch=fetch_batch,
                    batch_size=25,
                    delay_seconds=0.0,
                    max_retries=0,
                    sleep_fn=lambda _: None,
                )
                second = run_monitor_batches(
                    store=store,
                    usernames=usernames,
                    fetch_batch=fetch_batch,
                    batch_size=25,
                    delay_seconds=0.0,
                    max_retries=0,
                    sleep_fn=lambda _: None,
                )

                self.assertEqual(2, first["new_posts_found"])
                self.assertEqual(0, second["new_posts_found"])
                self.assertEqual(2, store.count_rows("new_posts_queue"))
                self.assertEqual(2, store.count_rows("seen_posts"))
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
