from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import requests


def _normalize(vec: np.ndarray) -> np.ndarray:
    denom = float(np.linalg.norm(vec))
    if denom <= 0.0:
        return vec
    return vec / denom


def _tokenize(text: str) -> List[str]:
    raw = (text or "").lower()
    out: List[str] = []
    token: List[str] = []
    for ch in raw:
        if ch.isalnum() or ch in {"_", "-"}:
            token.append(ch)
        else:
            if token:
                out.append("".join(token))
                token = []
    if token:
        out.append("".join(token))
    return out


def hashed_embedding(text: str, dim: int = 256) -> np.ndarray:
    import hashlib

    vec = np.zeros(dim, dtype=np.float32)
    tokens = _tokenize(text)
    if not tokens:
        return vec
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8", errors="ignore")).digest()
        idx = int.from_bytes(digest[:4], byteorder="little", signed=False) % dim
        sign = -1.0 if (digest[4] & 1) else 1.0
        vec[idx] += sign
    vec = vec / float(max(1, len(tokens)))
    return _normalize(vec)


def remote_embed(
    api_key: str,
    base_url: str,
    model: str,
    text: str,
    timeout_seconds: int = 20,
    extra_headers: Dict[str, str] | None = None,
) -> List[float]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    headers.update(extra_headers or {})
    response = requests.post(
        f"{base_url.rstrip('/')}/embeddings",
        headers=headers,
        json={"model": model, "input": text},
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    body = response.json()
    return list(body.get("data", [{}])[0].get("embedding", []))


def load_story_cards(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def build_documents(knowledge_dir: Path) -> List[Dict[str, Any]]:
    timeline = json.loads((knowledge_dir / "truth_timeline.json").read_text(encoding="utf-8"))
    stories = load_story_cards(knowledge_dir / "story_cards.jsonl")

    docs: List[Dict[str, Any]] = []

    for event in timeline.get("events", []):
        item_id = str(event.get("id", ""))
        claim = str(event.get("claim", "")).strip()
        if not item_id or not claim:
            continue
        year = event.get("year")
        uncertainty = str(event.get("uncertainty_note", "")).strip()
        text = f"{claim}"
        if year is not None:
            text = f"[{year}] {text}"
        if uncertainty:
            text += f" Uncertainty note: {uncertainty}"

        docs.append(
            {
                "item_id": item_id,
                "kind": "truth_timeline",
                "title": str(event.get("claim", "")).strip()[:120],
                "text": text,
                "sources": list(event.get("sources") or []),
                "payload": event,
            }
        )

    for story in stories:
        story_id = str(story.get("story_id", "")).strip()
        if not story_id:
            continue
        arc = story.get("narrative_arc") or {}
        setup = str(arc.get("setup", "")).strip()
        turn = str(arc.get("turn", "")).strip()
        landing = str(arc.get("landing", "")).strip()
        anchors = "; ".join(str(a) for a in (story.get("factual_anchors") or []) if str(a).strip())
        text = f"{setup} {turn} {landing}".strip()
        if anchors:
            text += f" Anchors: {anchors}"

        docs.append(
            {
                "item_id": story_id,
                "kind": "story_card",
                "title": str(story.get("title", story_id)),
                "text": text,
                "sources": list(story.get("sources") or []),
                "payload": story,
            }
        )

    # Include boundary policy as one retrievable policy card.
    policy_payload = json.loads((knowledge_dir / "boundary_policy.json").read_text(encoding="utf-8"))
    private_cfg = policy_payload.get("private_topics") or {}
    docs.append(
        {
            "item_id": "policy_private_topics",
            "kind": "policy",
            "title": "Strict public-only private-topic boundary",
            "text": (
                "Private-topic boundary keywords: "
                + ", ".join(str(k) for k in (private_cfg.get("keywords") or []) if str(k).strip())
                + ". Response style: gentle deflection and return to public lessons."
            ),
            "sources": [str(knowledge_dir / "boundary_policy.json")],
            "payload": policy_payload,
        }
    )

    return docs


def main() -> None:
    parser = argparse.ArgumentParser(description="Build local retrieval index for Blake interview artifacts")
    parser.add_argument("--knowledge-dir", default="blake/persona_interview/v1")
    parser.add_argument("--embedding-model", default="")
    parser.add_argument("--dim", type=int, default=256)
    parser.add_argument("--force-hash", action="store_true", default=False)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    knowledge_dir = (repo_root / args.knowledge_dir).resolve()
    retrieval_dir = knowledge_dir / "retrieval"
    retrieval_dir.mkdir(parents=True, exist_ok=True)

    docs = build_documents(knowledge_dir)
    if not docs:
        raise RuntimeError("No documents found to index.")

    # Read from environment only to avoid accidental secret handling in args.
    import os

    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    embedding_provider = os.getenv("INTERVIEW_EMBEDDING_PROVIDER", "auto").strip().lower()
    if embedding_provider == "auto":
        if openai_api_key:
            embedding_provider = "openai"
        elif openrouter_api_key:
            embedding_provider = "openrouter"
        else:
            embedding_provider = "hash"
    if args.force_hash:
        embedding_provider = "hash"
    if embedding_provider not in {"openai", "openrouter", "hash"}:
        embedding_provider = "hash"

    embedding_api_key_override = os.getenv("INTERVIEW_EMBEDDING_API_KEY", "").strip()
    embedding_base_url_override = os.getenv("INTERVIEW_EMBEDDING_BASE_URL", "").strip()
    openrouter_http_referer = os.getenv("OPENROUTER_HTTP_REFERER", "").strip()
    openrouter_app_name = os.getenv("OPENROUTER_APP_NAME", "").strip()

    if embedding_provider == "openai":
        embedding_api_key = embedding_api_key_override or openai_api_key
        embedding_base_url = embedding_base_url_override or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
        embedding_model = args.embedding_model or os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small").strip()
        extra_headers: Dict[str, str] = {}
    elif embedding_provider == "openrouter":
        embedding_api_key = embedding_api_key_override or openrouter_api_key
        embedding_base_url = embedding_base_url_override or os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip()
        embedding_model = args.embedding_model or os.getenv("OPENROUTER_EMBEDDING_MODEL", "openai/text-embedding-3-small").strip()
        extra_headers = {}
        if openrouter_http_referer:
            extra_headers["HTTP-Referer"] = openrouter_http_referer
        if openrouter_app_name:
            extra_headers["X-Title"] = openrouter_app_name
    else:
        embedding_api_key = ""
        embedding_base_url = ""
        embedding_model = args.embedding_model or os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small").strip()
        extra_headers = {}

    vectors: List[np.ndarray] = []
    use_remote_embeddings = embedding_provider in {"openai", "openrouter"} and bool(embedding_api_key)

    for doc in docs:
        text = str(doc.get("text", ""))
        if use_remote_embeddings:
            try:
                emb = remote_embed(
                    api_key=embedding_api_key,
                    base_url=embedding_base_url,
                    model=embedding_model,
                    text=text,
                    extra_headers=extra_headers,
                )
                vec = np.array(emb, dtype=np.float32)
                if vec.shape[0] > args.dim:
                    vec = vec[: args.dim]
                elif vec.shape[0] < args.dim:
                    padded = np.zeros(args.dim, dtype=np.float32)
                    padded[: vec.shape[0]] = vec
                    vec = padded
                vec = _normalize(vec)
            except Exception:
                vec = hashed_embedding(text, dim=args.dim)
        else:
            vec = hashed_embedding(text, dim=args.dim)
        vectors.append(vec)

    matrix = np.vstack(vectors).astype(np.float32)
    np.savez_compressed(retrieval_dir / "index.npz", matrix=matrix)

    meta_path = retrieval_dir / "metadata.jsonl"
    with meta_path.open("w", encoding="utf-8") as handle:
        for doc in docs:
            row = {
                "item_id": doc.get("item_id"),
                "kind": doc.get("kind"),
                "title": doc.get("title"),
                "text": doc.get("text"),
                "sources": doc.get("sources") or [],
                "payload": doc.get("payload") or {},
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(
        f"[build_interview_retrieval_index] indexed {len(docs)} docs -> {retrieval_dir / 'index.npz'} "
        f"(embedding_provider={embedding_provider}, model={embedding_model}, remote={use_remote_embeddings})"
    )


if __name__ == "__main__":
    main()
