from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from utils.interview_policy import InterviewPolicy, compact_source_line
from utils.interview_retrieval import LocalInterviewRetriever, RetrievedItem


def now_epoch() -> int:
    return int(time.time())


def project_root() -> Path:
    return Path(__file__).resolve().parent


def repo_root() -> Path:
    return project_root().parent


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
            value = value[1:-1]
        os.environ[key] = value


def resolve_config_path(raw_value: str, default_path: Path, base_dir: Path) -> Path:
    value = (raw_value or "").strip()
    if not value:
        return default_path
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = (base_dir / candidate).resolve()
    return candidate


def extract_message_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        out: List[str] = []
        for part in content:
            if isinstance(part, dict):
                text = str(part.get("text", "") or "").strip()
                if text:
                    out.append(text)
        return "\n".join(out).strip()
    return str(content or "").strip()


def extract_last_user_message(messages: List[Dict[str, Any]]) -> str:
    for msg in reversed(messages):
        if str(msg.get("role", "")).lower() != "user":
            continue
        text = extract_message_text(msg.get("content"))
        if text:
            return text
    return ""


def compact_history(messages: List[Dict[str, Any]], max_items: int = 8) -> List[Dict[str, str]]:
    compacted: List[Dict[str, str]] = []
    for msg in messages[-max_items:]:
        role = str(msg.get("role", "")).lower().strip()
        if role not in {"user", "assistant"}:
            continue
        text = extract_message_text(msg.get("content"))
        if not text:
            continue
        compacted.append({"role": role, "text": text})
    return compacted


@dataclass
class AppConfig:
    llm_provider: str
    llm_api_key: str
    llm_model: str
    llm_base_url: str
    embedding_provider: str
    embedding_api_key: str
    embedding_model: str
    embedding_base_url: str
    openrouter_http_referer: str
    openrouter_app_name: str
    knowledge_dir: Path
    char_bible_path: Path
    timeout_seconds: int


def load_config() -> AppConfig:
    repo = repo_root()
    proj = project_root()
    load_env_file(proj / ".env")
    knowledge_dir = resolve_config_path(
        os.getenv("INTERVIEW_KNOWLEDGE_DIR", ""),
        default_path=(repo / "blake" / "persona_interview" / "v1"),
        base_dir=proj,
    )
    char_bible_path = resolve_config_path(
        os.getenv("INTERVIEW_CHARACTER_BIBLE_PATH", ""),
        default_path=(repo / "blake" / "voice_builder" / "runs" / "blake_v1" / "07_character_bible.json"),
        base_dir=proj,
    )

    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "").strip()

    openrouter_http_referer = os.getenv("OPENROUTER_HTTP_REFERER", "").strip()
    openrouter_app_name = os.getenv("OPENROUTER_APP_NAME", "").strip()

    llm_provider = os.getenv("INTERVIEW_LLM_PROVIDER", "").strip().lower()
    if llm_provider not in {"openai", "openrouter"}:
        llm_provider = "openrouter" if openrouter_api_key else "openai"

    llm_api_key = os.getenv("INTERVIEW_LLM_API_KEY", "").strip()
    llm_base_url = os.getenv("INTERVIEW_LLM_BASE_URL", "").strip()

    if llm_provider == "openrouter":
        if not llm_api_key:
            llm_api_key = openrouter_api_key
        if not llm_base_url:
            llm_base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip()
        llm_model = os.getenv(
            "OPENROUTER_MODEL_INTERVIEW",
            os.getenv("OPENROUTER_MODEL", "openai/gpt-5-mini"),
        ).strip()
    else:
        if not llm_api_key:
            llm_api_key = openai_api_key
        if not llm_base_url:
            llm_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
        llm_model = os.getenv("OPENAI_MODEL_INTERVIEW", "gpt-5-mini").strip()

    embedding_provider = os.getenv("INTERVIEW_EMBEDDING_PROVIDER", "auto").strip().lower()
    if embedding_provider == "auto":
        if openai_api_key:
            embedding_provider = "openai"
        elif openrouter_api_key:
            embedding_provider = "openrouter"
        else:
            embedding_provider = "hash"
    if embedding_provider not in {"openai", "openrouter", "hash"}:
        embedding_provider = "hash"

    embedding_api_key = os.getenv("INTERVIEW_EMBEDDING_API_KEY", "").strip()
    embedding_base_url = os.getenv("INTERVIEW_EMBEDDING_BASE_URL", "").strip()
    if embedding_provider == "openrouter":
        if not embedding_api_key:
            embedding_api_key = openrouter_api_key
        if not embedding_base_url:
            embedding_base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip()
        embedding_model = os.getenv("OPENROUTER_EMBEDDING_MODEL", "openai/text-embedding-3-small").strip()
    elif embedding_provider == "openai":
        if not embedding_api_key:
            embedding_api_key = openai_api_key
        if not embedding_base_url:
            embedding_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
        embedding_model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small").strip()
    else:
        embedding_api_key = ""
        embedding_base_url = ""
        embedding_model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small").strip()

    return AppConfig(
        llm_provider=llm_provider,
        llm_api_key=llm_api_key,
        llm_model=llm_model,
        llm_base_url=llm_base_url.rstrip("/"),
        embedding_provider=embedding_provider,
        embedding_api_key=embedding_api_key,
        embedding_model=embedding_model,
        embedding_base_url=embedding_base_url.rstrip("/"),
        openrouter_http_referer=openrouter_http_referer,
        openrouter_app_name=openrouter_app_name,
        knowledge_dir=knowledge_dir,
        char_bible_path=char_bible_path,
        timeout_seconds=max(8, int(os.getenv("INTERVIEW_TIMEOUT_SECONDS", "30"))),
    )


