from __future__ import annotations

import json
from typing import Any, Dict, Optional

import requests


class LLMError(RuntimeError):
    """Raised when LLM response is malformed or request fails."""


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
                f"OpenRouter request failed ({response.status_code}): {response.text[:500]}"
            )

        body = response.json()
        choices = body.get("choices") or []
        if not choices:
            raise LLMError("OpenRouter response contained no choices")

        content = choices[0].get("message", {}).get("content", "")
        if isinstance(content, list):
            content = "".join(
                str(part.get("text", "")) for part in content if isinstance(part, dict)
            )

        return self._extract_json_object(str(content))

    def _extract_json_object(self, content: str) -> Dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        # Fallback: parse first balanced JSON object.
        start = text.find("{")
        if start == -1:
            raise LLMError(f"No JSON object found in LLM output: {content[:300]}")

        depth = 0
        for idx in range(start, len(text)):
            char = text[idx]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    snippet = text[start : idx + 1]
                    try:
                        parsed = json.loads(snippet)
                        if isinstance(parsed, dict):
                            return parsed
                    except json.JSONDecodeError:
                        break

        raise LLMError(f"Unable to parse JSON object from LLM output: {content[:300]}")


def coerce_score(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return max(0.0, min(1.0, number))
