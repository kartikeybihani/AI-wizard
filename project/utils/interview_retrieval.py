from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

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


@dataclass
class RetrievedPassage:
    passage_id: str
    score: float
    source: str
    text: str
    story_ids: List[str]


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


def _sentence_split(text: str) -> List[str]:
    # Handles transcripts and markdown-like blocks.
    raw = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [part.strip() for part in raw if part and part.strip()]


def _clean_passage(text: str) -> str:
    value = (text or "").strip()
    if not value:
        return ""
    value = re.sub(r"\[[^\]]{0,24}\]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _is_passage_candidate(text: str) -> bool:
    words = _tokenize(text)
    count = len(words)
    if count < 10 or count > 90:
        return False
    lowered = text.lower()
    if not re.search(r"[.!?]$", text):
        return False
    if lowered.startswith("- "):
        return False
    if "http://" in lowered or "https://" in lowered:
        return False
    alpha = re.sub(r"[^A-Za-z]", "", text)
    if not alpha:
        return False
    if alpha.isupper() and len(alpha) > 12:
        return False
    return True


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
        self._repo_root = self._infer_repo_root(self.knowledge_dir)
        self._source_passages: Dict[str, List[Dict[str, Any]]] = {}

    def _infer_repo_root(self, path: Path) -> Path:
        current = path.resolve()
        for candidate in [current, *current.parents]:
            if (candidate / ".git").exists():
                return candidate
        # Fallback for common layout: <repo>/blake/persona_interview/v1
        if len(current.parents) >= 3:
            return current.parents[2]
        return current

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
        self._build_source_passage_cache()

    def _resolve_source_path(self, source: str) -> Optional[Path]:
        raw = str(source or "").strip()
        if not raw:
            return None
        candidate = Path(raw)
        if candidate.is_absolute():
            return candidate if candidate.exists() else None
        resolved = (self._repo_root / raw).resolve()
        return resolved if resolved.exists() else None

    def _build_source_passage_cache(self) -> None:
        source_paths: Dict[str, Path] = {}
        for row in self._metadata:
            for src in list(row.get("sources") or []):
                rel = str(src or "").strip()
                if not rel or rel in source_paths:
                    continue
                resolved = self._resolve_source_path(rel)
                if resolved is None:
                    continue
                # Keep passage extraction targeted to human-readable sources.
                if resolved.suffix.lower() not in {".txt"}:
                    continue
                source_paths[rel] = resolved

        cache: Dict[str, List[Dict[str, Any]]] = {}
        for source, filepath in source_paths.items():
            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            passages: List[Dict[str, Any]] = []
            seen: Set[str] = set()
            for idx, sentence in enumerate(_sentence_split(content), start=1):
                cleaned = _clean_passage(sentence)
                if not cleaned or not _is_passage_candidate(cleaned):
                    continue
                key = cleaned.lower()
                if key in seen:
                    continue
                seen.add(key)
                passages.append(
                    {
                        "passage_id": f"{source}#{idx}",
                        "text": cleaned,
                        "token_set": set(_tokenize(cleaned)),
                        "embedding": hashed_embedding(cleaned, dim=self._dim),
                    }
                )
                if len(passages) >= 240:
                    break
            if passages:
                cache[source] = passages
        self._source_passages = cache

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

    def _story_payload(self, item: RetrievedItem) -> Dict[str, Any]:
        payload = item.payload.get("payload") if isinstance(item.payload, dict) else {}
        if isinstance(payload, dict):
            return payload
        return {}

    def _filter_story_candidates(self, rows: List[RetrievedItem], max_stories: int = 2) -> List[RetrievedItem]:
        stories: List[RetrievedItem] = []
        for row in rows:
            payload = self._story_payload(row)
            allowed_use = str(payload.get("allowed_use", "")).strip().lower()
            if allowed_use == "boundary_only":
                continue
            stories.append(row)
            if len(stories) >= max(1, int(max_stories)):
                break
        return stories

    def _story_context_text(self, row: RetrievedItem) -> str:
        payload = self._story_payload(row)
        arc = payload.get("narrative_arc") if isinstance(payload.get("narrative_arc"), dict) else {}
        trigger_topics = payload.get("trigger_topics") if isinstance(payload.get("trigger_topics"), list) else []
        factual_anchors = payload.get("factual_anchors") if isinstance(payload.get("factual_anchors"), list) else []
        fields = [
            row.title,
            row.text,
            " ".join(str(item) for item in trigger_topics if str(item).strip()),
            " ".join(str(item) for item in factual_anchors if str(item).strip()),
            str(arc.get("setup", "")).strip() if isinstance(arc, dict) else "",
            str(arc.get("turn", "")).strip() if isinstance(arc, dict) else "",
            str(arc.get("landing", "")).strip() if isinstance(arc, dict) else "",
        ]
        return " ".join(part for part in fields if part)

    def _story_sources(self, row: RetrievedItem) -> List[str]:
        payload = self._story_payload(row)
        sources = payload.get("sources") if isinstance(payload.get("sources"), list) else []
        merged = [str(item).strip() for item in list(row.sources) + list(sources) if str(item).strip()]
        # Preserve order while deduping.
        seen: Set[str] = set()
        out: List[str] = []
        for src in merged:
            if src in seen:
                continue
            seen.add(src)
            out.append(src)
        return out

    def retrieve_story_passages(
        self,
        query: str,
        stories: List[RetrievedItem],
        top_k: int = 3,
    ) -> List[RetrievedPassage]:
        if not stories or not self._source_passages:
            return []

        query_tokens = set(_tokenize(query or ""))
        q_vec = hashed_embedding(query or "", dim=self._dim)
        story_vectors = [hashed_embedding(self._story_context_text(row), dim=self._dim) for row in stories]
        story_tokens: Set[str] = set()
        for row in stories:
            for token in _tokenize(self._story_context_text(row)):
                if len(token) >= 3:
                    story_tokens.add(token)
        focus_tokens = {token for token in query_tokens.union(story_tokens) if len(token) >= 3}
        story_ids = [row.item_id for row in stories]
        story_sources: Set[str] = set()
        for row in stories:
            for src in self._story_sources(row):
                if src in self._source_passages:
                    story_sources.add(src)

        scored: List[RetrievedPassage] = []
        for src in story_sources:
            for entry in self._source_passages.get(src, []):
                emb = entry.get("embedding")
                if not isinstance(emb, np.ndarray):
                    continue
                sim_query = float(np.dot(emb, q_vec))
                sim_story = max(float(np.dot(emb, svec)) for svec in story_vectors) if story_vectors else 0.0
                token_set = entry.get("token_set")
                overlap = 0
                if isinstance(token_set, set):
                    overlap = len(focus_tokens.intersection(token_set))
                if overlap <= 0:
                    continue
                lexical_boost = min(0.08, 0.012 * overlap)
                final_score = (0.62 * sim_query) + (0.32 * sim_story) + lexical_boost
                if final_score < 0.09:
                    continue
                scored.append(
                    RetrievedPassage(
                        passage_id=str(entry.get("passage_id", "")),
                        score=float(final_score),
                        source=src,
                        text=str(entry.get("text", "")),
                        story_ids=story_ids,
                    )
                )

        scored.sort(key=lambda row: row.score, reverse=True)

        deduped: List[RetrievedPassage] = []
        seen_texts: Set[str] = set()
        for row in scored:
            key = row.text.lower().strip()
            if not key or key in seen_texts:
                continue
            seen_texts.add(key)
            deduped.append(row)
            if len(deduped) >= max(1, int(top_k)):
                break
        return deduped

    def retrieve_mixed(self, query: str) -> Dict[str, Any]:
        """Default retrieval shape for v2 interview generation.

        - 1 timeline card
        - up to 2 story cards (higher-quality cues)
        - up to 3 source passages linked to those stories
        """
        timeline = self.retrieve(query, top_k=1, include_kinds=["truth_timeline"])  # strict 1
        story_pool = self.retrieve(query, top_k=12, include_kinds=["story_card"])
        stories = self._filter_story_candidates(story_pool, max_stories=2)
        passages = self.retrieve_story_passages(query=query, stories=stories, top_k=3)

        return {
            "timeline": timeline,
            "stories": stories,
            "policies": [],
            "passages": passages,
        }
