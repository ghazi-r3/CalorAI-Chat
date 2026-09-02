"""
Tests for agent tools — verifies tool CRUD operations work correctly.

Focuses on the three critical cases from the PDF:
  1. Corrections don't double-count (update_meal, not create new)
  2. Daily totals stay correct through edits
  3. Memory persistence across operations
"""

import json
import os
import pytest
import sys

# Use test database
os.environ["CALORAI_DB_PATH"] = "test_calorai.db"

from backend.db.database import init_db, get_db
from backend.db.meals import (
    create_meal, update_meal, delete_meal,
    get_meal_by_id, get_meals, get_daily_totals,
)
from backend.db.memory import (
    upsert_memory, get_all_memory, get_memory_by_category,
    get_memory_by_key, delete_memory, save_message, get_conversation_history,
)


@pytest.fixture(autouse=True)
def setup_db():
    """Create a fresh test database for each test."""
    init_db("test_calorai.db")
    yield
    # Clean up
    try:
        os.remove("test_calorai.db")
    except OSError:
        pass


USER_ID = "test_user"


class TestMealCRUD:
    """Test basic meal create, read, update, delete."""

    def test_create_meal(self):
        with get_db("test_calorai.db") as conn:
            meal_id = create_meal(
                conn, USER_ID,
                description="2 parathas and chai",
                items=[{"name": "paratha", "quantity": 2}, {"name": "chai", "quantity": 1}],
                calories=640, protein_g=13, carbs_g=75, fat_g=33,
                meal_type="breakfast", source="text",
            )
            assert meal_id > 0

            meal = get_meal_by_id(conn, meal_id)
            assert meal is not None
            assert meal["description"] == "2 parathas and chai"
            assert meal["calories"] == 640

    def test_get_daily_totals(self):
        with get_db("test_calorai.db") as conn:
            create_meal(
                conn, USER_ID,
                description="breakfast",
                items=[], calories=500, protein_g=20,
                carbs_g=60, fat_g=15,
            )
            create_meal(
                conn, USER_ID,
                description="lunch",
                items=[], calories=700, protein_g=30,
                carbs_g=80, fat_g=25,
            )

            totals = get_daily_totals(conn, USER_ID)
            assert totals["total_calories"] == 1200
            assert totals["total_protein_g"] == 50
            assert totals["meal_count"] == 2

    def test_soft_delete_updates_totals(self):
        with get_db("test_calorai.db") as conn:
            id1 = create_meal(
                conn, USER_ID,
                description="meal 1",
                items=[], calories=500, protein_g=20,
                carbs_g=60, fat_g=15,
            )
            create_meal(
                conn, USER_ID,
                description="meal 2",
                items=[], calories=300, protein_g=10,
                carbs_g=30, fat_g=10,
            )

            # Delete first meal
            delete_meal(conn, id1)

            totals = get_daily_totals(conn, USER_ID)
            assert totals["total_calories"] == 300
            assert totals["meal_count"] == 1


class TestCorrectionNoDoubleCount:
    """
    THE CRITICAL TEST: "actually that was 3 rotis not 2"

    This test proves that corrections via update_meal do NOT double-count.
    The daily total must reflect the UPDATED value, not original + updated.
    """

    def test_correction_updates_not_doubles(self):
        """
        Scenario:
          1. Log "2 rotis" (200 cal)
          2. Correct to "3 rotis" (300 cal)
          3. Daily total should be 300, not 500
        """
        with get_db("test_calorai.db") as conn:
            # Step 1: Log 2 rotis
            meal_id = create_meal(
                conn, USER_ID,
                description="2 rotis",
                items=[{"name": "roti", "quantity": 2}],
                calories=200, protein_g=6, carbs_g=36, fat_g=4,
                meal_type="dinner",
            )

            totals_before = get_daily_totals(conn, USER_ID)
            assert totals_before["total_calories"] == 200

            # Step 2: Correct to 3 rotis (in-place update)
            update_meal(
                conn, meal_id,
                description="3 rotis",
                items=[{"name": "roti", "quantity": 3}],
                calories=300, protein_g=9, carbs_g=54, fat_g=6,
            )

            # Step 3: Verify totals — should be 300, NOT 500
            totals_after = get_daily_totals(conn, USER_ID)
            assert totals_after["total_calories"] == 300, (
                f"DOUBLE-COUNT BUG: Expected 300 cal after correction, "
                f"got {totals_after['total_calories']}"
            )
            assert totals_after["total_protein_g"] == 9
            assert totals_after["meal_count"] == 1

    def test_correction_with_multiple_meals(self):
        """
        Ensure correction only affects the targeted meal,
        not other meals logged the same day.
        """
        with get_db("test_calorai.db") as conn:
            # Log breakfast
            create_meal(
                conn, USER_ID,
                description="breakfast - oatmeal",
                items=[], calories=150, protein_g=5,
                carbs_g=27, fat_g=3,
            )

            # Log dinner with 2 rotis
            dinner_id = create_meal(
                conn, USER_ID,
                description="2 rotis and dal",
                items=[], calories=560, protein_g=18,
                carbs_g=66, fat_g=5,
            )

            totals_before = get_daily_totals(conn, USER_ID)
            assert totals_before["total_calories"] == 710  # 150 + 560

            # Correct dinner to 3 rotis
            update_meal(
                conn, dinner_id,
                description="3 rotis and dal",
                calories=660, protein_g=21,
                carbs_g=84, fat_g=7,
            )

            totals_after = get_daily_totals(conn, USER_ID)
            assert totals_after["total_calories"] == 810  # 150 + 660
            assert totals_after["meal_count"] == 2


