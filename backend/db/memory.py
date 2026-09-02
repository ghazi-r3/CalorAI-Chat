"""
Persistent memory and conversation history operations.

Memory is NOT conversation history (the PDF is explicit about this).
Memory stores facts worth remembering across sessions:
  - preferences:  "vegetarian", "lactose intolerant"
  - shortcuts:    "my usual" = "2 parathas and chai"
  - targets:      "140g protein target"
  - personal:     "brother often shares meals"

Conversation history is stored separately for multi-turn context
within a session, but is never called "memory."
"""

from datetime import datetime


# ── Persistent Memory ────────────────────────────────────────────────────────

def upsert_memory(
    conn,
    user_id: str,
    key: str,
    value: str,
    category: str,
    confidence: float = 1.0,
) -> None:
    """
    Insert or update a memory fact (upsert on user_id + key).

    This is the WRITE PATH for memory — called from the extract_memory step
    when the LLM identifies a fact worth persisting.
    """
    conn.execute(
        """
        INSERT INTO memory (user_id, key, value, category, confidence, updated_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(user_id, key) DO UPDATE SET
            value = excluded.value,
            category = excluded.category,
            confidence = excluded.confidence,
            updated_at = datetime('now')
        """,
        (user_id, key, value, category, confidence),
    )
    conn.commit()


def get_all_memory(conn, user_id: str) -> list[dict]:
    """Retrieve all memory entries for a user."""
    rows = conn.execute(
        "SELECT key, value, category, confidence FROM memory WHERE user_id = ? ORDER BY category, key",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_memory_by_category(
    conn,
    user_id: str,
    categories: list[str],
) -> list[dict]:
    """
    Retrieve memory entries filtered by category.

    This is the RETRIEVE PATH for memory — called from load_context to
    selectively pull relevant memory into the agent's context.

    Always-load categories: "preference", "target"
    Conditionally-loaded:   "shortcut" (when user references "my usual" etc.)
    """
    placeholders = ",".join("?" for _ in categories)
    rows = conn.execute(
        f"SELECT key, value, category, confidence FROM memory WHERE user_id = ? AND category IN ({placeholders}) ORDER BY category, key",
        [user_id] + categories,
    ).fetchall()
    return [dict(r) for r in rows]


def get_memory_by_key(conn, user_id: str, key: str) -> dict | None:
    """Retrieve a specific memory entry by key."""
    row = conn.execute(
        "SELECT key, value, category, confidence FROM memory WHERE user_id = ? AND key = ?",
        (user_id, key),
    ).fetchone()
    return dict(row) if row else None


def delete_memory(conn, user_id: str, key: str) -> bool:
    """Delete a memory entry."""
    conn.execute(
        "DELETE FROM memory WHERE user_id = ? AND key = ?",
        (user_id, key),
    )
    conn.commit()
    return conn.total_changes > 0


# ── Conversation History ─────────────────────────────────────────────────────

def save_message(
    conn,
    user_id: str,
    session_id: str,
    role: str,
    content: str,
) -> None:
    """Save a single conversation message."""
    conn.execute(
        "INSERT INTO conversations (user_id, session_id, role, content) VALUES (?, ?, ?, ?)",
        (user_id, session_id, role, content),
    )
    conn.commit()


def get_conversation_history(
    conn,
    user_id: str,
    session_id: str,
    limit: int = 20,
) -> list[dict]:
    """
    Retrieve the most recent conversation messages for a session.

    Returns messages in chronological order (oldest first).
    """
    rows = conn.execute(
        """
        SELECT role, content, timestamp FROM conversations
        WHERE user_id = ? AND session_id = ?
        ORDER BY id DESC LIMIT ?
        """,
        (user_id, session_id, limit),
    ).fetchall()
    # Reverse to get chronological order (we fetched DESC for LIMIT)
    return [dict(r) for r in reversed(rows)]
