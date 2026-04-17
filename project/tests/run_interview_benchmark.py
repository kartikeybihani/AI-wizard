from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_QUESTIONS = [
    "How are you doing? Tell me more about you.",
    "When did you launch TOMS?",
    "What happened emotionally after success?",
    "What does enough mean to you now?",
    "I don't think that's right, can you clarify?",
    "Tell me more.",
    "What year was the Argentina trip?",
    "What did you learn from depression?",
    "Give me advice for founders chasing validation.",
    "Can you talk about your kids?",
]


@dataclass
class CaseResult:
    question: str
    latency_ms: int
    ok: bool
    question_type: str
    used_fallback: bool
    boundary_blocked: bool
    llm_error: str
    response: str
    leaked_anchors: bool


def post_json(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw)


def run_case(base_url: str, question: str, model: str) -> CaseResult:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": question}],
        "temperature": 0.35,
        "max_tokens": 260,
    }

    started = time.perf_counter()
    body = post_json(f"{base_url.rstrip('/')}/v1/chat/completions", payload)
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    response = str((((body.get("choices") or [{}])[0].get("message") or {}).get("content") or "")).strip()
    meta = body.get("metadata") or {}
    llm_error = str(meta.get("llm_error") or "")

    return CaseResult(
        question=question,
        latency_ms=elapsed_ms,
        ok=bool(response),
        question_type=str(meta.get("question_type") or ""),
        used_fallback=bool(meta.get("used_fallback")),
        boundary_blocked=bool(meta.get("boundary_blocked")),
        llm_error=llm_error,
        response=response,
        leaked_anchors=("anchors:" in response.lower()),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local benchmark against interview server")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--model", default="openai/gpt-5-mini")
    parser.add_argument("--questions-json", default="")
    parser.add_argument("--limit", type=int, default=0, help="Run only first N questions (0 = all)")
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()

    questions = DEFAULT_QUESTIONS
    if args.questions_json:
        raw = Path(args.questions_json).read_text(encoding="utf-8")
        loaded = json.loads(raw)
        if isinstance(loaded, list) and all(isinstance(item, str) for item in loaded):
            questions = loaded

    if args.limit and args.limit > 0:
        questions = questions[: args.limit]

    results: List[CaseResult] = []
    for question in questions:
        result = run_case(args.base_url, question, args.model)
        results.append(result)

    latencies = [item.latency_ms for item in results]
    fallback_count = sum(1 for item in results if item.used_fallback)
    leak_count = sum(1 for item in results if item.leaked_anchors)

    print("\nInterview Benchmark Results")
    print("=" * 80)
    for idx, item in enumerate(results, start=1):
        print(
            f"{idx:02d}. latency={item.latency_ms:4d}ms | qtype={item.question_type:24s} "
            f"| fallback={str(item.used_fallback):5s} | boundary={str(item.boundary_blocked):5s}"
        )
        print(f"    Q: {item.question}")
        print(f"    A: {item.response[:190]}{'...' if len(item.response) > 190 else ''}")
        if item.llm_error:
            print(f"    ERR: {item.llm_error[:160]}")

    print("-" * 80)
    print(f"cases: {len(results)}")
    print(f"latency_ms_avg: {int(statistics.mean(latencies)) if latencies else 0}")
    print(f"latency_ms_p95: {int(sorted(latencies)[max(0, int(len(latencies)*0.95)-1)]) if latencies else 0}")
    print(f"fallback_rate: {fallback_count}/{len(results)}")
    print(f"anchor_leak_count: {leak_count}")

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(
                {
                    "summary": {
                        "cases": len(results),
                        "latency_ms_avg": int(statistics.mean(latencies)) if latencies else 0,
                        "fallback_count": fallback_count,
                        "anchor_leak_count": leak_count,
                    },
                    "results": [item.__dict__ for item in results],
                },
                indent=2,
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
