"""
Tests for Phase 10 guardrails.

is_sensitive_request/extract_customer_id/has_required_citation/
contains_unsupported_commitment are pure string checks. check_sensitive_
request() does write a real ticket via crm.create_support_ticket() when
a customer id is present, so those tests point crm.DB_PATH at a temp
file first (same pattern as test_crm.py) — no API key or network needed
anywhere in this file.

Run:
    uv run pytest
"""

import tempfile
from pathlib import Path

import crm
import guardrails
from kb import KBDoc
from memory import Message


def _use_temp_db():
    tmp_dir = tempfile.mkdtemp()
    crm.DB_PATH = Path(tmp_dir) / "test.db"
    crm.init_db()


# --- is_sensitive_request / extract_customer_id ---


def test_is_sensitive_request_true_for_account_deletion():
    assert guardrails.is_sensitive_request("I want to delete my account") is True


def test_is_sensitive_request_true_case_insensitive():
    assert guardrails.is_sensitive_request("DISPUTE THIS CHARGE please") is True


def test_is_sensitive_request_false_for_ordinary_question():
    assert guardrails.is_sensitive_request("How do I track my order?") is False


def test_is_sensitive_request_false_for_stolen_package():
    # A stolen/missing PACKAGE is an ordinary, KB-coverable shipping
    # question -- it should NOT trigger escalation just because it
    # shares a word with account-security phrasing.
    assert guardrails.is_sensitive_request("My package was stolen off my porch") is False


def test_extract_customer_id_found():
    assert guardrails.extract_customer_id("My id is CUST-003, please help") == "CUST-003"


def test_extract_customer_id_case_insensitive():
    assert guardrails.extract_customer_id("my id is cust-007") == "CUST-007"


def test_extract_customer_id_missing():
    assert guardrails.extract_customer_id("I don't know my customer id") is None


def test_find_customer_id_prefers_current_message():
    history = [Message(role="user", content="my id is CUST-001")]
    assert guardrails.find_customer_id("actually it's CUST-002", history) == "CUST-002"


def test_find_customer_id_falls_back_to_history():
    history = [
        Message(role="user", content="someone accessed my account"),
        Message(role="assistant", content="Could you share your customer id?"),
        Message(role="user", content="CUST-002"),
        Message(role="assistant", content="I've opened ticket #4 for you."),
    ]
    assert guardrails.find_customer_id("what about a fraud case?", history) == "CUST-002"


def test_find_customer_id_none_when_nowhere():
    history = [Message(role="user", content="hello"), Message(role="assistant", content="hi there")]
    assert guardrails.find_customer_id("I have a question", history) is None


# --- is_smalltalk ---


def test_is_smalltalk_true_for_thanks():
    assert guardrails.is_smalltalk("thank you.") is True


def test_is_smalltalk_true_case_and_punctuation_insensitive():
    assert guardrails.is_smalltalk("  Thanks!  ") is True


def test_is_smalltalk_true_for_greeting():
    assert guardrails.is_smalltalk("hi") is True


def test_is_smalltalk_false_for_real_question():
    assert guardrails.is_smalltalk("How do I track my order?") is False


def test_is_smalltalk_false_when_word_is_only_a_substring():
    # These CONTAIN smalltalk words but are real questions -- exact
    # match (not substring) is what prevents these from misfiring.
    assert guardrails.is_smalltalk("no, I mean the other order") is False
    assert guardrails.is_smalltalk("hi, can you check my refund status") is False


def test_is_smalltalk_false_for_fraud_question():
    assert guardrails.is_smalltalk("what happens if a purchase was fraud case") is False


def test_is_smalltalk_true_for_compound_unspaced_variant():
    # The exact case reported live: no space between "Thank" and "you",
    # comma-joined with "ok", trailing period. This is what motivated
    # switching from exact-phrase matching to word-level matching.
    assert guardrails.is_smalltalk("ok, Thankyou.") is True


def test_is_smalltalk_true_for_various_real_world_phrasings():
    for message in [
        "Thanks!!",
        "ok thank you so much",
        "That's all, thank you!",
        "no thanks",
        "Great, thank you",
        "cool thanks",
    ]:
        assert guardrails.is_smalltalk(message) is True, f"expected small talk: {message!r}"


