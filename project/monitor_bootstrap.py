from __future__ import annotations

import argparse
from pathlib import Path

from utils.monitoring import MONITOR_DB_PATH, MonitorStore, read_ranked_accounts_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap tracked monitor accounts from final ranked CSV."
    )
    parser.add_argument("--input", default="data/final_ranked.csv")
    parser.add_argument("--db-path", default=str(MONITOR_DB_PATH))
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--source-run-id", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ranked_path = Path(args.input)
    db_path = Path(args.db_path)

    accounts = read_ranked_accounts_csv(
        path=ranked_path,
        limit=args.limit if args.limit and args.limit > 0 else None,
    )

    store = MonitorStore(db_path=db_path)
    try:
        stats = store.upsert_tracked_accounts(
            accounts=accounts,
            source_run_id=args.source_run_id.strip() or None,
        )
    finally:
        store.close()

    print(
        "[monitor_bootstrap] tracked accounts updated "
        f"(input={len(accounts)}, inserted={stats['inserted']}, "
        f"updated={stats['updated']}, skipped={stats['skipped']})"
    )
    print(f"[monitor_bootstrap] db -> {db_path}")


if __name__ == "__main__":
    main()