class TestMemoryPersistence:
    """Test that memory survives across connections (simulating sessions)."""

    def test_upsert_and_retrieve(self):
        # Session 1: store a preference
        with get_db("test_calorai.db") as conn:
            upsert_memory(conn, USER_ID, "dietary_restriction", "vegetarian", "preference")

        # Session 2: retrieve it (new connection)
        with get_db("test_calorai.db") as conn:
            memories = get_all_memory(conn, USER_ID)
            assert len(memories) == 1
            assert memories[0]["key"] == "dietary_restriction"
            assert memories[0]["value"] == "vegetarian"

    def test_upsert_overwrites(self):
        with get_db("test_calorai.db") as conn:
            upsert_memory(conn, USER_ID, "protein_target", "120g", "target")
            upsert_memory(conn, USER_ID, "protein_target", "140g", "target")

            mem = get_memory_by_key(conn, USER_ID, "protein_target")
            assert mem["value"] == "140g"  # Updated, not duplicated

            all_mem = get_all_memory(conn, USER_ID)
            assert len(all_mem) == 1  # Only one entry

    def test_category_filtering(self):
        with get_db("test_calorai.db") as conn:
            upsert_memory(conn, USER_ID, "diet", "vegetarian", "preference")
            upsert_memory(conn, USER_ID, "usual_breakfast", "2 parathas and chai", "shortcut")
            upsert_memory(conn, USER_ID, "protein_target", "140g", "target")

            # Load only preferences and targets (the "always-load" categories)
            prefs = get_memory_by_category(conn, USER_ID, ["preference", "target"])
            assert len(prefs) == 2
            keys = {m["key"] for m in prefs}
            assert "diet" in keys
            assert "protein_target" in keys
            assert "usual_breakfast" not in keys

    def test_delete_memory(self):
        with get_db("test_calorai.db") as conn:
            upsert_memory(conn, USER_ID, "old_fact", "outdated", "personal")
            assert delete_memory(conn, USER_ID, "old_fact")
            assert get_memory_by_key(conn, USER_ID, "old_fact") is None


class TestConversationHistory:
    """Test conversation history storage and retrieval."""

    def test_save_and_retrieve(self):
        with get_db("test_calorai.db") as conn:
            save_message(conn, USER_ID, "session1", "user", "had 2 parathas")
            save_message(conn, USER_ID, "session1", "assistant", "Got it!")
            save_message(conn, USER_ID, "session1", "user", "and chai")

            history = get_conversation_history(conn, USER_ID, "session1")
            assert len(history) == 3
            assert history[0]["role"] == "user"
            assert history[0]["content"] == "had 2 parathas"

    def test_session_isolation(self):
        with get_db("test_calorai.db") as conn:
            save_message(conn, USER_ID, "session1", "user", "msg in session 1")
            save_message(conn, USER_ID, "session2", "user", "msg in session 2")

            h1 = get_conversation_history(conn, USER_ID, "session1")
            h2 = get_conversation_history(conn, USER_ID, "session2")
            assert len(h1) == 1
            assert len(h2) == 1
            assert h1[0]["content"] == "msg in session 1"


class TestNutritionLookup:
    """Test the hardcoded nutrition database."""

    def test_known_food(self):
        from backend.models.nutrition import lookup_nutrition
        result = lookup_nutrition("paratha", quantity=2)
        assert result is not None
        assert result.calories == 520  # 260 * 2
        assert result.source == "hardcoded"

    def test_unknown_food(self):
        from backend.models.nutrition import lookup_nutrition
        result = lookup_nutrition("dragon fruit smoothie")
        assert result is None  # Agent should estimate

    def test_alias_resolution(self):
        from backend.models.nutrition import lookup_nutrition
        result = lookup_nutrition("parathas")
        assert result is not None
        assert result.food_item == "parathas"

    def test_quantity_scaling(self):
        from backend.models.nutrition import lookup_nutrition
        one = lookup_nutrition("roti", quantity=1)
        three = lookup_nutrition("roti", quantity=3)
        assert three.calories == one.calories * 3
