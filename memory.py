"""
SupportPilot AI — Phase 7: Memory (SQLite)

Goal: support follow-up questions, without complex summarization.

Adds two tables to a local SQLite file:

    conversations(id, created_at)
    messages(id, conversation_id, role, content, created_at)

Flow this phase adds around the Phase 6 flow:

    conversation_id -> get_recent_messages() -> history
    message -> search_kb -> ... -> response
    -> add_message() saves both the question and the answer

Memory here is deliberately simple: the last few messages, verbatim, no
summarization. That's enough for short follow-ups ("what about a refund
instead?") and stays easy to reason about — the acceptance bar for this
phase is "short and understandable," not "remembers everything forever."
"""

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List

DB_PATH = Path(__file__).parent / "data" / "supportpilot.db"

# How many past messages (user + assistant combined) get pulled into the
# prompt for a follow-up question.
HISTORY_LIMIT = 8


@dataclass
class Message:
    role: str      # "user" or "assistant"
    content: str


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    """Create the conversations/messages tables if they don't exist yet.
    Cheap and idempotent — safe to call on every app start.
    """
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            )
            """
        )


def create_conversation() -> str:
    """Start a new conversation and return its id."""
    conversation_id = str(uuid.uuid4())
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO conversations (id, created_at) VALUES (?, ?)",
            (conversation_id, datetime.now(timezone.utc).isoformat()),
        )
    return conversation_id


def add_message(conversation_id: str, role: str, content: str) -> None:
    """Append one message to a conversation's history."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content, created_at) "
            "VALUES (?, ?, ?, ?)",
            (conversation_id, role, content, datetime.now(timezone.utc).isoformat()),
        )


def get_recent_messages(conversation_id: str, limit: int = HISTORY_LIMIT) -> List[Message]:
    """Return the last `limit` messages for a conversation, oldest first.

    Called before the current turn's messages are saved, so this never
    includes the question currently being answered — only what came
    before it.
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages "
            "WHERE conversation_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (conversation_id, limit),
        ).fetchall()
    return [Message(role=role, content=content) for role, content in reversed(rows)]
