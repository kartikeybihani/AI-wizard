#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = REPO_ROOT / "project"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.llm import LLMError, OpenRouterClient  # noqa: E402


DEFAULT_SOURCE_WEIGHTS = {
    "podcasts_transcripts": 0.45,
    "substack_personal_site": 0.30,
    "instagram_captions": 0.20,
    "external_articles": 0.05,
}

DEFAULT_ERA_WEIGHTS = {
    "era_a_toms_builder": 0.10,
    "era_b_transition_seeker": 0.30,
    "era_c_enough_current": 0.60,
}

DEFAULT_MODELS = {
    "extract": os.getenv("OPENROUTER_MODEL_EXTRACT", "openrouter/auto"),
    "synthesis": os.getenv("OPENROUTER_MODEL_SYNTHESIS", "openrouter/auto"),
    "critic": os.getenv("OPENROUTER_MODEL_CRITIC", "openrouter/auto"),
}

DEFAULT_LLM_MAX_TOKENS = {
    "instagram_batch": 800,
    "instagram_consolidate": 900,
    "youtube_chunk": 1200,
    "youtube_consolidate_video": 1600,
    "youtube_consolidate_global": 2200,
    "podcast_chunk": 1200,
    "podcast_consolidate_doc": 1600,
    "podcast_consolidate_global": 2400,
    "longform_chunk": 850,
    "longform_consolidate_doc": 900,
    "longform_consolidate_global": 1100,
    "written_chunk": 1200,
    "written_consolidate_doc": 1500,
    "written_consolidate_global": 2200,
    "calibration_chunk": 700,
    "calibration_consolidate_doc": 1000,
    "calibration_consolidate_global": 1400,
    "antipatterns": 1100,
    "character_bible": 1400,
}

LLM_MAX_TOKENS = dict(DEFAULT_LLM_MAX_TOKENS)

DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
WS_RE = re.compile(r"[ \t]+")

STEP_ORDER = [
    "01_instagram",
    "02_youtube",
    "03_podcast_depth",
    "04_written_values",
    "05_external_calibration",
    "06_antipatterns",
    "07_character_bible",
]

STEP_ALIASES = {
    "1": "01_instagram",
    "01": "01_instagram",
    "instagram": "01_instagram",
    "01_instagram": "01_instagram",
    "2": "02_youtube",
    "02": "02_youtube",
    "youtube": "02_youtube",
    "02_youtube": "02_youtube",
    "3": "03_podcast_depth",
    "03": "03_podcast_depth",
    "podcast": "03_podcast_depth",
    "podcasts": "03_podcast_depth",
    "03_podcast_depth": "03_podcast_depth",
    "4": "04_written_values",
    "04": "04_written_values",
    "written": "04_written_values",
    "substack": "04_written_values",
    "personal_site": "04_written_values",
    "04_written_values": "04_written_values",
    "5": "05_external_calibration",
    "05": "05_external_calibration",
    "calibration": "05_external_calibration",
    "articles": "05_external_calibration",
    "05_external_calibration": "05_external_calibration",
    "6": "06_antipatterns",
    "06": "06_antipatterns",
    "antipatterns": "06_antipatterns",
    "06_antipatterns": "06_antipatterns",
    "7": "07_character_bible",
    "07": "07_character_bible",
    "bible": "07_character_bible",
    "character_bible": "07_character_bible",
    "07_character_bible": "07_character_bible",
}


@dataclass
class SourceDoc:
    doc_id: str
    bucket: str
    source_group: str
    era: str
    date_key: str
    title: str
    path: str
    url: str
    text: str


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def normalize_text(text: str) -> str:
    text = text.replace("\r", "\n")
    lines: List[str] = []
    for raw in text.split("\n"):
        line = WS_RE.sub(" ", raw).strip()
        if line:
            lines.append(line)
    return "\n".join(lines).strip()


def parse_steps(raw_steps: str) -> List[str]:
    text = (raw_steps or "all").strip().lower()
    if text in {"all", "*"}:
        return list(STEP_ORDER)
    out: List[str] = []
    for token in text.split(","):
        key = token.strip().lower()
        if not key:
            continue
        resolved = STEP_ALIASES.get(key)
        if not resolved:
            raise ValueError(
                f"Unknown step token '{token}'. Use one of: {', '.join(STEP_ORDER)} or aliases."
            )
        if resolved not in out:
            out.append(resolved)
    if not out:
        return list(STEP_ORDER)
    return out


def parse_frontmatter(content: str) -> Tuple[Dict[str, str], str]:
    meta: Dict[str, str] = {}
    if not content.startswith("---\n"):
        return meta, content

    parts = content.split("\n")
    if len(parts) < 3:
        return meta, content

    end_idx = -1
    for i in range(1, min(len(parts), 120)):
        if parts[i].strip() == "---":
            end_idx = i
            break
    if end_idx == -1:
        return meta, content

    for line in parts[1:end_idx]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()

    body = "\n".join(parts[end_idx + 1 :]).strip()
    return meta, body


def infer_date_key(meta: Dict[str, str], path: Path) -> str:
    candidates = [
        meta.get("published_at", ""),
        meta.get("collected_at", ""),
        path.name,
    ]
    for raw in candidates:
        if not raw:
            continue
        if raw.isdigit() and len(raw) == 8:
            return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
        match = DATE_RE.search(raw)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return "unknown-date"


def infer_era(date_key: str) -> str:
    if date_key == "unknown-date":
        return "era_b_transition_seeker"
    try:
        year = int(date_key[0:4])
    except Exception:  # noqa: BLE001
        return "era_b_transition_seeker"

    if year <= 2020:
        return "era_a_toms_builder"
    if year <= 2024:
        return "era_b_transition_seeker"
    return "era_c_enough_current"


def make_doc_id(bucket: str, path: Path) -> str:
    stem = re.sub(r"[^a-z0-9]+", "_", path.stem.lower()).strip("_")
    return f"{bucket}_{stem}"


def load_txt_docs(paths: Iterable[Path], bucket: str, source_group_default: str) -> List[SourceDoc]:
    docs: List[SourceDoc] = []
    for path in sorted(paths):
        content = read_text(path)
        meta, body = parse_frontmatter(content)
        text = normalize_text(body or content)
        if not text:
            continue
        source_group = meta.get("source_group", source_group_default) or source_group_default
        date_key = infer_date_key(meta, path)
        title = meta.get("title", path.stem)
        docs.append(
            SourceDoc(
                doc_id=make_doc_id(bucket, path),
                bucket=bucket,
                source_group=source_group,
                era=infer_era(date_key),
                date_key=date_key,
                title=title,
                path=str(path),
                url=meta.get("url", ""),
                text=text,
            )
        )
    return docs


def load_instagram_captions(csv_path: Path) -> List[Dict[str, Any]]:
    if not csv_path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with csv_path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle)
        for i, row in enumerate(reader):
            caption = (row.get("caption") or "").strip()
            if not caption:
                continue
            ts = (row.get("timestamp") or "").strip()
            date_key = "unknown-date"
            match = DATE_RE.search(ts)
            if match:
                date_key = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
            rows.append(
                {
                    "row_id": i + 1,
                    "caption": caption,
                    "timestamp": ts,
                    "date_key": date_key,
                    "era": infer_era(date_key),
                    "url": (row.get("url") or "").strip(),
                    "likes": (row.get("likes") or "").strip(),
                    "comments_count": (row.get("comments_count") or "").strip(),
                }
            )
    return rows


