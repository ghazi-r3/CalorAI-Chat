"""
Meal CRUD operations.

All queries filter by is_deleted = 0 to support soft-delete. Daily totals
are computed via SUM queries — no separate table to keep in sync.
"""

import json
from datetime import date, datetime


def create_meal(
    conn,
    user_id: str,
    description: str,
    items: list[dict],
    calories: float,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    fiber_g: float = 0,
    meal_type: str | None = None,
    source: str = "text",
    raw_input: str | None = None,
    image_path: str | None = None,
) -> int:
    """Insert a new meal and return its ID."""
    cursor = conn.execute(
        """
        INSERT INTO meals (
            user_id, meal_type, description, items,
            calories, protein_g, carbs_g, fat_g, fiber_g,
            source, raw_input, image_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id, meal_type, description, json.dumps(items),
            calories, protein_g, carbs_g, fat_g, fiber_g,
            source, raw_input, image_path,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def update_meal(conn, meal_id: int, **fields) -> bool:
    """
    Update specific fields on an existing meal.

    Only non-None values in `fields` are applied. This is the path used for
    corrections like "actually that was 3 rotis not 2" — it mutates in place
    rather than delete-and-reinsert, so daily totals stay correct automatically.
    """
    allowed = {
        "description", "items", "calories", "protein_g", "carbs_g",
        "fat_g", "fiber_g", "meal_type",
    }
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return False

    # Serialize items list if present
    if "items" in updates and isinstance(updates["items"], list):
        updates["items"] = json.dumps(updates["items"])

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [meal_id]

    conn.execute(
        f"UPDATE meals SET {set_clause}, updated_at = datetime('now') WHERE id = ? AND is_deleted = 0",
        values,
    )
    conn.commit()
    return conn.total_changes > 0


def delete_meal(conn, meal_id: int) -> bool:
    """Soft-delete a meal by setting is_deleted = 1."""
    conn.execute(
        "UPDATE meals SET is_deleted = 1, updated_at = datetime('now') WHERE id = ?",
        (meal_id,),
    )
    conn.commit()
    return conn.total_changes > 0


def get_meal_by_id(conn, meal_id: int) -> dict | None:
    """Retrieve a single meal by ID (only if not deleted)."""
    row = conn.execute(
        "SELECT * FROM meals WHERE id = ? AND is_deleted = 0",
        (meal_id,),
    ).fetchone()
    return dict(row) if row else None


def get_meals(
    conn,
    user_id: str,
    target_date: str | None = None,
    last_n: int | None = None,
    meal_type: str | None = None,
) -> list[dict]:
    """
    Retrieve meals with optional filters.

    Args:
        target_date: ISO date string (e.g. "2024-03-15"). Defaults to today.
        last_n: Return the N most recent meals (ignores date filter).
        meal_type: Filter by meal type ("breakfast", "lunch", etc.).
    """
    query = "SELECT * FROM meals WHERE user_id = ? AND is_deleted = 0"
    params: list = [user_id]

    if last_n:
        # Last N meals regardless of date
        if meal_type:
            query += " AND meal_type = ?"
            params.append(meal_type)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(last_n)
    else:
        # Filter by date (default: today)
        if target_date is None:
            target_date = date.today().isoformat()
        query += " AND date(timestamp) = ?"
        params.append(target_date)
        if meal_type:
            query += " AND meal_type = ?"
            params.append(meal_type)
        query += " ORDER BY timestamp ASC"

    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_daily_totals(
    conn,
    user_id: str,
    target_date: str | None = None,
) -> dict:
    """
    Compute daily nutrition totals via SUM query.

    This is the single source of truth for totals — no materialized table.
    Corrections via update_meal are automatically reflected because we always
    re-aggregate from the meals table.
    """
    if target_date is None:
        target_date = date.today().isoformat()

    row = conn.execute(
        """
        SELECT
            COALESCE(SUM(calories), 0)  AS total_calories,
            COALESCE(SUM(protein_g), 0) AS total_protein_g,
            COALESCE(SUM(carbs_g), 0)   AS total_carbs_g,
            COALESCE(SUM(fat_g), 0)     AS total_fat_g,
            COALESCE(SUM(fiber_g), 0)   AS total_fiber_g,
            COUNT(*)                     AS meal_count
        FROM meals
        WHERE user_id = ? AND date(timestamp) = ? AND is_deleted = 0
        """,
        (user_id, target_date),
    ).fetchone()

    return {
        "date": target_date,
        "total_calories": round(row["total_calories"], 1),
        "total_protein_g": round(row["total_protein_g"], 1),
        "total_carbs_g": round(row["total_carbs_g"], 1),
        "total_fat_g": round(row["total_fat_g"], 1),
        "total_fiber_g": round(row["total_fiber_g"], 1),
        "meal_count": row["meal_count"],
    }
