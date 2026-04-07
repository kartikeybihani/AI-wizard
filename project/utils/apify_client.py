from __future__ import annotations

import time
import re
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote

import requests


class ApifyError(RuntimeError):
    """Raised when an Apify API call fails or returns an unusable run."""


USERNAME_KEYS = {
    "username",
    "userName",
    "ownerUsername",
    "authorUsername",
    "profileUsername",
    "handle",
    "screenName",
}
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._]{1,30}$")


def normalize_username(value: str) -> str:
    if not value:
        return ""
    cleaned = value.strip().lstrip("@").strip()
    return cleaned.lower()


def is_plausible_username(value: str) -> bool:
    cleaned = normalize_username(value)
    if not cleaned:
        return False
    if cleaned.startswith("http"):
        return False
    return bool(USERNAME_PATTERN.match(cleaned))


def extract_username(payload: Any) -> str:
    """
    Best-effort username extraction from heterogeneous Apify actor payloads.
    """
    if isinstance(payload, str):
        return normalize_username(payload) if is_plausible_username(payload) else ""

    if isinstance(payload, dict):
        for key in USERNAME_KEYS:
            raw = payload.get(key)
            if isinstance(raw, str) and is_plausible_username(raw):
                return normalize_username(raw)

        for key in ("owner", "author", "profile", "user", "account"):
            nested = payload.get(key)
            value = extract_username(nested)
            if value:
                return value

        # Last-pass recursive scan for nested records.
        for value in payload.values():
            nested_value = extract_username(value)
            if nested_value:
                return nested_value

    if isinstance(payload, list):
        for item in payload:
            nested_value = extract_username(item)
            if nested_value:
                return nested_value

    return ""


class ApifyClient:
    BASE_URL = "https://api.apify.com/v2"

    def __init__(self, token: str, timeout_seconds: int = 60):
        if not token:
            raise ValueError("APIFY_TOKEN is required to use ApifyClient")
        self.token = token
        self.timeout_seconds = timeout_seconds

    def run_actor(
        self,
        actor_id: str,
        actor_input: Dict[str, Any],
        wait_for_finish_seconds: int = 180,
    ) -> Dict[str, Any]:
        encoded_actor = quote(actor_id, safe="")
        url = f"{self.BASE_URL}/acts/{encoded_actor}/runs"
        params = {
            "token": self.token,
            "waitForFinish": wait_for_finish_seconds,
        }

        response = requests.post(
            url,
            params=params,
            json=actor_input,
            timeout=self.timeout_seconds,
        )
        if not response.ok:
            raise ApifyError(
                f"Apify actor run failed ({response.status_code}): {response.text[:500]}"
            )

        data = response.json().get("data") or {}
        run_id = data.get("id")
        status = data.get("status")

        if run_id and status not in {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}:
            data = self.wait_for_run(run_id)

        return data

    def wait_for_run(self, run_id: str, poll_seconds: float = 2.0) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/actor-runs/{run_id}"

        while True:
            response = requests.get(
                url,
                params={"token": self.token},
                timeout=self.timeout_seconds,
            )
            if not response.ok:
                raise ApifyError(
                    f"Apify run poll failed ({response.status_code}): {response.text[:500]}"
                )
            run_data = response.json().get("data") or {}
            status = run_data.get("status")
            if status in {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}:
                return run_data
            time.sleep(poll_seconds)

    def get_dataset_items(
        self,
        dataset_id: str,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        url = f"{self.BASE_URL}/datasets/{dataset_id}/items"
        params: Dict[str, Any] = {
            "token": self.token,
            "format": "json",
            "clean": "1",
        }
        if limit is not None:
            params["limit"] = limit

        response = requests.get(url, params=params, timeout=self.timeout_seconds)
        if not response.ok:
            raise ApifyError(
                f"Apify dataset fetch failed ({response.status_code}): {response.text[:500]}"
            )

        data = response.json()
        return data if isinstance(data, list) else []

    def run_actor_and_fetch_items(
        self,
        actor_id: str,
        actor_input: Dict[str, Any],
        wait_for_finish_seconds: int = 180,
        dataset_limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        run_data = self.run_actor(actor_id, actor_input, wait_for_finish_seconds)
        status = run_data.get("status")

        if status != "SUCCEEDED":
            raise ApifyError(f"Actor run did not succeed (status={status})")

        dataset_id = run_data.get("defaultDatasetId")
        if not dataset_id:
            raise ApifyError("Actor run succeeded but returned no default dataset")

        return self.get_dataset_items(dataset_id, limit=dataset_limit)


def chunked(values: List[str], batch_size: int) -> Iterable[List[str]]:
    for index in range(0, len(values), batch_size):
        yield values[index : index + batch_size]