def chunk_text(text: str, max_chars: int = 12000) -> List[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return []
    chunks: List[str] = []
    current = ""
    for p in paragraphs:
        candidate = f"{current}\n\n{p}".strip() if current else p
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(p) <= max_chars:
            current = p
            continue
        # Hard split extremely long paragraphs.
        start = 0
        while start < len(p):
            end = min(start + max_chars, len(p))
            chunks.append(p[start:end].strip())
            start = end
        current = ""
    if current:
        chunks.append(current)
    return chunks


def sample_chunks(chunks: List[str], max_chunks: int) -> List[str]:
    if max_chunks <= 0 or len(chunks) <= max_chunks:
        return chunks
    if max_chunks == 1:
        return [chunks[len(chunks) // 2]]
    if max_chunks == 2:
        return [chunks[0], chunks[-1]]

    # Preserve beginning and end, sample middle positions.
    selected = [chunks[0]]
    middle_needed = max_chunks - 2
    if middle_needed > 0:
        for i in range(1, middle_needed + 1):
            idx = round(i * (len(chunks) - 1) / (middle_needed + 1))
            idx = max(1, min(len(chunks) - 2, idx))
            selected.append(chunks[idx])
    selected.append(chunks[-1])

    deduped: List[str] = []
    seen: set[str] = set()
    for c in selected:
        key = c[:120]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)
    return deduped[:max_chunks]


def load_prompt_template(prompt_dir: Path, filename: str) -> str:
    path = prompt_dir / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8", errors="replace").strip()


class ModelPool:
    def __init__(self, api_key: str, app_name: str, app_url: str):
        self.api_key = api_key
        self.app_name = app_name
        self.app_url = app_url
        self._clients: Dict[str, OpenRouterClient] = {}

    def client(self, model: str) -> OpenRouterClient:
        existing = self._clients.get(model)
        if existing:
            return existing
        client = OpenRouterClient(
            api_key=self.api_key,
            model=model,
            app_name=self.app_name,
            app_url=self.app_url,
        )
        self._clients[model] = client
        return client


def llm_json_with_retry(
    client: OpenRouterClient,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
    retries: int = 4,
    context_label: str = "",
    debug_dir: Optional[Path] = None,
    debug_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    def _slug(text: str) -> str:
        clean = re.sub(r"[^a-zA-Z0-9._-]+", "_", text).strip("_")
        return clean[:120] if clean else "llm_call"

    def _write_debug(attempt_num: int, token_budget: int, err: Exception) -> None:
        if debug_dir is None:
            return
        debug_dir.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        label = _slug(context_label or "llm_call")
        payload: Dict[str, Any] = {
            "ts_utc": stamp,
            "context_label": context_label,
            "attempt": attempt_num,
            "retries": retries,
            "model": client.model,
            "token_budget": token_budget,
            "error_type": type(err).__name__,
            "error": str(err),
            "system_prompt_chars": len(system_prompt),
            "user_prompt_chars": len(user_prompt),
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "extra": debug_payload or {},
        }
        details = getattr(err, "details", None)
        if isinstance(details, dict) and details:
            payload["llm_details"] = details
        out_path = debug_dir / f"{stamp}_{label}_attempt{attempt_num}.json"
        write_json(out_path, payload)

    last_err: Optional[Exception] = None
    current_max_tokens = int(max_tokens)
    for attempt in range(1, retries + 1):
        try:
            return client.chat_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=current_max_tokens,
            )
        except (LLMError, Exception) as exc:  # noqa: BLE001
            last_err = exc
            _write_debug(attempt, current_max_tokens, exc)
            msg = str(exc).replace("\n", " ").strip()
            msg = msg[:260] if len(msg) > 260 else msg
            label = f"[{context_label}] " if context_label else ""
            print(
                f"[voice_builder] {label}LLM attempt {attempt}/{retries} failed: {msg}",
                file=sys.stderr,
            )
            if attempt < retries and "truncated" in msg.lower():
                bumped = min(max(current_max_tokens + 600, int(current_max_tokens * 1.6)), 10000)
                if bumped > current_max_tokens:
                    current_max_tokens = bumped
                    print(
                        f"[voice_builder] {label}retrying with higher max_tokens={current_max_tokens}",
                        file=sys.stderr,
                    )
            if attempt < retries:
                time.sleep(1.6 * attempt)
    detail = str(last_err).replace("\n", " ").strip() if last_err else "unknown"
    raise RuntimeError(f"LLM call failed after {retries} attempts: {detail[:500]}") from last_err


def summarize_batches(
    pool: ModelPool,
    model: str,
    system_prompt: str,
    outputs: List[Dict[str, Any]],
    objective: str,
    max_tokens: int = 1400,
    context_label: str = "",
    debug_dir: Optional[Path] = None,
    extra_constraints: str = "",
) -> Dict[str, Any]:
    user_prompt = (
        "Consolidate the extraction outputs into one canonical JSON object.\n"
        f"Objective: {objective}\n"
        "Keep only stable, repeated patterns and remove one-off noise.\n"
        "Preserve evidence references when present.\n\n"
        "Output compactness constraints:\n"
        "- Keep only strongest repeated patterns.\n"
        "- Keep arrays concise.\n"
        "- Keep total response concise so it fits token limits.\n\n"
        f"{extra_constraints}"
        "Extraction outputs (JSON array):\n"
        f"{json.dumps(outputs, ensure_ascii=False)}\n\n"
        "Return strict JSON only."
    )
    return llm_json_with_retry(
        client=pool.client(model),
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.0,
        max_tokens=max_tokens,
        context_label=context_label,
        debug_dir=debug_dir,
        debug_payload={"objective": objective, "output_count": len(outputs)},
    )


def run_instagram_patterns(
    pool: ModelPool,
    run_dir: Path,
    prompt_dir: Path,
    captions: List[Dict[str, Any]],
    model: str,
    source_weights: Dict[str, float],
    era_weights: Dict[str, float],
    dry_run: bool,
    batch_size: int,
) -> Dict[str, Any]:
    step_dir = run_dir / "01_instagram_patterns"
    step_dir.mkdir(parents=True, exist_ok=True)

    system_prompt = load_prompt_template(prompt_dir, "01_instagram_pattern_mining.md")
    batches = [captions[i : i + batch_size] for i in range(0, len(captions), batch_size)]
    batch_outputs: List[Dict[str, Any]] = []

    for idx, batch in enumerate(batches, start=1):
        payload = {
            "source_weights": source_weights,
            "era_weights": era_weights,
            "batch_index": idx,
            "batch_size": len(batch),
            "captions": batch,
        }
        batch_path = step_dir / f"batch_{idx:03d}.json"
        if dry_run:
            out = {
                "dry_run": True,
                "batch_index": idx,
                "patterns": [],
                "notes": "LLM call skipped (dry-run).",
                "input_preview_count": len(batch),
            }
        else:
            user_prompt = (
                "Task: Mine recurrent Blake Instagram caption structures and voice patterns.\n"
                "Focus on comment-ready behavior and short-form cadence.\n"
                "Prioritize repeated patterns over one-off lines.\n"
                "Do not invent facts.\n\n"
                "Output compactness constraints:\n"
                "- top_patterns: max 6 items.\n"
                "- archetypal_structures: max 8 items.\n"
                "- voice_tells: max 6 items.\n"
                "- anti_patterns: max 8 items.\n"
                "- Any example_quotes array: max 2 quotes, <=160 chars each.\n"
                "- Keep total response concise so it fits token limits.\n\n"
                "Input JSON:\n"
                f"{json.dumps(payload, ensure_ascii=False)}\n\n"
                "Return strict JSON only."
            )
            out = llm_json_with_retry(
                client=pool.client(model),
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.0,
                max_tokens=int(LLM_MAX_TOKENS["instagram_batch"]),
            )
        write_json(batch_path, out)
        batch_outputs.append(out)

    consolidated_path = step_dir / "consolidated.json"
    if dry_run:
        consolidated = {
            "dry_run": True,
            "total_batches": len(batches),
            "patterns": [],
            "notes": "Consolidation skipped (dry-run).",
        }
    else:
        consolidated = summarize_batches(
            pool=pool,
            model=model,
            system_prompt=system_prompt,
            outputs=batch_outputs,
            objective="Produce the canonical Instagram pattern inventory for Blake's current voice.",
            max_tokens=int(LLM_MAX_TOKENS["instagram_consolidate"]),
            context_label="01_instagram:consolidate_global",
        )
    write_json(consolidated_path, consolidated)
    return consolidated


def run_youtube_primitives(
    pool: ModelPool,
    run_dir: Path,
    prompt_dir: Path,
    docs: List[SourceDoc],
    model: str,
    source_weights: Dict[str, float],
    era_weights: Dict[str, float],
    dry_run: bool,
    max_chars_per_chunk: int,
    max_chunks_per_doc: int,
    debug_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    step_dir = run_dir / "02_youtube_primitives"
    per_video_dir = step_dir / "per_video"
    per_video_dir.mkdir(parents=True, exist_ok=True)
    system_prompt = load_prompt_template(prompt_dir, "02_youtube_voice_primitives_compact.md")

    video_outputs: List[Dict[str, Any]] = []
    for doc in docs:
        chunks = sample_chunks(
            chunk_text(doc.text, max_chars=max_chars_per_chunk),
            max_chunks=max_chunks_per_doc,
        )
        chunk_outputs: List[Dict[str, Any]] = []

        for chunk_idx, chunk in enumerate(chunks, start=1):
            chunk_payload = {
                "source_weights": source_weights,
                "era_weights": era_weights,
                "doc_id": doc.doc_id,
                "title": doc.title,
                "date_key": doc.date_key,
                "era": doc.era,
                "chunk_index": chunk_idx,
                "chunk_count": len(chunks),
                "text": chunk,
            }
            if dry_run:
                chunk_out = {
                    "dry_run": True,
                    "doc_id": doc.doc_id,
                    "chunk_index": chunk_idx,
                    "primitives": [],
                }
            else:
                user_prompt = (
                    "Task: Extract behavioral voice primitives from this YouTube transcript chunk.\n"
                    "Focus on thinking patterns, bridge words, pacing, self-interruptions, and emotional stance.\n"
                    "Prefer concrete linguistic signals with examples.\n\n"
                    "Output compactness constraints:\n"
                    "- primitives: exactly 6.\n"
                    "- thought_patterns: max 4.\n"
                    "- vulnerability: max 4.\n"
                    "- bridge_words/openers/closers: max 4 each.\n"
                    "- Any quote <= 14 words.\n"
                    "- Keep strings concise and avoid long explanations.\n"
                    "- Keep total response concise so it fits token limits.\n\n"
                    "Input JSON:\n"
                    f"{json.dumps(chunk_payload, ensure_ascii=False)}\n\n"
                    "Return strict JSON only."
                )
                chunk_out = llm_json_with_retry(
                    client=pool.client(model),
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=0.0,
                    max_tokens=int(LLM_MAX_TOKENS["youtube_chunk"]),
                    context_label=f"02_youtube:doc={doc.doc_id}:chunk={chunk_idx}/{len(chunks)}",
                    debug_dir=debug_dir,
                    debug_payload={
                        "step_name": "02_youtube",
                        "doc_id": doc.doc_id,
                        "title": doc.title,
                        "chunk_index": chunk_idx,
                        "chunk_count": len(chunks),
                    },
                )
            chunk_outputs.append(chunk_out)

        if dry_run:
            video_summary = {
                "dry_run": True,
                "doc_id": doc.doc_id,
                "title": doc.title,
                "era": doc.era,
                "date_key": doc.date_key,
                "primitives": [],
                "chunk_count": len(chunks),
            }
        else:
            reduce_prompt = (
                "Consolidate chunk-level extractions into a single transcript-level primitive set.\n"
                "Keep only repeated, high-confidence primitives.\n\n"
                "Output compactness constraints:\n"
                "- primitives: exactly 6.\n"
                "- thought_patterns: max 4.\n"
                "- vulnerability: max 4.\n"
                "- bridge_words/openers/closers: max 4 each.\n"
                "- Any quote <= 14 words.\n"
                "- Keep strings concise and avoid long explanations.\n"
                "- Keep total response concise so it fits token limits.\n\n"
                f"Transcript metadata: doc_id={doc.doc_id}, title={doc.title}, era={doc.era}, date_key={doc.date_key}\n"
                "Chunk outputs (JSON array):\n"
                f"{json.dumps(chunk_outputs, ensure_ascii=False)}\n\n"
                "Return strict JSON only."
            )
            video_summary = llm_json_with_retry(
                client=pool.client(model),
                system_prompt=system_prompt,
                user_prompt=reduce_prompt,
                temperature=0.0,
                max_tokens=int(LLM_MAX_TOKENS["youtube_consolidate_video"]),
                context_label=f"02_youtube:doc={doc.doc_id}:consolidate",
                debug_dir=debug_dir,
                debug_payload={
                    "step_name": "02_youtube",
                    "doc_id": doc.doc_id,
                    "title": doc.title,
                    "chunk_count": len(chunks),
                },
            )
            video_summary.setdefault("doc_id", doc.doc_id)
            video_summary.setdefault("title", doc.title)
            video_summary.setdefault("era", doc.era)
            video_summary.setdefault("date_key", doc.date_key)

        write_json(per_video_dir / f"{doc.doc_id}.json", video_summary)
        video_outputs.append(video_summary)

    consolidated_path = step_dir / "consolidated.json"
    if dry_run:
        consolidated = {
            "dry_run": True,
            "video_count": len(video_outputs),
            "primitives": [],
            "notes": "Consolidation skipped (dry-run).",
        }
    else:
        consolidated = summarize_batches(
            pool=pool,
            model=model,
            system_prompt=system_prompt,
            outputs=video_outputs,
            objective=(
                "Produce canonical YouTube-derived behavioral voice primitives for Blake. "
                "Mark which are stable across eras vs strongest in 2025-2026."
            ),
            max_tokens=int(LLM_MAX_TOKENS["youtube_consolidate_global"]),
            context_label="02_youtube:consolidate_global",
            debug_dir=debug_dir,
            extra_constraints=(
                "Output compactness constraints:\n"
                "- primitives: exactly 6.\n"
                "- thought_patterns: max 4.\n"
                "- vulnerability: max 4.\n"
                "- bridge_words/openers/closers: max 4 each.\n"
                "- Any quote <= 14 words.\n"
                "- Keep strings concise and avoid long explanations.\n\n"
            ),
        )
    write_json(consolidated_path, consolidated)
    return consolidated


def run_longform_depth(
    pool: ModelPool,
    run_dir: Path,
    prompt_dir: Path,
    docs: List[SourceDoc],
    model: str,
    source_weights: Dict[str, float],
    era_weights: Dict[str, float],
    dry_run: bool,
    step_name: str,
    prompt_file: str,
    objective: str,
    max_chars_per_chunk: int,
    max_chunks_per_doc: int,
    chunk_token_key: str = "longform_chunk",
    consolidate_doc_token_key: str = "longform_consolidate_doc",
    consolidate_global_token_key: str = "longform_consolidate_global",
    debug_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    step_dir = run_dir / step_name
    per_doc_dir = step_dir / "per_doc"
    per_doc_dir.mkdir(parents=True, exist_ok=True)
    system_prompt = load_prompt_template(prompt_dir, prompt_file)

    doc_outputs: List[Dict[str, Any]] = []
    for doc in docs:
        chunks = sample_chunks(
            chunk_text(doc.text, max_chars=max_chars_per_chunk),
            max_chunks=max_chunks_per_doc,
        )
        chunk_outputs: List[Dict[str, Any]] = []
        for chunk_idx, chunk in enumerate(chunks, start=1):
            payload = {
                "source_weights": source_weights,
                "era_weights": era_weights,
                "doc_id": doc.doc_id,
                "title": doc.title,
                "bucket": doc.bucket,
                "date_key": doc.date_key,
                "era": doc.era,
                "chunk_index": chunk_idx,
                "chunk_count": len(chunks),
                "text": chunk,
            }
            if dry_run:
                chunk_out = {
                    "dry_run": True,
                    "doc_id": doc.doc_id,
                    "chunk_index": chunk_idx,
                    "signals": [],
                }
            else:
                compact_block = (
                    "Output compactness constraints:\n"
                    "- Keep only strongest repeated patterns.\n"
                    "- Any evidence_quotes array: max 2 quotes, <=180 chars each.\n"
                    "- Keep total response concise so it fits token limits.\n\n"
                )
                if step_name == "04_written_values":
                    compact_block = (
                        "Output compactness constraints:\n"
                        "- values: exactly 3\n"
                        "- rhetoric: exactly 3\n"
                        "- implications: exactly 3\n"
                        "- avoid: exactly 3\n"
                        "- each quote <= 12 words\n"
                        "- each string <= 12 words\n"
                        "- no extra keys, no prose paragraphs\n\n"
                    )
                elif step_name == "03_podcast_depth":
                    compact_block = (
                        "Output compactness constraints:\n"
                        "- core_arcs: max 4\n"
                        "- inner_life_patterns: max 4\n"
                        "- recurring_metaphors: max 3\n"
                        "- belief lists: max 4 each\n"
                        "- any evidence quote <= 14 words\n"
                        "- keep fields concise; avoid long explanations\n\n"
                    )
                elif step_name == "05_external_calibration":
                    compact_block = (
                        "Output compactness constraints:\n"
                        "- descriptors: exactly 6\n"
                        "- factual_points: max 6\n"
                        "- caution_flags: max 4\n"
                        "- each string <= 14 words\n"
                        "- no long prose, no extra keys\n\n"
                    )
                user_prompt = (
                    f"Task objective: {objective}\n"
                    "Extract recurring arcs, values, and language markers.\n"
                    "Keep outputs grounded in text evidence.\n\n"
                    f"{compact_block}"
                    "Input JSON:\n"
                    f"{json.dumps(payload, ensure_ascii=False)}\n\n"
                    "Return strict JSON only."
                )
                chunk_out = llm_json_with_retry(
                    client=pool.client(model),
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=0.0,
                    max_tokens=int(LLM_MAX_TOKENS.get(chunk_token_key, LLM_MAX_TOKENS["longform_chunk"])),
                    context_label=f"{step_name}:doc={doc.doc_id}:chunk={chunk_idx}/{len(chunks)}",
                    debug_dir=debug_dir,
                    debug_payload={
                        "step_name": step_name,
                        "doc_id": doc.doc_id,
                        "title": doc.title,
                        "chunk_index": chunk_idx,
                        "chunk_count": len(chunks),
                        "prompt_file": prompt_file,
                        "objective": objective,
                    },
                )
            chunk_outputs.append(chunk_out)

        if dry_run:
            doc_summary = {
                "dry_run": True,
                "doc_id": doc.doc_id,
                "title": doc.title,
                "bucket": doc.bucket,
                "era": doc.era,
                "signals": [],
            }
        else:
            reduce_compact_block = (
                "Output compactness constraints:\n"
                "- Keep only strongest repeated patterns.\n"
                "- Any evidence_quotes array: max 2 quotes, <=180 chars each.\n"
                "- Keep total response concise so it fits token limits.\n\n"
            )
            if step_name == "04_written_values":
                reduce_compact_block = (
                    "Output compactness constraints:\n"
                    "- values: exactly 3\n"
                    "- rhetoric: exactly 3\n"
                    "- implications: exactly 3\n"
                    "- avoid: exactly 3\n"
                    "- each quote <= 12 words\n"
                    "- each string <= 12 words\n"
                    "- no extra keys, no prose paragraphs\n\n"
                )
            elif step_name == "03_podcast_depth":
                reduce_compact_block = (
                    "Output compactness constraints:\n"
                    "- core_arcs: max 4\n"
                    "- inner_life_patterns: max 4\n"
                    "- recurring_metaphors: max 3\n"
                    "- belief lists: max 4 each\n"
                    "- any evidence quote <= 14 words\n"
                    "- keep fields concise; avoid long explanations\n\n"
                )
            elif step_name == "05_external_calibration":
                reduce_compact_block = (
                    "Output compactness constraints:\n"
                    "- descriptors: exactly 6\n"
                    "- factual_points: max 6\n"
                    "- caution_flags: max 4\n"
                    "- each string <= 14 words\n"
                    "- no long prose, no extra keys\n\n"
                )
            reduce_prompt = (
                "Consolidate chunk-level outputs into one document-level extraction.\n"
                "Keep only repeated, high-confidence insights.\n\n"
                f"{reduce_compact_block}"
                f"Document metadata: doc_id={doc.doc_id}, title={doc.title}, bucket={doc.bucket}, era={doc.era}\n"
                "Chunk outputs:\n"
                f"{json.dumps(chunk_outputs, ensure_ascii=False)}\n\n"
                "Return strict JSON only."
            )
            doc_summary = llm_json_with_retry(
                client=pool.client(model),
                system_prompt=system_prompt,
                user_prompt=reduce_prompt,
                temperature=0.0,
                max_tokens=int(
                    LLM_MAX_TOKENS.get(consolidate_doc_token_key, LLM_MAX_TOKENS["longform_consolidate_doc"])
                ),
                context_label=f"{step_name}:doc={doc.doc_id}:consolidate",
                debug_dir=debug_dir,
                debug_payload={
                    "step_name": step_name,
                    "doc_id": doc.doc_id,
                    "title": doc.title,
                    "chunk_count": len(chunks),
                    "prompt_file": prompt_file,
                    "objective": objective,
                },
            )
            doc_summary.setdefault("doc_id", doc.doc_id)
            doc_summary.setdefault("title", doc.title)
            doc_summary.setdefault("bucket", doc.bucket)
            doc_summary.setdefault("era", doc.era)

        write_json(per_doc_dir / f"{doc.doc_id}.json", doc_summary)
        doc_outputs.append(doc_summary)

    consolidated_path = step_dir / "consolidated.json"
    if dry_run:
        consolidated = {
            "dry_run": True,
            "doc_count": len(doc_outputs),
            "insights": [],
            "notes": "Consolidation skipped (dry-run).",
        }
    else:
        consolidated = summarize_batches(
            pool=pool,
            model=model,
            system_prompt=system_prompt,
            outputs=doc_outputs,
            objective=objective,
            max_tokens=int(
                LLM_MAX_TOKENS.get(consolidate_global_token_key, LLM_MAX_TOKENS["longform_consolidate_global"])
            ),
            context_label=f"{step_name}:consolidate_global",
            debug_dir=debug_dir,
            extra_constraints=(
                "Output compactness constraints:\n"
                "- values: exactly 3\n"
                "- rhetoric: exactly 3\n"
                "- implications: exactly 3\n"
                "- avoid: exactly 3\n"
                "- each quote <= 12 words\n"
                "- each string <= 12 words\n"
                "- no extra keys, no prose paragraphs\n\n"
            )
            if step_name == "04_written_values"
            else (
                "Output compactness constraints:\n"
                "- core_arcs: max 4\n"
                "- inner_life_patterns: max 4\n"
                "- recurring_metaphors: max 3\n"
                "- belief lists: max 4 each\n"
                "- any evidence quote <= 14 words\n"
                "- keep fields concise; avoid long explanations\n\n"
            )
            if step_name == "03_podcast_depth"
            else (
                "Output compactness constraints:\n"
                "- descriptors: exactly 6\n"
                "- factual_points: max 6\n"
                "- caution_flags: max 4\n"
                "- m.doc_id must be \"multiple\"\n"
                "- m.era must be \"mixed\"\n"
                "- include only repeated multi-source signals\n"
                "- each string <= 14 words\n"
                "- no long prose, no extra keys\n\n"
            )
            if step_name == "05_external_calibration"
            else "",
        )
    write_json(consolidated_path, consolidated)
    return consolidated


def run_antipatterns(
    pool: ModelPool,
    run_dir: Path,
    prompt_dir: Path,
    model: str,
    dry_run: bool,
    positive_inputs: Dict[str, Any],
) -> Dict[str, Any]:
    out_path = run_dir / "06_antipatterns.json"
    system_prompt = load_prompt_template(prompt_dir, "04_antipattern_generation.md")
    if dry_run:
        output = {
            "dry_run": True,
            "anti_patterns": [],
            "notes": "LLM call skipped (dry-run).",
        }
        write_json(out_path, output)
        return output

    user_prompt = (
        "Generate anti-patterns and negative-space constraints for Blake voice.\n"
        "Use the positive extraction inputs below.\n"
        "Each anti-pattern should include why it is wrong and how to fix.\n\n"
        "Output compactness constraints:\n"
        "- near_miss_examples: max 8 items.\n"
        "- Keep examples short and specific.\n"
        "- Keep total response concise so it fits token limits.\n\n"
        "Positive inputs JSON:\n"
        f"{json.dumps(positive_inputs, ensure_ascii=False)}\n\n"
        "Return strict JSON only."
    )
    output = llm_json_with_retry(
        client=pool.client(model),
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.0,
        max_tokens=int(LLM_MAX_TOKENS["antipatterns"]),
    )
    write_json(out_path, output)
    return output


def build_identity_grounding(blake_root: Path) -> Dict[str, Any]:
    def _read_first(pattern: str) -> Tuple[Dict[str, str], str]:
        matches = sorted(blake_root.glob(pattern))
        if not matches:
            return {}, ""
        raw = read_text(matches[0])
        meta, body = parse_frontmatter(raw)
        return meta, normalize_text(body or raw)

    def _select_lines(text: str, keywords: List[str], limit: int) -> List[str]:
        out: List[str] = []
        for line in text.split("\n"):
            candidate = line.strip()
            if len(candidate) < 14:
                continue
            lc = candidate.lower()
            if any(k in lc for k in keywords):
                out.append(candidate)
            if len(out) >= limit:
                break
        return out

    wiki_meta, wiki_text = _read_first("self/wikipedia/*blake_mycoskie*.txt")
    about_meta, about_text = _read_first("self/personal_site/*_about.txt")
    substack_meta, substack_text = _read_first("self/substack/*i-had-everything-it-still-wasnt-enough*.txt")

    facts: List[str] = []
    wiki_l = wiki_text.lower()
    if "born august 26, 1976" in wiki_l:
        facts.append("Born August 26, 1976 (Arlington, Texas).")
    if "founder of toms shoes" in wiki_l:
        facts.append("Founder of TOMS Shoes and architect of the One for One model.")
    if "co-founder of madefor" in wiki_l:
        facts.append("Co-founder of Madefor after TOMS.")
    if "published the book start something that matters in 2011" in wiki_l:
        facts.append("Author of Start Something That Matters (2011).")
    if "shoes for better tomorrows" in wiki_l and "started in 2006" in wiki_l:
        facts.append("Launched TOMS in 2006 after a trip to Argentina.")

    self_descriptors = _select_lines(
        about_text,
        [
            "toms / enough founder",
            "seeker",
            "grateful human",
            "lover of life",
            "dad",
        ],
        limit=6,
    )

    first_person_lines = _select_lines(
        substack_text,
        [
            "i planned to take my own life",
            "i am enough",
            "enough was my way",
            "i'm not a therapist",
            "it still wasn't enough",
        ],
        limit=8,
    )

    return {
        "bio_facts": facts[:8],
        "self_descriptors": self_descriptors,
        "first_person_lines": first_person_lines,
        "source_refs": [
            {
                "source": "wikipedia",
                "title": wiki_meta.get("title", ""),
                "url": wiki_meta.get("url", ""),
                "path_hint": "blake/self/wikipedia/*blake_mycoskie*.txt",
            },
            {
                "source": "personal_site_about",
                "title": about_meta.get("title", ""),
                "url": about_meta.get("url", ""),
                "path_hint": "blake/self/personal_site/*_about.txt",
            },
            {
                "source": "substack_origin_post",
                "title": substack_meta.get("title", ""),
                "url": substack_meta.get("url", ""),
                "path_hint": "blake/self/substack/*i-had-everything-it-still-wasnt-enough*.txt",
            },
        ],
    }


def render_character_bible_md(data: Dict[str, Any]) -> str:
    def _bucket_title(raw: str) -> str:
        return str(raw or "Bucket").replace("_", " ").strip().title()

    def _to_list(value: Any) -> List[Any]:
        if isinstance(value, list):
            return value
        if value in (None, ""):
            return []
        return [value]

    lines: List[str] = ["# Blake Character Bible", ""]
    positioning = data.get("voice_positioning") or {}
    if isinstance(positioning, dict) and positioning:
        lines.append("## Voice Positioning")
        one_liner = positioning.get("one_sentence_definition")
        distinct = positioning.get("what_makes_him_distinct")
        not_voice = positioning.get("what_the_voice_is_not")
        if one_liner:
            lines.append(f"- Definition: {one_liner}")
        if distinct:
            lines.append(f"- Distinctive Edge: {distinct}")
        if not_voice:
            lines.append(f"- Not This Voice: {not_voice}")
        lines.append("")

    who_block = data.get("who_blake_is") or {}
    if isinstance(who_block, dict) and who_block:
        lines.append("## Who Blake Is")
        short_bio = who_block.get("short_bio")
        present = who_block.get("current_context")
        if short_bio:
            lines.append(short_bio)
            lines.append("")
        if present:
            lines.append(f"Current Context: {present}")
            lines.append("")
        beats = _to_list(who_block.get("timeline_beats"))
        if beats:
            lines.append("Timeline Highlights:")
            for beat in beats:
                lines.append(f"- {beat}")
            lines.append("")

    identity = data.get("identity_core")
    if isinstance(identity, dict) and identity:
        lines.append("## Identity Core")
        who = identity.get("who_he_is")
        if who:
            lines.append(f"- Who He Is: {who}")
        beliefs = _to_list(identity.get("core_beliefs"))
        for belief in beliefs:
            lines.append(f"- Core Belief: {belief}")
        emotional_home = identity.get("emotional_home_base")
        if emotional_home:
            lines.append(f"- Emotional Home Base: {emotional_home}")
        mission = identity.get("public_mission")
        if mission:
            lines.append(f"- Public Mission: {mission}")
        tension = identity.get("private_tension")
        if tension:
            lines.append(f"- Private Tension: {tension}")
        shift = identity.get("current_voice_shift")
        if shift:
            lines.append(f"- Current Shift: {shift}")
        lines.append("")
    elif identity:
        lines.extend(["## Identity Core", str(identity).strip(), ""])

    rules = data.get("voice_rules") or {}
    if rules:
        lines.append("## Voice Rules")
        if isinstance(rules, dict):
            ordered_keys = [
                "cadence_rules",
                "syntax_rules",
                "bridge_phrases",
                "openers",
                "closers",
                "preferred_pronouns",
                "vocabulary_preferences",
                "emotional_register",
                "comment_length_rules",
            ]
            for key in ordered_keys:
                vals = _to_list(rules.get(key))
                if not vals:
                    continue
                label = key.replace("_", " ").title()
                lines.append(f"### {label}")
                for val in vals:
                    lines.append(f"- {val}")
                lines.append("")
        else:
            for rule in _to_list(rules):
                lines.append(f"- {rule}")
        lines.append("")

    anti = data.get("anti_patterns") or []
    if anti:
        lines.append("## Anti-Patterns")
        for item in anti:
            if isinstance(item, dict):
                name = item.get("name", "Unnamed")
                reason = item.get("why_wrong", "")
                lines.append(f"- {name}: {reason}".strip())
            else:
                lines.append(f"- {item}")
        lines.append("")

    buckets = data.get("bucket_examples") or {}
    if buckets:
        lines.append("## Bucket Examples")
        if isinstance(buckets, dict):
            for bucket_name, examples in buckets.items():
                lines.append(f"### {_bucket_title(str(bucket_name))}")
                for ex in _to_list(examples):
                    if isinstance(ex, dict):
                        example_text = (ex.get("example") or "").strip()
                        why = (ex.get("why_it_works") or "").strip()
                        context_fit = (ex.get("context_fit") or "").strip()
                        if example_text:
                            lines.append(f"- {example_text}")
                        if why:
                            lines.append(f"  Why it works: {why}")
                        if context_fit:
                            lines.append(f"  Best when: {context_fit}")
                    else:
                        lines.append(f"- {ex}")
                lines.append("")
        else:
            for bucket in _to_list(buckets):
                if not isinstance(bucket, dict):
                    continue
                lines.append(f"### {bucket.get('bucket', 'Bucket')}")
                for ex in _to_list(bucket.get("examples")):
                    lines.append(f"- {ex}")
                lines.append("")

    generation_policy = data.get("generation_policy") or {}
    if isinstance(generation_policy, dict) and generation_policy:
        lines.append("## Generation Policy")
        default_mode = generation_policy.get("default_voice_mode")
        if default_mode:
            lines.append(f"- Default Mode: {default_mode}")
        emphasize = _to_list(generation_policy.get("what_to_emphasize_for_current_comments"))
        if emphasize:
            lines.append("- Emphasize:")
            for item in emphasize:
                lines.append(f"  - {item}")
        deemphasize = _to_list(generation_policy.get("what_to_de_emphasize_for_current_comments"))
        if deemphasize:
            lines.append("- De-Emphasize:")
            for item in deemphasize:
                lines.append(f"  - {item}")
        facts_rule = generation_policy.get("facts_vs_style_rule")
        if facts_rule:
            lines.append(f"- Facts vs Style: {facts_rule}")
        retrieval_rule = generation_policy.get("retrieval_rule")
        if retrieval_rule:
            lines.append(f"- Retrieval Rule: {retrieval_rule}")
        lines.append("")

    checklist = data.get("generation_checklist") or data.get("comment_generation_checklist") or []
    if checklist:
        lines.append("## Generation Checklist")
        for item in _to_list(checklist):
            lines.append(f"- {item}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def run_character_bible(
    pool: ModelPool,
    run_dir: Path,
    prompt_dir: Path,
    model: str,
    dry_run: bool,
    source_weights: Dict[str, float],
    era_weights: Dict[str, float],
    extracted: Dict[str, Any],
    identity_grounding: Dict[str, Any],
) -> Dict[str, Any]:
    json_path = run_dir / "07_character_bible.json"
    md_path = run_dir / "07_character_bible.md"
    system_prompt = load_prompt_template(prompt_dir, "05_character_bible_assembly.md")

    if dry_run:
        data = {
            "dry_run": True,
            "identity_core": "",
            "voice_rules": [],
            "anti_patterns": [],
            "bucket_examples": [],
            "generation_checklist": [],
            "notes": "LLM call skipped (dry-run).",
        }
        write_json(json_path, data)
        md_path.write_text(render_character_bible_md(data), encoding="utf-8")
        return data

    payload = {
        "source_weights": source_weights,
        "era_weights": era_weights,
        "extracted_layers": extracted,
        "identity_grounding": identity_grounding,
        "requirements": {
            "temporal_priority": "Prioritize 2025-2026 voice for current mental-health comments.",
            "max_comment_length_sentences": 4,
            "avoid_generic_therapy_speak": True,
            "avoid_corporate_voice": True,
            "comment_target": "Instagram comments on mental-health influencer posts",
            "goal": "Should read like Blake himself wrote it today",
        },
    }
    user_prompt = (
        "Assemble the final Blake character bible from extraction layers.\n"
        "Return a practical generation-ready artifact for Instagram comment writing.\n"
        "Keep it concise, precise, and non-generic.\n\n"
        "Critical quality requirements:\n"
        "- Include a strong `who_blake_is` block with concrete biography + current context.\n"
        "- Use `identity_grounding` for factual identity anchors; do not invent facts.\n"
        "- `bucket_examples` must contain concrete sample comments, not abstract labels.\n"
        "- Every sample comment should sound first-person, warm, vulnerable, and non-preachy.\n"
        "- Preserve current voice: post-crisis, Enough-era, emotionally grounded.\n\n"
        "Output compactness constraints:\n"
        "- who_blake_is.timeline_beats: max 6 bullets.\n"
        "- voice_rules arrays: max 4 items per array.\n"
        "- anti_patterns: max 10.\n"
        "- bucket_examples: 4 buckets, max 3 examples each.\n"
        "- Each bucket example: <=4 sentences.\n"
        "- comment_generation_checklist: max 12.\n"
        "- Keep total response concise so it fits token limits.\n\n"
        "Input JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n\n"
        "Return strict JSON only."
    )
    data = llm_json_with_retry(
        client=pool.client(model),
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.0,
        max_tokens=int(LLM_MAX_TOKENS["character_bible"]),
    )
    write_json(json_path, data)
    md_path.write_text(render_character_bible_md(data), encoding="utf-8")
    return data


def load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {
            "source_weights": DEFAULT_SOURCE_WEIGHTS,
            "era_weights": DEFAULT_ERA_WEIGHTS,
            "models": DEFAULT_MODELS,
            "batch_sizes": {"instagram": 30},
            "chunk_chars": {
                "youtube": 4500,
                "longform": 12000,
                "podcast_depth": 5000,
                "written_values": 2800,
                "calibration": 2200,
            },
            "max_chunks_per_doc": {
                "youtube": 2,
                "longform": 4,
                "podcast_depth": 2,
                "written_values": 2,
                "calibration": 1,
            },
            "llm_max_tokens": DEFAULT_LLM_MAX_TOKENS,
        }
    data = json.loads(path.read_text(encoding="utf-8"))
    return data


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def prepare_corpus(blake_root: Path) -> Tuple[List[SourceDoc], List[Dict[str, Any]]]:
    youtube_docs = load_txt_docs(
        [p for p in (blake_root / "podcasts" / "youtube").glob("*.txt") if not p.name.startswith("youtube_")],
        bucket="youtube_transcripts",
        source_group_default="youtube",
    )
    tim_docs = load_txt_docs(
        (blake_root / "podcasts" / "tim_ferriss").glob("*.txt"),
        bucket="podcast_transcripts",
        source_group_default="tim_ferriss",
    )
    substack_docs = load_txt_docs(
        (blake_root / "self" / "substack").glob("*.txt"),
        bucket="substack_posts",
        source_group_default="substack",
    )
    personal_docs = load_txt_docs(
        (blake_root / "self" / "personal_site").glob("*.txt"),
        bucket="personal_site_pages",
        source_group_default="personal_site",
    )
    article_docs = load_txt_docs(
        (blake_root / "articles").glob("*.txt"),
        bucket="external_articles",
        source_group_default="articles",
    )
    docs = youtube_docs + tim_docs + substack_docs + personal_docs + article_docs
    captions = load_instagram_captions(blake_root / "instagram" / "captions.csv")
    return docs, captions


def build_stats(docs: List[SourceDoc], captions: List[Dict[str, Any]]) -> Dict[str, Any]:
    bucket_counts: Dict[str, int] = {}
    era_counts: Dict[str, int] = {}
    for d in docs:
        bucket_counts[d.bucket] = bucket_counts.get(d.bucket, 0) + 1
        era_counts[d.era] = era_counts.get(d.era, 0) + 1

    cap_era_counts: Dict[str, int] = {}
    for row in captions:
        era = row.get("era", "unknown")
        cap_era_counts[era] = cap_era_counts.get(era, 0) + 1

    return {
        "doc_count": len(docs),
        "caption_count": len(captions),
        "doc_bucket_counts": bucket_counts,
        "doc_era_counts": era_counts,
        "caption_era_counts": cap_era_counts,
    }


def select_podcast_depth_docs(docs: List[SourceDoc]) -> List[SourceDoc]:
    selected: List[SourceDoc] = []
    for d in docs:
        if d.bucket == "podcast_transcripts":
            selected.append(d)
            continue
        if d.bucket != "youtube_transcripts":
            continue
        title_l = d.title.lower()
        if any(
            k in title_l
            for k in [
                "rich roll",
                "lifelong seeker",
                "enough",
                "identity",
                "healing",
                "midlife",
                "nearly broke",
            ]
        ):
            selected.append(d)
    return selected


def select_written_depth_docs(docs: List[SourceDoc]) -> List[SourceDoc]:
    return [d for d in docs if d.bucket in {"substack_posts", "personal_site_pages"}]


def select_calibration_docs(docs: List[SourceDoc]) -> List[SourceDoc]:
    return [d for d in docs if d.bucket == "external_articles"]


def run_pipeline(args: argparse.Namespace) -> int:
    global LLM_MAX_TOKENS

    blake_root = Path(args.blake_root)
    prompt_dir = Path(args.prompt_dir)
    config_path = Path(args.config)
    config = load_config(config_path)

    source_weights = config.get("source_weights", DEFAULT_SOURCE_WEIGHTS)
    era_weights = config.get("era_weights", DEFAULT_ERA_WEIGHTS)
    models = config.get("models", DEFAULT_MODELS)
    batch_sizes = config.get("batch_sizes", {"instagram": 30})
    chunk_chars = config.get("chunk_chars", {"youtube": 12000, "longform": 12000})
    max_chunks_per_doc = config.get("max_chunks_per_doc", {"youtube": 4, "longform": 4, "calibration": 2})
    llm_max_tokens = config.get("llm_max_tokens", {})
    LLM_MAX_TOKENS = {**DEFAULT_LLM_MAX_TOKENS, **llm_max_tokens}

    run_id = args.run_id or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = ensure_dir(Path(args.run_dir) / run_id)
    ensure_dir(run_dir / "00_corpus")
    debug_llm_dir = ensure_dir(run_dir / "_debug_llm")

    docs, captions = prepare_corpus(blake_root=blake_root)
    identity_grounding = build_identity_grounding(blake_root=blake_root)
    stats = build_stats(docs, captions)
    write_json(run_dir / "00_corpus" / "stats.json", stats)
    write_jsonl(
        run_dir / "00_corpus" / "docs.jsonl",
        [
            {
                "doc_id": d.doc_id,
                "bucket": d.bucket,
                "source_group": d.source_group,
                "era": d.era,
                "date_key": d.date_key,
                "title": d.title,
                "path": d.path,
                "url": d.url,
                "text_length": len(d.text),
            }
            for d in docs
        ],
    )
    write_json(run_dir / "00_corpus" / "weights.json", {"source_weights": source_weights, "era_weights": era_weights})

    if args.dry_run:
        print("[voice_builder] dry-run mode enabled; LLM calls will be skipped.")

    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not args.dry_run and not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required unless --dry-run is enabled.")

    pool = ModelPool(
        api_key=api_key or "dry-run-key",
        app_name="Blake Voice Builder",
        app_url="https://example.com/blake-voice-builder",
    )

    extract_model = args.extract_model or models.get("extract", DEFAULT_MODELS["extract"])
    synthesis_model = args.synthesis_model or models.get("synthesis", DEFAULT_MODELS["synthesis"])

    print(f"[voice_builder] run_id={run_id}")
    print(f"[voice_builder] docs={len(docs)} captions={len(captions)}")
    print(f"[voice_builder] extract_model={extract_model}")
    print(f"[voice_builder] synthesis_model={synthesis_model}")

    selected_steps = parse_steps(args.steps)
    completed_steps: List[str] = []
    print(f"[voice_builder] selected_steps={','.join(selected_steps)}")

    step_paths = {
        "01_instagram": run_dir / "01_instagram_patterns" / "consolidated.json",
        "02_youtube": run_dir / "02_youtube_primitives" / "consolidated.json",
        "03_podcast_depth": run_dir / "03_podcast_depth" / "consolidated.json",
        "04_written_values": run_dir / "04_written_values" / "consolidated.json",
        "05_external_calibration": run_dir / "05_external_calibration" / "consolidated.json",
        "06_antipatterns": run_dir / "06_antipatterns.json",
        "07_character_bible_json": run_dir / "07_character_bible.json",
        "07_character_bible_md": run_dir / "07_character_bible.md",
    }

    def require_output(step_key: str, command_hint: str) -> Dict[str, Any]:
        path = step_paths[step_key]
        if not path.exists():
            raise RuntimeError(
                f"Missing prerequisite output: {path}. Run step first with: "
                f"python3 blake/scripts/run_voice_builder.py --run-id {run_id} --steps {command_hint}"
            )
        return load_json(path)

    instagram_out: Optional[Dict[str, Any]] = None
    youtube_out: Optional[Dict[str, Any]] = None
    podcast_out: Optional[Dict[str, Any]] = None
    written_out: Optional[Dict[str, Any]] = None
    calibration_out: Optional[Dict[str, Any]] = None
    antipatterns_out: Optional[Dict[str, Any]] = None
    character_data: Optional[Dict[str, Any]] = None

    if "01_instagram" in selected_steps:
        instagram_out = run_instagram_patterns(
            pool=pool,
            run_dir=run_dir,
            prompt_dir=prompt_dir,
            captions=captions,
            model=extract_model,
            source_weights=source_weights,
            era_weights=era_weights,
            dry_run=args.dry_run,
            batch_size=int(batch_sizes.get("instagram", 30)),
        )
        completed_steps.append("01_instagram")
        print("[voice_builder] completed step 01 (instagram patterns)")

    if "02_youtube" in selected_steps:
        youtube_docs = [d for d in docs if d.bucket == "youtube_transcripts"]
        youtube_out = run_youtube_primitives(
            pool=pool,
            run_dir=run_dir,
            prompt_dir=prompt_dir,
            docs=youtube_docs,
            model=extract_model,
            source_weights=source_weights,
            era_weights=era_weights,
            dry_run=args.dry_run,
            max_chars_per_chunk=int(chunk_chars.get("youtube", 4500)),
            max_chunks_per_doc=int(max_chunks_per_doc.get("youtube", 2)),
            debug_dir=debug_llm_dir / "02_youtube",
        )
        completed_steps.append("02_youtube")
        print("[voice_builder] completed step 02 (youtube primitives)")

    if "03_podcast_depth" in selected_steps:
        podcast_docs = select_podcast_depth_docs(docs)
        podcast_out = run_longform_depth(
            pool=pool,
            run_dir=run_dir,
            prompt_dir=prompt_dir,
            docs=podcast_docs,
            model=extract_model,
            source_weights=source_weights,
            era_weights=era_weights,
            dry_run=args.dry_run,
            step_name="03_podcast_depth",
            prompt_file="03_podcast_depth_arcs.md",
            objective="Extract deep personal narrative arcs and inner-life language from long-form spoken sources.",
            max_chars_per_chunk=int(chunk_chars.get("podcast_depth", 5000)),
            max_chunks_per_doc=int(max_chunks_per_doc.get("podcast_depth", 2)),
            chunk_token_key="podcast_chunk",
            consolidate_doc_token_key="podcast_consolidate_doc",
            consolidate_global_token_key="podcast_consolidate_global",
            debug_dir=debug_llm_dir / "03_podcast_depth",
        )
        completed_steps.append("03_podcast_depth")
        print("[voice_builder] completed step 03 (podcast depth arcs)")

    if "04_written_values" in selected_steps:
        written_docs = select_written_depth_docs(docs)
        written_out = run_longform_depth(
            pool=pool,
            run_dir=run_dir,
            prompt_dir=prompt_dir,
            docs=written_docs,
            model=extract_model,
            source_weights=source_weights,
            era_weights=era_weights,
            dry_run=args.dry_run,
            step_name="04_written_values",
            prompt_file="04_written_values_extraction.md",
            objective="Extract values hierarchy, deliberate rhetoric, and intentional written voice from Substack + personal site.",
            max_chars_per_chunk=int(chunk_chars.get("written_values", 2800)),
            max_chunks_per_doc=int(max_chunks_per_doc.get("written_values", 2)),
            chunk_token_key="written_chunk",
            consolidate_doc_token_key="written_consolidate_doc",
            consolidate_global_token_key="written_consolidate_global",
            debug_dir=debug_llm_dir / "04_written_values",
        )
        completed_steps.append("04_written_values")
        print("[voice_builder] completed step 04 (written values)")

    if "05_external_calibration" in selected_steps:
        calibration_docs = select_calibration_docs(docs)
        calibration_out = run_longform_depth(
            pool=pool,
            run_dir=run_dir,
            prompt_dir=prompt_dir,
            docs=calibration_docs,
            model=extract_model,
            source_weights=source_weights,
            era_weights=era_weights,
            dry_run=args.dry_run,
            step_name="05_external_calibration",
            prompt_file="05_external_calibration_compact.md",
            objective="Extract third-person descriptors only for calibration; avoid using this source as primary style signal.",
            max_chars_per_chunk=int(chunk_chars.get("calibration", 2200)),
            max_chunks_per_doc=int(max_chunks_per_doc.get("calibration", 1)),
            chunk_token_key="calibration_chunk",
            consolidate_doc_token_key="calibration_consolidate_doc",
            consolidate_global_token_key="calibration_consolidate_global",
            debug_dir=debug_llm_dir / "05_external_calibration",
        )
        completed_steps.append("05_external_calibration")
        print("[voice_builder] completed step 05 (external calibration)")

    if "06_antipatterns" in selected_steps:
        positive_inputs = {
            "instagram_patterns": instagram_out or require_output("01_instagram", "01_instagram"),
            "youtube_primitives": youtube_out or require_output("02_youtube", "02_youtube"),
            "podcast_depth": podcast_out or require_output("03_podcast_depth", "03_podcast_depth"),
            "written_values": written_out or require_output("04_written_values", "04_written_values"),
            "external_calibration": calibration_out or require_output(
                "05_external_calibration", "05_external_calibration"
            ),
        }
        antipatterns_out = run_antipatterns(
            pool=pool,
            run_dir=run_dir,
            prompt_dir=prompt_dir,
            model=synthesis_model,
            dry_run=args.dry_run,
            positive_inputs=positive_inputs,
        )
        completed_steps.append("06_antipatterns")
        print("[voice_builder] completed step 06 (anti-pattern generation)")

    if "07_character_bible" in selected_steps:
        positive_inputs = {
            "instagram_patterns": instagram_out or require_output("01_instagram", "01_instagram"),
            "youtube_primitives": youtube_out or require_output("02_youtube", "02_youtube"),
            "podcast_depth": podcast_out or require_output("03_podcast_depth", "03_podcast_depth"),
            "written_values": written_out or require_output("04_written_values", "04_written_values"),
            "external_calibration": calibration_out or require_output(
                "05_external_calibration", "05_external_calibration"
            ),
        }
        antipatterns_resolved = antipatterns_out or require_output("06_antipatterns", "06_antipatterns")
        character_data = run_character_bible(
            pool=pool,
            run_dir=run_dir,
            prompt_dir=prompt_dir,
            model=synthesis_model,
            dry_run=args.dry_run,
            source_weights=source_weights,
            era_weights=era_weights,
            extracted={
                **positive_inputs,
                "anti_patterns": antipatterns_resolved,
            },
            identity_grounding=identity_grounding,
        )
        completed_steps.append("07_character_bible")
        print("[voice_builder] completed step 07 (character bible)")

    print(f"[voice_builder] outputs -> {run_dir}")

    run_summary = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "dry_run": bool(args.dry_run),
        "selected_steps": selected_steps,
        "completed_steps": completed_steps,
        "extract_model": extract_model,
        "synthesis_model": synthesis_model,
        "llm_max_tokens": LLM_MAX_TOKENS,
        "stats": stats,
        "character_bible_path_json": str(step_paths["07_character_bible_json"]),
        "character_bible_path_md": str(step_paths["07_character_bible_md"]),
        "character_bible_keys": sorted(
            list((character_data or load_json(step_paths["07_character_bible_json"])).keys())
        )
        if step_paths["07_character_bible_json"].exists()
        else [],
    }
    write_json(run_dir / "run_summary.json", run_summary)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the layered Blake voice extraction pipeline (Instagram -> YouTube -> long-form depth -> "
            "anti-patterns -> final character bible) using OpenRouter."
        )
    )
    parser.add_argument("--blake-root", default="blake")
    parser.add_argument("--prompt-dir", default="blake/prompts/voice_builder")
    parser.add_argument("--config", default="blake/voice_builder/config.json")
    parser.add_argument("--run-dir", default="blake/voice_builder/runs")
    parser.add_argument("--run-id", default="")
    parser.add_argument(
        "--steps",
        default="all",
        help=(
            "Comma-separated steps to run. "
            "Valid: 01_instagram,02_youtube,03_podcast_depth,04_written_values,"
            "05_external_calibration,06_antipatterns,07_character_bible. "
            "Default: all."
        ),
    )
    parser.add_argument("--extract-model", default="")
    parser.add_argument("--synthesis-model", default="")
    parser.add_argument("--list-steps", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.list_steps:
        print("Available steps:")
        for step in STEP_ORDER:
            print(f"- {step}")
        return 0

    try:
        return run_pipeline(args)
    except Exception as exc:  # noqa: BLE001
        print(f"[voice_builder] error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
