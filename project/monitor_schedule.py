from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests


class ScheduleError(RuntimeError):
    """Raised when schedule management fails."""


class ApifyScheduleClient:
    BASE_URL = "https://api.apify.com/v2"

    def __init__(self, token: str, timeout_seconds: int = 60):
        if not token:
            raise ValueError("APIFY_TOKEN is required")
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
        )

    def _request(self, method: str, url: str, json_payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        response = self.session.request(
            method=method,
            url=url,
            json=json_payload,
            timeout=self.timeout_seconds,
        )
        if not response.ok:
            raise ScheduleError(
                f"Apify schedule API failed ({response.status_code}): {response.text[:500]}"
            )
        return response.json().get("data") or {}

    def list_schedules(self) -> List[Dict[str, Any]]:
        all_items: List[Dict[str, Any]] = []
        offset = 0
        limit = 1000
        while True:
            payload = self._request(
                "GET",
                f"{self.BASE_URL}/schedules?offset={offset}&limit={limit}",
            )
            items = payload.get("items") or []
            if not isinstance(items, list):
                break
            all_items.extend(item for item in items if isinstance(item, dict))
            if len(items) < limit:
                break
            offset += limit
        return all_items

    def create_schedule(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", f"{self.BASE_URL}/schedules", json_payload=payload)

    def update_schedule(self, schedule_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        encoded = quote(schedule_id, safe="")
        return self._request("PUT", f"{self.BASE_URL}/schedules/{encoded}", json_payload=payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or update Apify Schedule for 4-hour monitor polling."
    )
    parser.add_argument("--ensure", action="store_true", help="Create/update schedule idempotently.")
    parser.add_argument("--name", default="toms-part2-monitor-4h")
    parser.add_argument("--cron", default="0 */4 * * *")
    parser.add_argument("--timezone", default="America/Phoenix")
    parser.add_argument(
        "--description",
        default=(
            "Runs Part 2 monitoring workflow every 4 hours "
            "to detect new influencer posts for comment generation queue."
        ),
    )
    parser.add_argument(
        "--actor-task-id",
        default=os.getenv("APIFY_MONITOR_ACTOR_TASK_ID", ""),
        help="Apify Actor Task ID to run (preferred).",
    )
    parser.add_argument(
        "--actor-id",
        default=os.getenv("APIFY_MONITOR_ACTOR_ID", ""),
        help="Apify Actor ID to run when actor-task-id is not provided.",
    )
    parser.add_argument(
        "--run-input",
        default='{"mode":"live","posts_per_account":5,"batch_size":25}',
        help="JSON input for task/actor action.",
    )
    parser.add_argument("--disable", action="store_true", help="Create/update schedule as disabled.")
    return parser.parse_args()


def build_actions(actor_task_id: str, actor_id: str, run_input: Dict[str, Any]) -> List[Dict[str, Any]]:
    if actor_task_id:
        return [
            {
                "type": "RUN_ACTOR_TASK",
                "actorTaskId": actor_task_id,
                "input": run_input,
            }
        ]
    if actor_id:
        return [
            {
                "type": "RUN_ACTOR",
                "actorId": actor_id,
                "runInput": {
                    "body": json.dumps(run_input),
                    "contentType": "application/json; charset=utf-8",
                },
            }
        ]
    raise ValueError("Provide --actor-task-id (preferred) or --actor-id.")


def build_schedule_payload(args: argparse.Namespace) -> Dict[str, Any]:
    try:
        run_input = json.loads(args.run_input)
    except json.JSONDecodeError as exc:
        raise ValueError(f"--run-input must be valid JSON: {exc}") from exc

    actions = build_actions(
        actor_task_id=args.actor_task_id.strip(),
        actor_id=args.actor_id.strip(),
        run_input=run_input,
    )

    return {
        "name": args.name.strip(),
        "cronExpression": args.cron.strip(),
        "timezone": args.timezone.strip(),
        "description": args.description.strip(),
        "isEnabled": not args.disable,
        "isExclusive": True,
        "actions": actions,
    }


def main() -> None:
    args = parse_args()
    if not args.ensure:
        raise SystemExit("Use --ensure to create/update schedule idempotently.")

    token = os.getenv("APIFY_TOKEN", "").strip()
    if not token:
        raise SystemExit("APIFY_TOKEN is required.")

    payload = build_schedule_payload(args)
    client = ApifyScheduleClient(token=token)
    existing = next(
        (item for item in client.list_schedules() if str(item.get("name", "")).strip() == payload["name"]),
        None,
    )

    if existing:
        schedule_id = str(existing.get("id", ""))
        data = client.update_schedule(schedule_id=schedule_id, payload=payload)
        print(f"[monitor_schedule] updated schedule '{payload['name']}' (id={schedule_id})")
    else:
        data = client.create_schedule(payload=payload)
        schedule_id = str(data.get("id", ""))
        print(f"[monitor_schedule] created schedule '{payload['name']}' (id={schedule_id})")

    print(f"[monitor_schedule] cron={payload['cronExpression']} timezone={payload['timezone']}")
    print(f"[monitor_schedule] enabled={payload['isEnabled']}")


if __name__ == "__main__":
    main()

