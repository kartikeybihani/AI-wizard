from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple


QUESTION_TYPES = (
    "factual_bio",
    "personal_emotional",
    "philosophical_advice",
    "pushback_clarification",
)

WORD_BUDGETS: Dict[str, Tuple[int, int]] = {
    "factual_bio": (40, 70),
    "personal_emotional": (90, 140),
    "philosophical_advice": (90, 140),
    "pushback_clarification": (60, 110),
}


@dataclass
class BoundaryDecision:
    blocked: bool
    reason: str
    response_template: str


class InterviewPolicy:
    def __init__(self, policy_path: Path):
        self.policy_path = Path(policy_path)
        self.payload: Dict[str, Any] = {}

    def load(self) -> None:
        if not self.policy_path.exists():
            raise FileNotFoundError(f"boundary policy not found: {self.policy_path}")
        self.payload = json.loads(self.policy_path.read_text(encoding="utf-8", errors="replace"))

    def classify_question_type(self, question: str) -> str:
        text = (question or "").lower().strip()
        if not text:
            return "factual_bio"

        pushback_tokens = ["are you sure", "that's not", "i disagree", "that doesn't sound right", "clarify", "but wait"]
        factual_tokens = ["when", "what year", "how old", "where", "launched", "founded", "timeline", "date"]
        emotional_tokens = ["depression", "anxiety", "identity", "breakdown", "healing", "struggle", "scared", "felt"]
        philosophy_tokens = ["purpose", "meaning", "enough", "advice", "lesson", "what did you learn", "mindset"]
        open_ended_tokens = [
            "tell me more",
            "say more",
            "go deeper",
            "can you elaborate",
            "elaborate",
            "expand on that",
            "keep going",
            "continue",
            "tell me about yourself",
            "how are you",
            "how are you doing",
            "what's coming up for you",
            "what does that mean for you",
        ]

        if any(token in text for token in pushback_tokens):
            return "pushback_clarification"
        if any(token in text for token in emotional_tokens):
            return "personal_emotional"
        if any(token in text for token in philosophy_tokens):
            return "philosophical_advice"
        if any(token in text for token in factual_tokens):
            return "factual_bio"
        if any(token in text for token in open_ended_tokens):
            return "philosophical_advice"

        words = text.split()
        if len(words) <= 6:
            # Short prompts without factual anchors are usually continuation/expansion asks.
            return "philosophical_advice"
        if len(words) > 16:
            return "philosophical_advice"
        if text.endswith("?"):
            # Generic open questions should bias reflective, not rigid factual snippets.
            return "philosophical_advice"
        return "factual_bio"

    def word_budget(self, question_type: str) -> Tuple[int, int]:
        return WORD_BUDGETS.get(question_type, (70, 120))

    def boundary_decision(self, question: str) -> BoundaryDecision:
        # Private/family topic boundary checks are intentionally disabled.
        # Keep this method for API compatibility and future toggles.
        return BoundaryDecision(
            blocked=False,
            reason="allowed",
            response_template="",
        )

    def uncertainty_line(self) -> str:
        cfg = (self.payload.get("insufficient_evidence") or {}) if isinstance(self.payload, dict) else {}
        lines = cfg.get("response_templates") or []
        if not lines:
            return "I don't remember the exact year, but it was around that period."
        return str(lines[0])


def compact_source_line(sources: List[str], max_items: int = 2) -> str:
    picked = [item for item in sources if item][: max(1, int(max_items))]
    return ", ".join(picked)
