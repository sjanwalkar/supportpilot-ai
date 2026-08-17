"""
SupportPilot AI — Phase 6: KB ingestion script

Embeds every article in data/kb/ with Gemini and upserts it into Pinecone.

Run this once, and again any time you add or edit a file in data/kb/:

    uv run python ingest_kb.py

This is a standalone script, not part of the request path — chat.py and
api.py only ever *query* Pinecone via vector_search.search_kb(); they
never write to it. Ingestion is a separate, deliberate step.
"""

import os

from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec

from kb import load_kb
from vector_search import EMBEDDING_DIMENSIONS, PINECONE_INDEX_NAME, doc_to_metadata, embed_text

load_dotenv()


def get_or_create_index(pc: Pinecone):
    existing = [idx.name for idx in pc.list_indexes()]
    if PINECONE_INDEX_NAME not in existing:
        print(f"Creating Pinecone index '{PINECONE_INDEX_NAME}' ({EMBEDDING_DIMENSIONS} dims)...")
        pc.create_index(
            name=PINECONE_INDEX_NAME,
            dimension=EMBEDDING_DIMENSIONS,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
    return pc.Index(PINECONE_INDEX_NAME)


def main():
    api_key = os.environ.get("PINECONE_API_KEY")
    if not api_key:
        raise SystemExit(
            "Missing PINECONE_API_KEY.\n"
            "Get a free key at https://app.pinecone.io and add it to .env."
        )

    pc = Pinecone(api_key=api_key)
    index = get_or_create_index(pc)

    docs = load_kb()
    if not docs:
        raise SystemExit("No KB articles found in data/kb/ — nothing to ingest.")

    print(f"Embedding and upserting {len(docs)} KB articles...")
    vectors = []
    for doc in docs:
        values = embed_text(doc.text, task_type="RETRIEVAL_DOCUMENT")
        vectors.append({
            "id": doc.doc_id,
            "values": values,
            "metadata": doc_to_metadata(doc),
        })
        print(f"  embedded: {doc.doc_id}")

    index.upsert(vectors=vectors)
    print(f"Done. {len(vectors)} vectors upserted into '{PINECONE_INDEX_NAME}'.")


if __name__ == "__main__":
    main()