def test_is_smalltalk_false_for_real_questions_with_smalltalk_words_mixed_in():
    # Contains smalltalk-ish words but is a genuine question -- must
    # stay False because it also contains substantive words outside the
    # smalltalk vocabulary.
    for message in [
        "ok but what's your refund policy",
        "thanks, but I still need help with my order",
        "no I don't have my customer id",
    ]:
        assert guardrails.is_smalltalk(message) is False, f"expected NOT small talk: {message!r}"


# --- new sensitive-keyword phrasing ---


def test_is_sensitive_request_true_for_fraud_case_phrasing():
    assert guardrails.is_sensitive_request(
        "what happens if a purchase was made, but it was a fraud case?"
    ) is True


# --- has_required_citation ---


def test_has_required_citation_true_when_cited():
    docs = [KBDoc(doc_id="orders", title="Orders", text="...")]
    assert guardrails.has_required_citation("See [orders] for details.", docs) is True


def test_has_required_citation_false_when_missing():
    docs = [KBDoc(doc_id="orders", title="Orders", text="...")]
    assert guardrails.has_required_citation("You can track it in your account.", docs) is False


def test_has_required_citation_true_when_no_docs_to_check():
    # Vacuously fine -- nothing was retrieved, so there's nothing to cite.
    assert guardrails.has_required_citation("General answer, no KB used.", []) is False


# --- contains_unsupported_commitment ---


def test_contains_unsupported_commitment_true():
    assert guardrails.contains_unsupported_commitment("I guarantee this will be resolved.") is True


def test_contains_unsupported_commitment_false():
    assert guardrails.contains_unsupported_commitment("I'll do my best to help with that.") is False


# --- check_sensitive_request (writes to crm's DB when a customer id is present) ---


def test_check_sensitive_request_not_triggered_for_ordinary_message():
    result = guardrails.check_sensitive_request("How do I reset my password?")
    assert result.triggered is None


def test_check_sensitive_request_with_customer_id_creates_ticket():
    _use_temp_db()
    result = guardrails.check_sensitive_request(
        "CUST-001 here, someone accessed my account without permission"
    )
    assert result.triggered == "sensitive_escalation"
    assert "ticket #" in result.response

    with crm.get_connection() as conn:
        rows = conn.execute("SELECT customer_id, subject FROM tickets").fetchall()
    assert rows == [("CUST-001", "Escalated: sensitive request")]


def test_check_sensitive_request_without_customer_id_asks_for_one():
    _use_temp_db()
    result = guardrails.check_sensitive_request("Someone accessed my account without permission")
    assert result.triggered == "sensitive_escalation"
    assert "customer id" in result.response.lower()

    with crm.get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
    assert count == 0  # no ticket created without a customer id to attach it to


# --- check_response (post-answer citation + commitment checks) ---


def test_check_response_flags_missing_citation():
    docs = [KBDoc(doc_id="refunds-and-returns", title="Refunds", text="...")]
    result = guardrails.check_response("You can return it within 30 days.", docs)
    assert result.triggered == "missing_citation"


def test_check_response_passes_with_citation():
    docs = [KBDoc(doc_id="refunds-and-returns", title="Refunds", text="...")]
    result = guardrails.check_response("See [refunds-and-returns] for the policy.", docs)
    assert result.triggered is None


def test_check_response_flags_unsupported_commitment():
    result = guardrails.check_response("I guarantee this issue is fully resolved.", [])
    assert result.triggered == "unsupported_commitment"


def test_check_response_passes_clean_answer_with_no_docs():
    result = guardrails.check_response("Happy to help with anything else!", [])
    assert result.triggered is None


def test_check_response_skips_citation_check_when_tool_was_used():
    # Real bug this covers: a message can retrieve KB docs (even
    # low-relevance ones) AND trigger a tool call in the same turn. The
    # response is a report of the action taken ("I opened ticket #4"),
    # not a KB claim, so it must not be held to the citation requirement.
    docs = [KBDoc(doc_id="contacting-support", title="Contact", text="...")]
    tool_calls = [
        {"name": "create_support_ticket", "args": {"customer_id": "CUST-002"}, "result": {"ticket_id": 4}}
    ]
    result = guardrails.check_response("I've opened ticket #4 for you.", docs, tool_calls)
    assert result.triggered is None


def test_check_response_still_flags_missing_citation_with_empty_tool_calls_list():
    docs = [KBDoc(doc_id="orders", title="Orders", text="...")]
    result = guardrails.check_response("You can track it in your account.", docs, tool_calls=[])
    assert result.triggered == "missing_citation"
