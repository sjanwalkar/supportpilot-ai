"""
Tests for Phase 6's pure helper functions.

doc_to_metadata()/metadata_to_doc() are plain dict <-> dataclass
conversions with no network call, no Gemini, no Pinecone. embed_text()
and search_kb() do need real credentials and a live Pinecone index, so
they're deliberately NOT tested here — this file only covers the parts
that can be tested without any external service.

Run:
    uv run pytest
"""

from kb import KBDoc
from vector_search import doc_to_metadata, metadata_to_doc


def test_doc_to_metadata_shape():
    doc = KBDoc(doc_id="orders", title="Orders", text="Some order info.")
    metadata = doc_to_metadata(doc)
    assert metadata == {
        "doc_id": "orders",
        "title": "Orders",
        "text": "Some order info.",
    }


def test_metadata_to_doc_shape():
    metadata = {"doc_id": "orders", "title": "Orders", "text": "Some order info."}
    doc = metadata_to_doc(metadata)
    assert isinstance(doc, KBDoc)
    assert doc.doc_id == "orders"
    assert doc.title == "Orders"
    assert doc.text == "Some order info."


def test_metadata_round_trip():
    original = KBDoc(doc_id="refunds-and-returns", title="Refunds", text="Refund policy text.")
    round_tripped = metadata_to_doc(doc_to_metadata(original))
    assert round_tripped == original
