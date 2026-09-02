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
import json
import math
import os
from google import genai

# ── Persistent Memory ────────────────────────────────────────────────────────

def generate_embedding(text: str) -> list[float]:
    """Generate embedding using Gemini API."""
    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    resp = client.models.embed_content(
        model="text-embedding-004", 
        contents=text
    )
    return resp.embeddings[0].values

def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = sum(a * a for a in v1) ** 0.5
    norm2 = sum(b * b for b in v2) ** 0.5
    if norm1 == 0 or norm2 == 0: return 0
    return dot / (norm1 * norm2)


def upsert_memory(
    conn,
    user_id: str,
    key: str,
    value: str,
    category: str,
    confidence: float = 1.0,
    embedding: list[float] | None = None,
) -> None:
    """
    Insert or update a memory fact (upsert on user_id + key).

    This is the WRITE PATH for memory — called from the extract_memory step
    when the LLM identifies a fact worth persisting.
    """
    emb_str = json.dumps(embedding) if embedding else None
    conn.execute(
        """
        INSERT INTO memory (user_id, key, value, category, confidence, embedding, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(user_id, key) DO UPDATE SET
            value = excluded.value,
            category = excluded.category,
            confidence = excluded.confidence,
            embedding = excluded.embedding,
            updated_at = datetime('now')
        """,
        (user_id, key, value, category, confidence, emb_str),
    )
    conn.commit()


def get_all_memory(conn, user_id: str) -> list[dict]:
    """Retrieve all memory entries for a user."""
    rows = conn.execute(
        "SELECT key, value, category, confidence FROM memory WHERE user_id = ? ORDER BY category, key",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_relevant_memories(conn, user_id: str, user_query: str, top_k: int = 5, threshold: float = 0.5) -> list[dict]:
    """
    Semantic search for memories. Replaces exact category matching.
    """
    try:
        query_emb = generate_embedding(user_query)
    except Exception:
        return []

    rows = conn.execute(
        "SELECT key, value, category, embedding FROM memory WHERE user_id = ? AND embedding IS NOT NULL",
        (user_id,)
    ).fetchall()

    scored = []
    for r in rows:
        emb = json.loads(r["embedding"])
        sim = cosine_similarity(query_emb, emb)
        if sim >= threshold:
            scored.append((sim, dict(r)))
            
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored[:top_k]]

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
