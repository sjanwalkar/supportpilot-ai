"""
Tests for Phase 11 eval scoring logic.

score_question() only reads state.citations / state.tool_calls /
state.guardrail_triggered — these tests use a plain SimpleNamespace with
just those three attributes as a stand-in for a real AgentState, so this
file runs with no API key, no network, and without importing agent.py's
full dependency chain (google-genai, pinecone, mcp) at all.

Run:
    uv run pytest
"""

from types import SimpleNamespace

from evals import score_question, summarize


def _fake_state(citations=None, tool_calls=None, guardrail_triggered=None):
    return SimpleNamespace(
        citations=citations or [],
        tool_calls=tool_calls or [],
        guardrail_triggered=guardrail_triggered,
    )


def test_kb_question_passes_with_correct_source():
    question = {"id": "q1", "message": "refund policy?", "expected_source": "refunds-and-returns"}
    state = _fake_state(citations=["refunds-and-returns"])
    result = score_question(question, state)
    assert result.passed is True
    assert result.checks["citation_presence"] is True
    assert result.checks["source_hit"] is True


def test_kb_question_fails_with_no_citation():
    question = {"id": "q2", "message": "refund policy?", "expected_source": "refunds-and-returns"}
    state = _fake_state(citations=[])
    result = score_question(question, state)
    assert result.passed is False
    assert result.checks["citation_presence"] is False
    assert "expected a citation" in result.notes[0]


def test_kb_question_fails_with_wrong_source():
    question = {"id": "q3", "message": "refund policy?", "expected_source": "refunds-and-returns"}
    state = _fake_state(citations=["orders"])
    result = score_question(question, state)
    assert result.passed is False
    assert result.checks["citation_presence"] is True
    assert result.checks["source_hit"] is False


def test_tool_question_passes():
    question = {"id": "q4", "message": "look up CUST-001", "expected_tool": "get_customer_profile"}
    state = _fake_state(tool_calls=[{"name": "get_customer_profile", "args": {}, "result": {}}])
    result = score_question(question, state)
    assert result.passed is True


def test_tool_question_fails_with_wrong_tool():
    question = {"id": "q5", "message": "look up CUST-001", "expected_tool": "get_customer_profile"}
    state = _fake_state(tool_calls=[{"name": "check_feature_access", "args": {}, "result": {}}])
    result = score_question(question, state)
    assert result.passed is False


def test_escalation_expected_and_happened_passes():
    question = {"id": "q6", "message": "delete my account", "expect_escalation": True}
    state = _fake_state(guardrail_triggered="sensitive_escalation")
    result = score_question(question, state)
    assert result.passed is True


def test_escalation_expected_but_did_not_happen_fails():
    question = {"id": "q7", "message": "delete my account", "expect_escalation": True}
    state = _fake_state(guardrail_triggered=None)
    result = score_question(question, state)
    assert result.passed is False


def test_no_escalation_expected_and_none_happened_passes():
    question = {"id": "q8", "message": "package stolen", "expect_escalation": False}
    state = _fake_state(guardrail_triggered=None)
    result = score_question(question, state)
    assert result.passed is True


def test_no_escalation_expected_but_wrongly_escalated_fails():
    question = {"id": "q9", "message": "package stolen", "expect_escalation": False}
    state = _fake_state(guardrail_triggered="sensitive_escalation")
    result = score_question(question, state)
    assert result.passed is False


def test_no_guardrail_expected_and_none_fired_passes():
    question = {"id": "q10", "message": "thanks", "expect_no_guardrail": True}
    state = _fake_state(guardrail_triggered=None)
    result = score_question(question, state)
    assert result.passed is True


def test_no_guardrail_expected_but_one_fired_fails():
    question = {"id": "q11", "message": "thanks", "expect_no_guardrail": True}
    state = _fake_state(guardrail_triggered="missing_citation")
    result = score_question(question, state)
    assert result.passed is False


def test_question_with_no_expectations_passes_vacuously():
    question = {"id": "q12", "message": "hi"}
    state = _fake_state()
    result = score_question(question, state)
    assert result.passed is True
    assert result.checks == {}


def test_summarize_computes_rates():
    results = [
        score_question({"id": "a", "message": "m", "expected_source": "orders"}, _fake_state(citations=["orders"])),
        score_question({"id": "b", "message": "m", "expected_source": "orders"}, _fake_state(citations=[])),
    ]
    summary = summarize(results)
    assert summary["citation_presence"] == (1, 2)
    assert summary["source_hit"] == (1, 2)
    assert summary["overall"] == (1, 2)


def test_summarize_none_for_inapplicable_metric():
    results = [score_question({"id": "a", "message": "m", "expect_escalation": False}, _fake_state())]
    summary = summarize(results)
    assert summary["citation_presence"] is None
    assert summary["escalation_correct"] == (1, 1)
