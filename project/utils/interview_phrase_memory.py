from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from .interview_retrieval import hashed_embedding

STYLE_KEYWORDS = (
    "for me",
    "i learned",
    "i realized",
    "the truth is",
    "one thing that helped",
    "i felt",
    "i feel",
    "i don't remember",
    "healing",
    "recovery",
    "enough",
    "connection",
    "present",
    "grateful",
    "depression",
    "anxiety",
    "struggle",
)

CONTENT_KEYWORDS = (
    "depression",
    "anxiety",
    "healing",
    "recovery",
    "enough",
    "identity",
    "purpose",
    "success",
    "disconnected",
    "connection",
    "present",
    "peace",
    "struggle",
    "felt",
    "feel",
    "help",
)


def _has_repeated_ngram(tokens: List[str], n: int = 2) -> bool:
    if len(tokens) < n * 2:
        return False
    for idx in range(0, len(tokens) - (2 * n) + 1):
        if tokens[idx : idx + n] == tokens[idx + n : idx + (2 * n)]:
            return True
    return False


def _normalize(vec: np.ndarray) -> np.ndarray:
    denom = float(np.linalg.norm(vec))
    if denom <= 0.0:
        return vec
    return vec / denom


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text or ""))


def _clean_line(text: str) -> str:
    value = (text or "").strip()
    if not value:
        return ""
    # Drop bracketed timestamps and compact whitespace.
    value = re.sub(r"\[[^\]]{0,24}\]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _sentence_split(text: str) -> List[str]:
    raw = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [part.strip() for part in raw if part and part.strip()]


def _is_phrase_candidate(text: str) -> bool:
    words = _word_count(text)
    if words < 9 or words > 28:
        return False
    lowered = text.lower()
    if not re.search(r"[.!?]$", text):
        return False
    if "http://" in lowered or "https://" in lowered:
        return False
    if re.search(r"\b(\w+)\s+\1\b", lowered):
        return False
    rough_tokens = re.findall(r"[a-z]+(?:['’][a-z]+)?", lowered)
    if _has_repeated_ngram(rough_tokens, n=2):
        return False
    if not re.search(r"\b(i|i'm|i’ve|i've|my|me)\b", lowered):
        return False
    if not re.match(r"^(?:i\b|i'm\b|i’ve\b|i've\b|for me\b|the truth is\b|what i\b|one thing\b)", lowered):
        return False
    if not any(token in lowered for token in STYLE_KEYWORDS):
        return False
    if not any(token in lowered for token in CONTENT_KEYWORDS):
        return False
    # Avoid noisy all-caps or metadata-like lines.
    letters = re.sub(r"[^A-Za-z]", "", text)
    if letters and letters.upper() == letters and len(letters) > 8:
        return False
    if re.search(r"\b(refreshments?|summer job|coupon|discount|subscribe|promo)\b", lowered):
        return False
    tail = re.findall(r"\b[\w'-]+\b", lowered)
    if tail:
        if tail[-1] in {"for", "and", "or", "but", "to", "with", "of", "the", "a", "an", "is", "it"}:
            return False
    return True


@dataclass
class PhraseMemoryItem:
    item_id: str
    text: str
    source: str


@dataclass
class PhraseMemoryHit:
    item_id: str
    text: str
    source: str
    score: float


class LocalPhraseMemory:
    def __init__(
        self,
        repo_root: Path,
        max_items: int = 1200,
        dim: int = 256,
    ):
        self.repo_root = Path(repo_root)
        self.max_items = max(100, int(max_items))
        self.dim = max(64, int(dim))
        self._items: List[PhraseMemoryItem] = []
        self._matrix: Optional[np.ndarray] = None

    @property
    def ready(self) -> bool:
        return bool(self._items) and self._matrix is not None

    def _source_files(self) -> List[Path]:
        # Primary source: long-form interview transcripts.
        patterns = [
            "blake/podcasts/tim_ferriss/*.txt",
            "blake/podcasts/youtube/*.txt",
        ]
        files: List[Path] = []
        for pattern in patterns:
            files.extend(sorted(self.repo_root.glob(pattern)))
        return files

    def load(self) -> None:
        items: List[PhraseMemoryItem] = []
        seen: set[str] = set()
        files = self._source_files()

        for path in files:
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            for sentence in _sentence_split(content):
                cleaned = _clean_line(sentence)
                if not cleaned or not _is_phrase_candidate(cleaned):
                    continue
                key = cleaned.lower()
                if key in seen:
                    continue
                seen.add(key)
                rel = str(path.relative_to(self.repo_root))
                item_id = f"phrase_{len(items)+1:04d}"
                items.append(PhraseMemoryItem(item_id=item_id, text=cleaned, source=rel))
                if len(items) >= self.max_items:
                    break
            if len(items) >= self.max_items:
                break

        if not items:
            self._items = []
            self._matrix = None
            return

        vectors: List[np.ndarray] = []
        for item in items:
            vec = hashed_embedding(item.text, dim=self.dim)
            vectors.append(_normalize(vec))

        self._items = items
        self._matrix = np.vstack(vectors).astype(np.float32)

    def retrieve(self, query: str, top_k: int = 4, min_score: float = 0.08) -> List[PhraseMemoryHit]:
        if not self.ready:
            return []
        assert self._matrix is not None

        q = _normalize(hashed_embedding(query or "", dim=self.dim))
        sims = self._matrix @ q
        order = np.argsort(-sims)

        hits: List[PhraseMemoryHit] = []
        for idx in order.tolist():
            score = float(sims[idx])
            if score < min_score:
                continue
            item = self._items[idx]
            hits.append(
                PhraseMemoryHit(
                    item_id=item.item_id,
                    text=item.text,
                    source=item.source,
                    score=score,
                )
            )
            if len(hits) >= max(1, int(top_k)):
                break
        return hits

    def to_debug(self, rows: List[PhraseMemoryHit], preview_chars: int = 200) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "item_id": row.item_id,
                    "score": round(float(row.score), 4),
                    "source": row.source,
                    "text_preview": row.text[: max(40, int(preview_chars))],
                }
            )
        return out
