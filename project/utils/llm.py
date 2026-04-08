from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

import requests


class LLMError(RuntimeError):
    """Raised when LLM response is malformed or request fails."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.details = details or {}


class OpenRouterClient:
    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(
        self,
        api_key: str,
        model: str = "mistralai/mixtral-8x7b-instruct",
        timeout_seconds: int = 60,
        app_name: str = "TOMS Influencer Discovery",
        app_url: str = "https://example.com",
    ):
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is required to use OpenRouterClient")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.app_name = app_name
        self.app_url = app_url

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 600,
    ) -> Dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.app_url,
            "X-Title": self.app_name,
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }

        response = requests.post(
            self.BASE_URL,
            headers=headers,
            json=payload,
            timeout=self.timeout_seconds,
        )
        if not response.ok:
            raise LLMError(
                f"OpenRouter request failed ({response.status_code}): {response.text[:500]}",
                details={
                    "status_code": response.status_code,
                    "response_text_prefix": response.text[:2000],
                    "model": self.model,
                    "max_tokens": max_tokens,
                },
            )

        body = response.json()
        choices = body.get("choices") or []
        if not choices:
            raise LLMError("OpenRouter response contained no choices")

        first_choice = choices[0]
        finish_reason = str(first_choice.get("finish_reason", "") or "")
        content = first_choice.get("message", {}).get("content", "")
        usage = body.get("usage") or {}
        completion_tokens_raw = usage.get("completion_tokens")
        completion_tokens: Optional[int]
        try:
            completion_tokens = int(completion_tokens_raw)
        except (TypeError, ValueError):
            completion_tokens = None

        if isinstance(content, dict):
            return content
        if isinstance(content, list):
            content = "".join(
                str(part.get("text", "")) for part in content if isinstance(part, dict)
            )

        try:
            return self._extract_json_object(str(content))
        except LLMError as exc:
            likely_truncated = finish_reason.lower() == "length"
            if completion_tokens is not None and completion_tokens >= max_tokens - 2:
                likely_truncated = True

            if likely_truncated:
                raise LLMError(
                    "Model output likely truncated. "
                    f"finish_reason={finish_reason or 'unknown'}, "
                    f"completion_tokens={completion_tokens}, "
                    f"max_tokens={max_tokens}. "
                    f"Consider larger max_tokens or smaller input batch. Parse error: {exc}",
                    details={
                        "finish_reason": finish_reason,
                        "completion_tokens": completion_tokens,
                        "max_tokens": max_tokens,
                        "model": self.model,
                        "raw_content": str(content),
                    },
                ) from exc
            raise LLMError(
                "Model output was not valid JSON. "
                f"finish_reason={finish_reason or 'unknown'}, "
                f"completion_tokens={completion_tokens}. "
                f"Parse error: {exc}",
                details={
                    "finish_reason": finish_reason,
                    "completion_tokens": completion_tokens,
                    "max_tokens": max_tokens,
                    "model": self.model,
                    "raw_content": str(content),
                },
            ) from exc

    def _extract_json_object(self, content: str) -> Dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL | re.IGNORECASE)
            if fenced:
                text = fenced.group(1).strip()
            else:
                text = text.strip("`")
                if text.lower().startswith("json"):
                    text = text[4:].strip()

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        # Fallback 1: decode first JSON object from offset.
        start = text.find("{")
        if start == -1:
            raise LLMError(f"No JSON object found in LLM output: {content[:300]}")

        decoder = json.JSONDecoder()
        try:
            parsed, _end = decoder.raw_decode(text[start:])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        # Fallback 2: quote-aware balanced brace scan.
        in_string = False
        escape = False
        depth = 0
        for idx in range(start, len(text)):
            ch = text[idx]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    snippet = text[start : idx + 1]
                    parsed = self._parse_json_snippet(snippet)
                    if isinstance(parsed, dict):
                        return parsed

        # Likely truncated object if we saw a start brace but never closed depth.
        if depth > 0:
            raise LLMError(
                f"Unable to parse JSON object (likely truncated output). "
                f"LLM output prefix: {content[:300]}"
            )
        raise LLMError(f"Unable to parse JSON object from LLM output: {content[:300]}")

    def _parse_json_snippet(self, snippet: str) -> Optional[Dict[str, Any]]:
        candidates = [snippet]
        # Common cleanup: remove trailing commas before object/array close.
        candidates.append(re.sub(r",\s*([}\]])", r"\1", snippet))
        for cand in candidates:
            try:
                parsed = json.loads(cand)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue
        return None


def coerce_score(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return max(0.0, min(1.0, number))
