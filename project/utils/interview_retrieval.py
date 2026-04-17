from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import requests


@dataclass
class RetrievedItem:
    item_id: str
    score: float
    kind: str
    title: str
    text: str
    sources: List[str]
    payload: Dict[str, Any]


def _normalize(vec: np.ndarray) -> np.ndarray:
    denom = float(np.linalg.norm(vec))
    if denom <= 0.0:
        return vec
    return vec / denom


def _tokenize(text: str) -> List[str]:
    raw = (text or "").lower()
    cleaned = []
    token = []
    for ch in raw:
        if ch.isalnum() or ch in {"_", "-"}:
            token.append(ch)
        else:
            if token:
                cleaned.append("".join(token))
                token = []
    if token:
        cleaned.append("".join(token))
    return cleaned


def hashed_embedding(text: str, dim: int = 256) -> np.ndarray:
    vec = np.zeros(dim, dtype=np.float32)
    tokens = _tokenize(text)
    if not tokens:
        return vec

    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8", errors="ignore")).digest()
        idx = int.from_bytes(digest[:4], byteorder="little", signed=False) % dim
        sign = -1.0 if (digest[4] & 1) else 1.0
        vec[idx] += sign

    # Light TF scaling
    vec = vec / float(max(1, len(tokens)))
    return _normalize(vec)


class LocalInterviewRetriever:
    def __init__(
        self,
        knowledge_dir: Path,
        embedding_api_key: str = "",
        embedding_model: str = "text-embedding-3-small",
        embedding_base_url: str = "https://api.openai.com/v1",
        embedding_extra_headers: Optional[Dict[str, str]] = None,
        timeout_seconds: int = 20,
    ):
        self.knowledge_dir = Path(knowledge_dir)
        self.embedding_api_key = (embedding_api_key or "").strip()
        self.embedding_model = (embedding_model or "text-embedding-3-small").strip()
        self.embedding_base_url = (embedding_base_url or "https://api.openai.com/v1").rstrip("/")
        self.embedding_extra_headers = dict(embedding_extra_headers or {})
        self.timeout_seconds = max(5, int(timeout_seconds))

        self._matrix: Optional[np.ndarray] = None
        self._metadata: List[Dict[str, Any]] = []
        self._dim: int = 256

    @property
    def ready(self) -> bool:
        return self._matrix is not None and len(self._metadata) > 0

    def load(self) -> None:
        index_path = self.knowledge_dir / "retrieval" / "index.npz"
        meta_path = self.knowledge_dir / "retrieval" / "metadata.jsonl"
        if not index_path.exists() or not meta_path.exists():
            raise FileNotFoundError(
                f"retrieval index not found. expected: {index_path} and {meta_path}"
            )

        loaded = np.load(index_path)
        matrix = loaded["matrix"].astype(np.float32)
        self._matrix = matrix
        self._dim = int(matrix.shape[1]) if matrix.ndim == 2 else 256

        rows: List[Dict[str, Any]] = []
        with meta_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))

        if len(rows) != matrix.shape[0]:
            raise RuntimeError(
                f"metadata count mismatch: matrix={matrix.shape[0]} metadata={len(rows)}"
            )
        self._metadata = rows

    def _embed_query(self, text: str) -> np.ndarray:
        text = (text or "").strip()
        if not text:
            return np.zeros(self._dim, dtype=np.float32)

        if not self.embedding_api_key:
            return hashed_embedding(text, dim=self._dim)

        try:
            headers = {
                "Authorization": f"Bearer {self.embedding_api_key}",
                "Content-Type": "application/json",
            }
            headers.update(self.embedding_extra_headers)
            response = requests.post(
                f"{self.embedding_base_url}/embeddings",
                headers=headers,
                json={
                    "model": self.embedding_model,
                    "input": text,
                },
                timeout=self.timeout_seconds,
            )
            if not response.ok:
                # Fallback to deterministic embedding for resiliency.
                return hashed_embedding(text, dim=self._dim)
            body = response.json()
            values = body.get("data", [{}])[0].get("embedding", [])
            if not isinstance(values, list) or not values:
                return hashed_embedding(text, dim=self._dim)
            vec = np.array(values, dtype=np.float32)
            if vec.shape[0] != self._dim:
                if vec.shape[0] > self._dim:
                    vec = vec[: self._dim]
                else:
                    padded = np.zeros(self._dim, dtype=np.float32)
                    padded[: vec.shape[0]] = vec
                    vec = padded
            return _normalize(vec)
        except Exception:
            return hashed_embedding(text, dim=self._dim)

    def retrieve(
        self,
        query: str,
        top_k: int = 4,
        include_kinds: Optional[Sequence[str]] = None,
        min_score: float = -1.0,
    ) -> List[RetrievedItem]:
        if not self.ready:
            raise RuntimeError("retriever is not loaded")

        assert self._matrix is not None
        q = self._embed_query(query)
        sims = self._matrix @ q

        allowed = {kind for kind in (include_kinds or []) if kind}
        order = np.argsort(-sims)

        results: List[RetrievedItem] = []
        for idx in order.tolist():
            row = self._metadata[idx]
            score = float(sims[idx])
            if score < min_score:
                continue

            kind = str(row.get("kind", ""))
            if allowed and kind not in allowed:
                continue

            results.append(
                RetrievedItem(
                    item_id=str(row.get("item_id", f"item_{idx}")),
                    score=score,
                    kind=kind,
                    title=str(row.get("title", "")),
                    text=str(row.get("text", "")),
                    sources=list(row.get("sources") or []),
                    payload=row,
                )
            )
            if len(results) >= max(1, int(top_k)):
                break

        return results

    def retrieve_mixed(self, query: str) -> Dict[str, List[RetrievedItem]]:
        """Default retrieval shape for v1 interview generation.

        - 1 timeline card
        - up to 4 story cards
        - optional policy card
        """
        timeline = self.retrieve(query, top_k=1, include_kinds=["truth_timeline"])  # strict 1
        stories = self.retrieve(query, top_k=4, include_kinds=["story_card"])  # strict <=4
        policies = self.retrieve(query, top_k=1, include_kinds=["policy"], min_score=0.0)

        return {
            "timeline": timeline,
            "stories": stories,
            "policies": policies,
        }
