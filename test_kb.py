"""
Tests for Phase 5 knowledge base loading and search.

No Gemini calls, no API key needed — search_kb() only reads local
markdown files and does word-overlap scoring.

Run:
    uv run pytest
"""

from kb import load_kb, search_kb


def test_load_kb_finds_articles():
    docs = load_kb()
    assert len(docs) >= 5
    doc_ids = {doc.doc_id for doc in docs}
    assert "orders" in doc_ids
    assert "refunds-and-returns" in doc_ids


def test_search_kb_finds_relevant_doc():
    results = search_kb("How do I reset my password?")
    assert len(results) > 0
    assert results[0].doc_id == "account-management"


def test_search_kb_finds_refund_doc():
    results = search_kb("When will I get my refund for a return?")
    assert len(results) > 0
    assert results[0].doc_id == "refunds-and-returns"


def test_search_kb_returns_empty_for_unrelated_query():
    results = search_kb("xyzzy plugh quux")
    assert results == []


def test_search_kb_respects_top_k():
    results = search_kb("order shipping payment refund account", top_k=2)
    assert len(results) <= 2
