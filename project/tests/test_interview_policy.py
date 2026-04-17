from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from utils.interview_policy import InterviewPolicy


class InterviewPolicyTests(unittest.TestCase):
    def _policy(self) -> InterviewPolicy:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "boundary_policy.json"
            path.write_text(
                json.dumps(
                    {
                        "private_topics": {
                            "keywords": ["my wife", "my kids"],
                            "response_template": "I keep family details private.",
                        },
                        "insufficient_evidence": {
                            "response_templates": [
                                "I don't remember the exact year, but it was around that transition period.",
                            ]
                        },
                    }
                ),
                encoding="utf-8",
            )
            policy = InterviewPolicy(path)
            policy.load()
            # Return a loaded copy backed by a persistent temp path.
            # For this short-lived test this is fine because every assertion runs synchronously.
            return policy

    def test_open_ended_prompts_route_to_reflective(self) -> None:
        policy = self._policy()
        self.assertEqual("philosophical_advice", policy.classify_question_type("Tell me more"))
        self.assertEqual("philosophical_advice", policy.classify_question_type("How are you doing?"))
        self.assertEqual("philosophical_advice", policy.classify_question_type("Can you elaborate"))

    def test_self_update_prompts_route_to_current_work(self) -> None:
        policy = self._policy()
        self.assertEqual(
            "self_update_current_work",
            policy.classify_question_type("Why don't you tell me more about you and what you're doing now with Enough?"),
        )
        self.assertEqual(
            (110, 170),
            policy.word_budget("self_update_current_work"),
        )

    def test_founder_operator_prompts_route_correctly(self) -> None:
        policy = self._policy()
        self.assertEqual(
            "founder_operator",
            policy.classify_question_type("How did scaling TOMS change your leadership and operating strategy?"),
        )
        self.assertEqual(
            (85, 130),
            policy.word_budget("founder_operator"),
        )

    def test_factual_prompts_still_route_to_factual(self) -> None:
        policy = self._policy()
        self.assertEqual("factual_bio", policy.classify_question_type("What year did you launch TOMS?"))
        self.assertEqual("factual_bio", policy.classify_question_type("Where did this start?"))

    def test_boundary_allows_private_topics(self) -> None:
        policy = self._policy()
        decision = policy.boundary_decision("Can you tell me about my kids?")
        self.assertFalse(decision.blocked)
        self.assertEqual("allowed", decision.reason)

    def test_boundary_allows_family_questions_with_you_perspective(self) -> None:
        policy = self._policy()
        decision = policy.boundary_decision("Can you talk about your kids?")
        self.assertFalse(decision.blocked)
        self.assertEqual("allowed", decision.reason)


if __name__ == "__main__":
    unittest.main()