class InterviewRuntime:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg

        self.policy = InterviewPolicy(policy_path=cfg.knowledge_dir / "boundary_policy.json")
        self.policy.load()

        self.retriever = LocalInterviewRetriever(
            knowledge_dir=cfg.knowledge_dir,
            embedding_api_key=cfg.embedding_api_key,
            embedding_model=cfg.embedding_model,
            embedding_base_url=cfg.embedding_base_url or "https://api.openai.com/v1",
            embedding_extra_headers=self._provider_headers(cfg.embedding_provider, include_content_type=False),
            timeout_seconds=cfg.timeout_seconds,
        )
        self.retriever.load()

        self.character_bible = load_json(cfg.char_bible_path, default={})

    def _provider_headers(self, provider: str, include_content_type: bool = True) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if include_content_type:
            headers["Content-Type"] = "application/json"
        if provider == "openrouter":
            if self.cfg.openrouter_http_referer:
                headers["HTTP-Referer"] = self.cfg.openrouter_http_referer
            if self.cfg.openrouter_app_name:
                headers["X-Title"] = self.cfg.openrouter_app_name
        return headers

    def _extract_session_id(self, payload: Dict[str, Any]) -> str:
        possible_containers: List[Any] = [
            payload.get("elevenlabs_extra_body"),
            payload.get("custom_llm_extra_body"),
            payload.get("metadata"),
        ]
        for container in possible_containers:
            if not isinstance(container, dict):
                continue
            raw = str(
                container.get("local_session_id")
                or container.get("session_id")
                or ""
            ).strip()
            if raw:
                return raw
        return ""

    def _append_session_event(self, session_id: str, event: Dict[str, Any]) -> None:
        if not session_id:
            return

        session_dir = repo_root() / "ui-blake" / "data" / "sessions" / session_id
        events_file = session_dir / "events.jsonl"
        if not events_file.exists():
            return

        row = {
            "ts": int(time.time() * 1000),
            **event,
        }
        with events_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _sanitize_retrieved_text(self, text: str) -> str:
        value = (text or "").strip()
        if not value:
            return ""
        value = re.sub(r"\s+", " ", value)
        value = re.sub(r"\s*Anchors:\s*", ". ", value, flags=re.IGNORECASE)
        value = re.sub(r"\[(\d{4})\]\s*", r"\1: ", value)
        value = re.sub(r"\s+\.\s+", ". ", value)
        return value.strip()

    def _format_retrieved(self, rows: List[RetrievedItem], label: str) -> str:
        if not rows:
            return f"{label}: (none)"
        lines = [f"{label}:"]
        for idx, row in enumerate(rows, start=1):
            cleaned_text = self._sanitize_retrieved_text(row.text)
            src_line = compact_source_line(row.sources)
            title = (row.title or row.item_id or "").strip()
            if cleaned_text:
                lines.append(f"{idx}. {title}: {cleaned_text}")
            else:
                lines.append(f"{idx}. {title}")
            if src_line:
                lines.append(f"   sources: {src_line}")
        return "\n".join(lines)

    def _build_system_prompt(
        self,
        question_type: str,
        min_words: int,
        max_words: int,
        retrieved_timeline: List[RetrievedItem],
        retrieved_stories: List[RetrievedItem],
        retrieved_policies: List[RetrievedItem],
    ) -> str:
        identity = self.character_bible.get("identity_core") or {}
        voice_rules = self.character_bible.get("voice_rules") or {}
        anti_patterns = self.character_bible.get("anti_patterns") or []

        identity_line = str(identity.get("who_he_is") or "Founder-turned-seeker voice, grounded and human.").strip()
        emotional_base = str(identity.get("emotional_home_base") or "calm, candid, grateful, grounded").strip()

        cadence_rules = ", ".join(voice_rules.get("cadence_rules") or [])
        syntax_rules = ", ".join(voice_rules.get("syntax_rules") or [])
        anti_line = ", ".join(str(item) for item in anti_patterns[:6])

        retrieved_block = "\n\n".join(
            [
                self._format_retrieved(retrieved_timeline, "Retrieved timeline"),
                self._format_retrieved(retrieved_stories, "Retrieved stories"),
                self._format_retrieved(retrieved_policies, "Retrieved policy"),
            ]
        )

        return (
            "You are AI Blake for a podcast interview simulation.\n"
            "Stay in first person and sound conversational, not scripted.\n"
            "\n"
            "Hard constraints:\n"
            "- Strict public-only policy. Do not disclose private family details.\n"
            "- Never invent precise dates, names, or events absent from retrieved evidence.\n"
            "- If uncertain, use human uncertainty language such as: 'I don't remember the exact year, but...'.\n"
            "- No diagnosis or treatment advice.\n"
            "- Keep one core idea per answer and avoid corporate PR language.\n"
            "- Never output internal scaffolding tokens like 'anchors', 'retrieved', 'score', or metadata labels.\n"
            "\n"
            f"Question type: {question_type}\n"
            f"Soft word budget: {min_words}-{max_words} words (not hard truncate).\n"
            "\n"
            "Answer style by question type:\n"
            "- factual_bio: direct answer first, then one short context sentence.\n"
            "- personal_emotional: acknowledge feeling, reflect honestly, close with grounded insight.\n"
            "- philosophical_advice: share principle from lived experience, not directives.\n"
            "- pushback_clarification: stay calm, clarify, and move conversation forward.\n"
            "\n"
            "Voice priors:\n"
            f"- Identity: {identity_line}\n"
            f"- Emotional base: {emotional_base}\n"
            f"- Cadence rules: {cadence_rules or 'short spoken clauses, natural pauses'}\n"
            f"- Syntax rules: {syntax_rules or 'first-person, reflective, non-prescriptive'}\n"
            f"- Anti-patterns: {anti_line}\n"
            "\n"
            "Use retrieved evidence below for facts/story anchors:\n"
            f"{retrieved_block}\n"
        )

    def _fallback_answer(
        self,
        question: str,
        question_type: str,
        retrieved_timeline: List[RetrievedItem],
        retrieved_stories: List[RetrievedItem],
    ) -> str:
        if retrieved_stories:
            card = retrieved_stories[0]
            cleaned = self._sanitize_retrieved_text(card.text)
            if question_type in {"personal_emotional", "philosophical_advice"}:
                return (
                    f"The way I think about it is this: {cleaned} "
                    "What mattered most to me was the shift underneath it, not the headline."
                )
            return (
                f"The way I remember it, {cleaned} "
                "I might be off on an exact date, but that period really changed how I thought about success and healing."
            )
        if retrieved_timeline:
            item = retrieved_timeline[0]
            cleaned = self._sanitize_retrieved_text(item.text)
            return (
                f"From what I've shared publicly, {cleaned} "
                "If you want, I can unpack what that season felt like for me."
            )
        return (
            "I don't want to fake details here. I can share what I've said publicly, "
            "and if there's a specific moment you're asking about, I'll stay with what I can verify."
        )

    def _call_llm_chat(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        temperature: float,
        max_tokens: int,
    ) -> str:
        if not self.cfg.llm_api_key:
            raise RuntimeError("Missing LLM API key. Set INTERVIEW_LLM_API_KEY or provider default key.")

        headers = {
            "Authorization": f"Bearer {self.cfg.llm_api_key}",
            **self._provider_headers(self.cfg.llm_provider),
        }

        def _extract_assistant_text(choice: Dict[str, Any]) -> str:
            message = choice.get("message") or {}
            text = extract_message_text(message.get("content"))
            if text:
                return text
            # Some providers expose legacy text on choice-level.
            alt_text = extract_message_text(choice.get("text"))
            if alt_text:
                return alt_text
            return ""

        def _request(payload: Dict[str, Any]) -> Dict[str, Any]:
            response = requests.post(
                f"{self.cfg.llm_base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.cfg.timeout_seconds,
            )
            if not response.ok:
                raise RuntimeError(f"LLM error {response.status_code}: {response.text[:300]}")
            return response.json()

        base_payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "max_completion_tokens": max_tokens,
        }

        body = _request(base_payload)
        choices = body.get("choices") or []
        if not choices:
            raise RuntimeError("No completion choices returned")
        choice = choices[0]
        text = _extract_assistant_text(choice)
        if text:
            return text

        # OpenRouter + GPT-5 can return empty content when reasoning consumes output budget.
        provider_model = str(body.get("model") or model).lower()
        if self.cfg.llm_provider == "openrouter" and "gpt-5" in provider_model:
            retry_max = max(900, int(max_tokens))
            retry_payload = {
                **base_payload,
                "max_tokens": retry_max,
                "max_completion_tokens": retry_max,
                "reasoning": {"effort": "minimal"},
            }
            body_retry = _request(retry_payload)
            choices_retry = body_retry.get("choices") or []
            if choices_retry:
                retry_text = _extract_assistant_text(choices_retry[0])
                if retry_text:
                    return retry_text
                retry_finish = str(choices_retry[0].get("finish_reason") or "")
                raise RuntimeError(f"Completion returned empty assistant content (retry_finish_reason={retry_finish})")

        finish_reason = str(choice.get("finish_reason") or "")
        raise RuntimeError(f"Completion returned empty assistant content (finish_reason={finish_reason})")

    def generate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        model = str(payload.get("model") or self.cfg.llm_model or "gpt-5-mini").strip()
        temperature = float(payload.get("temperature") if payload.get("temperature") is not None else 0.3)
        max_tokens = int(payload.get("max_tokens") if payload.get("max_tokens") is not None else 320)
        messages = payload.get("messages")
        if not isinstance(messages, list):
            messages = []

        question = extract_last_user_message(messages)
        if not question:
            question = "Could you share what this means to you right now?"
        session_id = self._extract_session_id(payload)

        boundary = self.policy.boundary_decision(question)
        question_type = self.policy.classify_question_type(question)
        min_words, max_words = self.policy.word_budget(question_type)

        retrieved = self.retriever.retrieve_mixed(question)
        timeline_rows = retrieved.get("timeline") or []
        story_rows = retrieved.get("stories") or []
        policy_rows = retrieved.get("policies") or []

        self._append_session_event(
            session_id=session_id,
            event={
                "type": "retrieval_hit",
                "question_type": question_type,
                "boundary_blocked": boundary.blocked,
                "retrieval_hits": {
                    "timeline": [item.item_id for item in timeline_rows],
                    "stories": [item.item_id for item in story_rows],
                    "policies": [item.item_id for item in policy_rows],
                },
            },
        )

        used_fallback = False
        llm_error: Optional[str] = None
        if boundary.blocked:
            assistant_text = boundary.response_template
        else:
            history = compact_history(messages)
            system_prompt = self._build_system_prompt(
                question_type=question_type,
                min_words=min_words,
                max_words=max_words,
                retrieved_timeline=timeline_rows,
                retrieved_stories=story_rows,
                retrieved_policies=policy_rows,
            )

            history_lines = "\n".join([f"{item['role']}: {item['text']}" for item in history])
            user_prompt = (
                "Current user question:\n"
                f"{question}\n\n"
                "Recent conversation context:\n"
                f"{history_lines or '(none)'}\n\n"
                "Respond naturally in spoken style."
            )

            llm_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            try:
                assistant_text = self._call_llm_chat(
                    model=model,
                    messages=llm_messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as exc:
                used_fallback = True
                llm_error = str(exc)[:400]
                assistant_text = self._fallback_answer(
                    question=question,
                    question_type=question_type,
                    retrieved_timeline=timeline_rows,
                    retrieved_stories=story_rows,
                )
                self._append_session_event(
                    session_id=session_id,
                    event={
                        "type": "llm_error",
                        "message": llm_error,
                        "used_fallback": True,
                    },
                )

        self._append_session_event(
            session_id=session_id,
            event={
                "type": "generation_result",
                "used_fallback": used_fallback,
                "response_chars": len(assistant_text or ""),
                "question_type": question_type,
            },
        )

        completion_id = f"chatcmpl_{uuid.uuid4().hex[:20]}"
        created = now_epoch()
        output = {
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": assistant_text,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
            "metadata": {
                "question_type": question_type,
                "word_budget": [min_words, max_words],
                "boundary_blocked": boundary.blocked,
                "used_fallback": used_fallback,
                "llm_error": llm_error,
                "retrieval_hits": {
                    "timeline": [item.item_id for item in timeline_rows],
                    "stories": [item.item_id for item in story_rows],
                    "policies": [item.item_id for item in policy_rows],
                },
            },
        }
        return output


CFG = load_config()
RUNTIME = InterviewRuntime(CFG)


class InterviewHandler(BaseHTTPRequestHandler):
    server_version = "InterviewServer/1.0"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        message = "%s - - [%s] %s" % (
            self.address_string(),
            self.log_date_time_string(),
            format % args,
        )
        print(message, flush=True)

    def _set_json_headers(self, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,Authorization")
        self.end_headers()

    def _set_sse_headers(self, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,Authorization")
        self.end_headers()

    def _write_json(self, payload: Dict[str, Any], status: int = 200) -> None:
        self._set_json_headers(status=status)
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def _write_stream(self, payload: Dict[str, Any], status: int = 200) -> None:
        self._set_sse_headers(status=status)
        now = int(payload.get("created") or now_epoch())
        chat_id = str(payload.get("id") or f"chatcmpl_{uuid.uuid4().hex[:20]}")
        model = str(payload.get("model") or CFG.llm_model)
        content = ""
        try:
            content = str(
                (((payload.get("choices") or [{}])[0].get("message") or {}).get("content"))
                or ""
            )
        except Exception:
            content = ""

        first = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": now,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": content},
                    "finish_reason": None,
                }
            ],
        }
        last = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": now,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",
                }
            ],
        }
        self.wfile.write(f"data: {json.dumps(first, ensure_ascii=False)}\n\n".encode("utf-8"))
        self.wfile.write(f"data: {json.dumps(last, ensure_ascii=False)}\n\n".encode("utf-8"))
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()
        self.close_connection = True

    def _read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8", errors="replace"))

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._set_json_headers(status=204)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz":
            return self._write_json(
                {
                    "ok": True,
                    "service": "interview_server",
                    "knowledge_dir": str(CFG.knowledge_dir),
                    "llm_provider": CFG.llm_provider,
                    "model": CFG.llm_model,
                    "embedding_provider": CFG.embedding_provider,
                    "embedding_model": CFG.embedding_model,
                }
            )
        self._write_json({"error": "Not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/v1/chat/completions":
            try:
                payload = self._read_json_body()
                result = RUNTIME.generate(payload)
                if bool(payload.get("stream")):
                    return self._write_stream(result, status=200)
                return self._write_json(result, status=200)
            except Exception as exc:  # noqa: BLE001
                return self._write_json(
                    {
                        "error": {
                            "message": str(exc),
                            "type": "server_error",
                        }
                    },
                    status=500,
                )

        self._write_json({"error": "Not found"}, status=404)


def run() -> None:
    host = os.getenv("INTERVIEW_SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("INTERVIEW_SERVER_PORT", "8787"))
    server = ThreadingHTTPServer((host, port), InterviewHandler)
    print(
        f"[interview_server] listening on http://{host}:{port} "
        f"(llm_provider={CFG.llm_provider}, model={CFG.llm_model}, embedding_provider={CFG.embedding_provider})"
    )
    server.serve_forever()


if __name__ == "__main__":
    run()
