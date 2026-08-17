"""
SupportPilot AI — Phase 6: Pinecone Vector Search (RAG v2)

Replaces Phase 5's keyword-overlap search with real semantic search:

    message -> embed_text(message) -> query Pinecone -> top KB docs

Same search_kb() shape as kb.py's Phase 5 version — same input, same
List[KBDoc] output. That's why agent.py only needs one import line
changed to use this instead: nothing about prompt building, citations,
or the rest of the RAG flow changes.

This file only *queries* Pinecone. Run ingest_kb.py first (and again any
time data/kb/ changes) to actually put vectors there.
"""

import os
from typing import List

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pinecone import Pinecone

from kb import KBDoc

load_dotenv()

EMBEDDING_MODEL = os.environ.get("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
# gemini-embedding-001 defaults to 3072 dimensions; 768 is plenty for a KB
# this size and keeps vectors smaller/cheaper to store and query.
EMBEDDING_DIMENSIONS = 768
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "supportpilot-kb")

_genai_client = None
_pinecone_index = None


def get_genai_client() -> genai.Client:
    """Create (once) and return the Gemini client used for embeddings."""
    global _genai_client
    if _genai_client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise SystemExit(
                "Missing GEMINI_API_KEY.\n"
                "Copy .env.example to .env and paste your key in there."
            )
        _genai_client = genai.Client(api_key=api_key)
    return _genai_client


def get_pinecone_index():
    """Connect to the Pinecone index.

    Does NOT create the index — that only happens in ingest_kb.py, since
    the chat app should only ever read from Pinecone, never write to it.
    """
    global _pinecone_index
    if _pinecone_index is None:
        api_key = os.environ.get("PINECONE_API_KEY")
        if not api_key:
            raise SystemExit(
                "Missing PINECONE_API_KEY.\n"
                "Get a free key at https://app.pinecone.io, add it to "
                ".env, then run `uv run python ingest_kb.py`."
            )
        pc = Pinecone(api_key=api_key)
        existing = [idx.name for idx in pc.list_indexes()]
        if PINECONE_INDEX_NAME not in existing:
            raise SystemExit(
                f"Pinecone index '{PINECONE_INDEX_NAME}' doesn't exist yet.\n"
                "Run `uv run python ingest_kb.py` first — it creates the "
                "index and loads the KB into it."
            )
        _pinecone_index = pc.Index(PINECONE_INDEX_NAME)
    return _pinecone_index


def embed_text(text: str, task_type: str) -> List[float]:
    """Embed one piece of text with Gemini.

    One text per call — gemini-embedding-001 doesn't support batching
    multiple inputs into a single request.

    task_type matters for retrieval quality: use "RETRIEVAL_DOCUMENT" when
    embedding KB articles (ingest_kb.py) and "RETRIEVAL_QUERY" when
    embedding a user's question (search_kb() below) — Gemini's embedding
    model is tuned differently for each side of a retrieval pair.
    """
    client = get_genai_client()
    result = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=EMBEDDING_DIMENSIONS,
        ),
    )
    return result.embeddings[0].values


def doc_to_metadata(doc: KBDoc) -> dict:
    """Pure: build the Pinecone metadata dict stored alongside one KB
    doc's vector. Used by ingest_kb.py. Separated out so it's testable
    without touching Gemini or Pinecone.
    """
    return {"doc_id": doc.doc_id, "title": doc.title, "text": doc.text}


def metadata_to_doc(metadata: dict) -> KBDoc:
    """Pure: reconstruct a KBDoc from a Pinecone match's metadata — the
    inverse of doc_to_metadata(). Also independently testable.
    """
    return KBDoc(
        doc_id=metadata["doc_id"],
        title=metadata["title"],
        text=metadata["text"],
    )


# Pinecone's query() always returns up to top_k matches, no matter how
# irrelevant they are -- unlike Phase 5's keyword search, which returned
# nothing for zero word overlap. Without a floor, a query with no real
# KB coverage (e.g. a bare customer id like "CUST-002") would still come
# back with "closest available" docs that aren't actually relevant,
# which then wrongly trips the citation guardrail (see PHASE_PLAN.md's
# Phase 10 debugging notes for how this surfaced in practice).
#
# 0.5 is a rough starting heuristic, not empirically tuned against real
# traffic -- cosine similarity scores depend on the embedding model, and
# what counts as "relevant enough" here is worth revisiting once this is
# running against real questions.
MIN_RELEVANCE_SCORE = 0.5


def search_kb(query: str, top_k: int = 2) -> List[KBDoc]:
    """Phase 6 replacement for kb.search_kb(): embeds the query, asks
    Pinecone for the most semantically similar KB doc vectors, and
    reconstructs KBDoc objects from the metadata stored at ingest time.

    Matches below MIN_RELEVANCE_SCORE are dropped — an irrelevant query
    should come back with nothing, the same as Phase 5's keyword search
    did for zero overlap, not with Pinecone's "closest available" guess.
    """
    index = get_pinecone_index()
    query_vector = embed_text(query, task_type="RETRIEVAL_QUERY")

    results = index.query(
        vector=query_vector,
        top_k=top_k,
        include_metadata=True,
    )

    relevant_matches = [m for m in results.matches if m.score >= MIN_RELEVANCE_SCORE]
    return [metadata_to_doc(match.metadata) for match in relevant_matches]
