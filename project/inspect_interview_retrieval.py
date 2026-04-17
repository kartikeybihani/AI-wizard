from __future__ import annotations

import argparse
import json

from interview_server import RUNTIME


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect interview retrieval results for a question.")
    parser.add_argument("question", help="User question to inspect retrieval for.")
    parser.add_argument("--model", default="openai/gpt-5-mini")
    parser.add_argument("--max-tokens", type=int, default=220)
    args = parser.parse_args()

    payload = {
        "model": args.model,
        "messages": [{"role": "user", "content": args.question}],
        "temperature": 0.3,
        "max_tokens": int(args.max_tokens),
    }
    out = RUNTIME.generate(payload)
    meta = out.get("metadata") or {}
    answer = str((((out.get("choices") or [{}])[0].get("message") or {}).get("content") or "")).strip()

    print("QUESTION")
    print(args.question)
    print("\nANSWER")
    print(answer)
    print("\nRETRIEVAL_DEBUG")
    print(json.dumps(meta.get("retrieval_debug") or {}, indent=2, ensure_ascii=False))
    print("\nRETRIEVAL_HITS")
    print(json.dumps(meta.get("retrieval_hits") or {}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
