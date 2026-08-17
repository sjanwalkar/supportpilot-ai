"""
SupportPilot AI — Phase 5: Local Knowledge Base (RAG v1)

Goal: ground answers in real KB content, without a vector database yet.

Flow this phase adds, ahead of the Phase 2 state machine:

    message -> search_kb(message) -> top matching KB docs
             -> build_prompt(message, docs) -> ... (same as before)

Retrieval here is deliberately simple: split text into words, count how
many words overlap between the question and each doc, rank by that count.
No embeddings, no external services. Phase 6 swaps this out for Pinecone
vector search — the *shape* of retrieve -> stuff into prompt -> cite stays
the same from here on, only search_kb()'s internals change.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

KB_DIR = Path(__file__).parent / "data" / "kb"

# Common words that would otherwise dominate every overlap score without
# telling us anything about topic — filtered out before scoring.
STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "i", "you", "he", "she", "it", "we", "they", "my", "your", "his",
    "her", "its", "our", "their", "this", "that", "these", "those",
    "to", "of", "in", "on", "for", "with", "at", "by", "from", "and",
    "or", "but", "not", "do", "does", "did", "can", "could", "will",
    "would", "should", "how", "what", "when", "where", "why", "who",
    "have", "has", "had", "if", "so", "as", "about", "me", "us", "get",
}


@dataclass
class KBDoc:
    """One loaded knowledge-base article."""
    doc_id: str    # filename without extension — used as the citation key
    title: str     # first '# ' heading in the file
    text: str      # full markdown content


def _tokenize(text: str) -> List[str]:
    """Lowercase word list, punctuation stripped, stopwords/short words removed."""
    words = re.findall(r"[a-zA-Z']+", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


def load_kb() -> List[KBDoc]:
    """Read every .md file in data/kb/ into a KBDoc.

    No caching on purpose — keeps this simple and means editing a KB file
    takes effect on the next request, no restart needed.
    """
    docs = []
    for path in sorted(KB_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        first_line = text.strip().splitlines()[0] if text.strip() else path.stem
        title = first_line.lstrip("#").strip()
        docs.append(KBDoc(doc_id=path.stem, title=title, text=text))
    return docs


def search_kb(query: str, top_k: int = 2) -> List[KBDoc]:
    """Return up to top_k KB docs whose words overlap the query the most.

    Pure keyword overlap — no embeddings, no network call. A doc only
    comes back if it scores above zero, so an unrelated question (or one
    with no KB coverage) correctly returns an empty list.
    """
    query_words = set(_tokenize(query))
    if not query_words:
        return []

    scored = []
    for doc in load_kb():
        doc_words = _tokenize(doc.text)
        score = sum(1 for w in doc_words if w in query_words)
        if score > 0:
            scored.append((score, doc))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [doc for _, doc in scored[:top_k]]
