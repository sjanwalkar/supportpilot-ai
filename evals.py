"""
SupportPilot AI — Phase 11: Evals (scoring logic)

Goal: measure quality instead of eyeballing it.

This file holds ONLY the scoring logic — comparing an AgentState (the
same object every earlier phase already produces) against one golden
question's expected behavior. No network calls happen here, so this
half is unit-testable (test_evals.py) without any API key.

run_evals.py is the other half: it loads data/eval/golden_questions.json,
actually calls agent.run_agent() for each question — a REAL Gemini +
Pinecone call, unlike every `uv run pytest` test in this project — and
uses score_question() from this file to grade the result.

Metrics, adapted from the original Bitext-inspired plan to what this
system's actual pipeline produces:

  - citation_presence:  for a KB question, was ANY citation returned?
  - source_hit:         was the SPECIFIC expected KB article cited?
                         (this replaces "intent accuracy" from the
                         original plan — we don't have a separate intent
                         classifier, but which KB article gets retrieved
                         is a direct proxy for whether the right
                         topic/intent was recognized)
  - tool_call_correct:  for a question expecting a tool, was that exact
                         tool called?
  - escalation_correct: for a question expecting (or explicitly NOT
                         expecting) guardrail 1 to fire, did it match?
                         Two-sided on purpose — catches both a guardrail
                         that's too quiet AND one that's too trigger-happy
                         (like the stolen-package false positive we
                         specifically designed guardrails.py around).
  - no_guardrail_fired: for small-talk questions, did NO guardrail fire
                         at all? Direct regression protection for the
                         "thank you" / "ok, Thankyou." bugs found during
                         Phase 10 live testing.

A question "passes" only if every check that applies to it passes. A
question with no expectations set (e.g. just checking the app doesn't
crash on some input) passes vacuously.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class QuestionResult:
    """Scoring outcome for one golden question."""
    question_id: str
    message: str
    passed: bool
    checks: dict = field(default_factory=dict)  # only keys that applied to this question
    notes: list = field(default_factory=list)    # human-readable reasons for any failure


def score_question(question: dict, state) -> QuestionResult:
    """Compare an AgentState against one golden question's expectations.

    `state` is whatever agent.run_agent() returned for question["message"].
    This function only reads state.citations / state.tool_calls /
    state.guardrail_triggered — it never calls the agent itself, so it's
    fully testable with a hand-built fake state (see test_evals.py).
    """
    checks = {}
    notes = []

    expected_source = question.get("expected_source")
    if expected_source:
        citation_present = len(state.citations) > 0
        source_hit = expected_source in state.citations
        checks["citation_presence"] = citation_present
        checks["source_hit"] = source_hit
        if not citation_present:
            notes.append(f"expected a citation (source '{expected_source}'), got none")
        elif not source_hit:
            notes.append(f"expected source '{expected_source}', got citations {state.citations}")

    expected_tool = question.get("expected_tool")
    if expected_tool:
        tool_names = [tc["name"] for tc in state.tool_calls]
        tool_correct = expected_tool in tool_names
        checks["tool_call_correct"] = tool_correct
        if not tool_correct:
            notes.append(f"expected tool '{expected_tool}', got {tool_names or 'none'}")

    if "expect_escalation" in question:
        expect_escalation = question["expect_escalation"]
        did_escalate = state.guardrail_triggered == "sensitive_escalation"
        escalation_correct = did_escalate == expect_escalation
        checks["escalation_correct"] = escalation_correct
        if not escalation_correct:
            notes.append(
                f"expected escalation={expect_escalation}, got guardrail_triggered={state.guardrail_triggered!r}"
            )

    if question.get("expect_no_guardrail"):
        no_guardrail_fired = state.guardrail_triggered is None
        checks["no_guardrail_fired"] = no_guardrail_fired
        if not no_guardrail_fired:
            notes.append(f"expected no guardrail to fire, got guardrail_triggered={state.guardrail_triggered!r}")

    passed = all(checks.values()) if checks else True

    return QuestionResult(
        question_id=question["id"],
        message=question["message"],
        passed=passed,
        checks=checks,
        notes=notes,
    )


def summarize(results):
    """Aggregate a list of QuestionResults into per-metric pass rates.

    Returns {metric: (passed, total) or None if no question used that
    metric} plus an "overall" key for the whole-question pass rate.
    """

    def rate(key):
        applicable = [r for r in results if key in r.checks]
        if not applicable:
            return None
        passed = sum(1 for r in applicable if r.checks[key])
        return passed, len(applicable)

    return {
        "citation_presence": rate("citation_presence"),
        "source_hit": rate("source_hit"),
        "tool_call_correct": rate("tool_call_correct"),
        "escalation_correct": rate("escalation_correct"),
        "no_guardrail_fired": rate("no_guardrail_fired"),
        "overall": (sum(1 for r in results if r.passed), len(results)),
    }
