"""
Agent tools — the callable actions available to the LangGraph agent.

Design decision on tool boundaries (explicitly evaluated):
  - log_meal:         CREATE — new meal only
  - update_meal:      UPDATE — mutate existing meal (corrections)
  - delete_meal:      DELETE — soft-delete
  - get_meals:        READ — raw meal data
  - get_daily_totals: READ — aggregated totals
  - lookup_nutrition: READ — nutrition data lookup
  - get_user_memory:  READ — persistent facts
  - set_user_memory:  WRITE — store persistent facts

No overlap: each tool has exactly one responsibility. The agent decides
which tool to use based on the user's intent.
"""

import json
from datetime import date, timedelta
from langchain_core.tools import tool

from backend.db.database import get_db
from backend.db.meals import (
    create_meal,
    update_meal as db_update_meal,
    delete_meal as db_delete_meal,
    get_meal_by_id,
    get_meals as db_get_meals,
    get_daily_totals as db_get_daily_totals,
)
from backend.db.memory import (
    upsert_memory,
    get_all_memory,
    get_memory_by_category,
)
from backend.models.nutrition import lookup_nutrition as db_lookup_nutrition

# Single user for now. Session isolation is a bonus feature; this would be
# replaced by config-based injection (via LangGraph RunnableConfig) for
# multi-user support.
DEFAULT_USER_ID = "default"


@tool
def log_meal(
    description: str,
    calories: float,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    items: str = "[]",
    meal_type: str = "other",
    source: str = "text",
    fiber_g: float = 0,
) -> str:
    """Log a new meal to the database. Use when the user reports eating something.

    Args:
        description: Human-readable summary (e.g., "2 parathas and chai for breakfast")
        calories: Estimated total calories for the entire meal
        protein_g: Total protein in grams
        carbs_g: Total carbs in grams
        fat_g: Total fat in grams
        items: JSON array of food items, e.g., '[{"name": "paratha", "quantity": 2, "unit": "piece"}, {"name": "chai", "quantity": 1, "unit": "cup"}]'
        meal_type: One of "breakfast", "lunch", "dinner", "snack", or "other"
        source: How the meal was reported - "text", "image", or "image+text"
        fiber_g: Total fiber in grams (optional)

    Returns:
        Confirmation with meal ID and nutrition summary
    """
    try:
        parsed_items = json.loads(items) if isinstance(items, str) else items
    except json.JSONDecodeError:
        parsed_items = []

    with get_db() as conn:
        meal_id = create_meal(
            conn,
            user_id=DEFAULT_USER_ID,
            description=description,
            items=parsed_items,
            calories=calories,
            protein_g=protein_g,
            carbs_g=carbs_g,
            fat_g=fat_g,
            fiber_g=fiber_g,
            meal_type=meal_type,
            source=source,
            raw_input=None,
        )

        # Get updated daily totals
        totals = db_get_daily_totals(conn, DEFAULT_USER_ID)

    return (
        f"✅ Meal logged (ID: {meal_id}): {description}\n"
        f"   Calories: {calories:.0f} kcal | Protein: {protein_g:.0f}g | "
        f"Carbs: {carbs_g:.0f}g | Fat: {fat_g:.0f}g\n"
        f"📊 Today's totals: {totals['total_calories']:.0f} kcal | "
        f"P: {totals['total_protein_g']:.0f}g | C: {totals['total_carbs_g']:.0f}g | "
        f"F: {totals['total_fat_g']:.0f}g ({totals['meal_count']} meals)"
    )


@tool
def update_meal(
    meal_id: int,
    description: str = "",
    calories: float = -1,
    protein_g: float = -1,
    carbs_g: float = -1,
    fat_g: float = -1,
    items: str = "",
    fiber_g: float = -1,
) -> str:
    """Update an existing meal for corrections. Use when the user says things like "actually that was 3 rotis not 2".

    IMPORTANT: Use get_meals first to find the meal_id of the meal to update.
    Only provide the fields that need to change — unchanged fields should be left at their defaults.

    Args:
        meal_id: The ID of the meal to update (get this from get_meals)
        description: Updated description (leave empty to keep current)
        calories: Updated calories (-1 to keep current)
        protein_g: Updated protein (-1 to keep current)
        carbs_g: Updated carbs (-1 to keep current)
        fat_g: Updated fat (-1 to keep current)
        items: Updated items JSON array (leave empty to keep current)
        fiber_g: Updated fiber (-1 to keep current)

    Returns:
        Confirmation with updated values and new daily totals
    """
    fields = {}
    if description:
        fields["description"] = description
    if calories >= 0:
        fields["calories"] = calories
    if protein_g >= 0:
        fields["protein_g"] = protein_g
    if carbs_g >= 0:
        fields["carbs_g"] = carbs_g
    if fat_g >= 0:
        fields["fat_g"] = fat_g
    if fiber_g >= 0:
        fields["fiber_g"] = fiber_g
    if items:
        try:
            fields["items"] = json.loads(items) if isinstance(items, str) else items
        except json.JSONDecodeError:
            pass

    if not fields:
        return "❌ No fields provided to update."

    with get_db() as conn:
        # Check meal exists
        meal = get_meal_by_id(conn, meal_id)
        if not meal:
            return f"❌ Meal with ID {meal_id} not found."

        success = db_update_meal(conn, meal_id, **fields)
        if not success:
            return f"❌ Failed to update meal {meal_id}."

        # Get the updated meal
        updated = get_meal_by_id(conn, meal_id)
        totals = db_get_daily_totals(conn, DEFAULT_USER_ID)

    return (
        f"✏️ Meal {meal_id} updated: {updated['description']}\n"
        f"   Calories: {updated['calories']:.0f} kcal | Protein: {updated['protein_g']:.0f}g | "
        f"Carbs: {updated['carbs_g']:.0f}g | Fat: {updated['fat_g']:.0f}g\n"
        f"📊 Updated daily totals: {totals['total_calories']:.0f} kcal | "
        f"P: {totals['total_protein_g']:.0f}g | C: {totals['total_carbs_g']:.0f}g | "
        f"F: {totals['total_fat_g']:.0f}g ({totals['meal_count']} meals)"
    )


@tool
def delete_meal(meal_id: int) -> str:
    """Delete a logged meal (soft-delete). Use when the user wants to remove a meal entry.

    Args:
        meal_id: The ID of the meal to delete (get this from get_meals)

    Returns:
        Confirmation of deletion with updated daily totals
    """
    with get_db() as conn:
        meal = get_meal_by_id(conn, meal_id)
        if not meal:
            return f"❌ Meal with ID {meal_id} not found."

        db_delete_meal(conn, meal_id)
        totals = db_get_daily_totals(conn, DEFAULT_USER_ID)

    return (
        f"🗑️ Deleted: {meal['description']}\n"
        f"📊 Updated daily totals: {totals['total_calories']:.0f} kcal | "
        f"P: {totals['total_protein_g']:.0f}g | C: {totals['total_carbs_g']:.0f}g | "
        f"F: {totals['total_fat_g']:.0f}g ({totals['meal_count']} meals)"
    )


@tool
def get_meals(
    date: str = "",
    last_n: int = 0,
    meal_type: str = "",
) -> str:
    """Retrieve past meals from the database. Use to find meals for corrections, look up "what I ate yesterday", or resolve "same as yesterday".

    Args:
        date: Date to look up in YYYY-MM-DD format. Defaults to today. Use "yesterday" for yesterday.
        last_n: Get the N most recent meals regardless of date. Set to 0 to use date filter.
        meal_type: Filter by type: "breakfast", "lunch", "dinner", "snack" (optional)

    Returns:
        List of meals with IDs, descriptions, and nutrition data
    """
    # Handle "yesterday" shorthand
    target_date = None
    if date.lower() == "yesterday":
        target_date = (date_module.today() - timedelta(days=1)).isoformat()
    elif date:
        target_date = date

    with get_db() as conn:
        meals = db_get_meals(
            conn,
            DEFAULT_USER_ID,
            target_date=target_date,
            last_n=last_n if last_n > 0 else None,
            meal_type=meal_type or None,
        )

    if not meals:
        period = f"on {target_date}" if target_date else "today"
        return f"No meals found {period}."

    lines = []
    for m in meals:
        lines.append(
            f"  ID {m['id']}: {m['description']} "
            f"({m['calories']:.0f} kcal | P: {m['protein_g']:.0f}g | "
            f"C: {m['carbs_g']:.0f}g | F: {m['fat_g']:.0f}g) "
            f"[{m['timestamp']}]"
        )

    header = f"Found {len(meals)} meal(s):"
    return header + "\n" + "\n".join(lines)


# Alias to avoid shadowing the built-in `date`
from datetime import date as date_module


@tool
def get_daily_totals(target_date: str = "") -> str:
    """Get total calories and macros for a specific day. Use for "how am I doing today?" or "how much protein have I had?"

    Args:
        target_date: Date in YYYY-MM-DD format. Defaults to today. Use "yesterday" for yesterday.

    Returns:
        Calorie and macro totals for the day
    """
    if target_date.lower() == "yesterday":
        d = (date_module.today() - timedelta(days=1)).isoformat()
    elif target_date:
        d = target_date
    else:
        d = None

    with get_db() as conn:
        totals = db_get_daily_totals(conn, DEFAULT_USER_ID, target_date=d)

    if totals["meal_count"] == 0:
        return f"No meals logged for {totals['date']} yet."

    return (
        f"📊 Daily totals for {totals['date']}:\n"
        f"   Calories: {totals['total_calories']:.0f} kcal\n"
        f"   Protein:  {totals['total_protein_g']:.0f}g\n"
        f"   Carbs:    {totals['total_carbs_g']:.0f}g\n"
        f"   Fat:      {totals['total_fat_g']:.0f}g\n"
        f"   Fiber:    {totals['total_fiber_g']:.0f}g\n"
        f"   Meals:    {totals['meal_count']}"
    )


@tool
def lookup_nutrition(food_item: str, quantity: float = 1.0) -> str:
    """Look up nutrition data for a specific food item. Use this BEFORE logging to get accurate calorie/macro estimates.

    Args:
        food_item: Name of the food (e.g., "paratha", "chai", "biryani")
        quantity: Number of servings (e.g., 2.0 for "2 parathas")

    Returns:
        Nutrition data per serving and total, or a message if not found
    """
    result = db_lookup_nutrition(food_item, quantity=quantity)

    if result is None:
        return (
            f"'{food_item}' not found in nutrition database. "
            f"Please estimate the nutrition values using your knowledge."
        )

    return (
        f"Nutrition for {food_item} (x{quantity}):\n"
        f"   Serving: {result.serving_size}\n"
        f"   Calories: {result.calories:.0f} kcal\n"
        f"   Protein:  {result.protein_g:.1f}g\n"
        f"   Carbs:    {result.carbs_g:.1f}g\n"
        f"   Fat:      {result.fat_g:.1f}g\n"
        f"   Fiber:    {result.fiber_g:.1f}g\n"
        f"   Source:   {result.source}"
    )


@tool
def get_user_memory(query: str = "") -> str:
    """Retrieve stored facts about the user. Use to recall dietary preferences, shortcuts ("my usual"), or nutritional goals.

    Args:
        query: Optional search query. If empty, returns all stored memory.

    Returns:
        List of stored facts about the user
    """
    with get_db() as conn:
        if query:
            # Search across all categories
            all_mem = get_all_memory(conn, DEFAULT_USER_ID)
            # Simple keyword matching
            query_lower = query.lower()
            memories = [
                m for m in all_mem
                if query_lower in m["key"].lower() or query_lower in m["value"].lower()
            ]
        else:
            memories = get_all_memory(conn, DEFAULT_USER_ID)

    if not memories:
        return "No stored memories found."

    lines = []
    for m in memories:
        lines.append(f"  [{m['category']}] {m['key']}: {m['value']}")

    return f"User memory ({len(memories)} entries):\n" + "\n".join(lines)


@tool
def set_user_memory(key: str, value: str, category: str) -> str:
    """Store a fact about the user for future sessions. Use when the user shares a lasting preference, defines a shortcut, or sets a goal.

    Args:
        key: Concise key for the fact (e.g., "dietary_restriction", "usual_breakfast", "protein_target")
        value: The fact to remember (e.g., "vegetarian", "2 parathas and chai", "140g daily")
        category: One of "preference", "shortcut", "target", or "personal"

    Returns:
        Confirmation that the fact was stored
    """
    valid_categories = {"preference", "shortcut", "target", "personal"}
    if category not in valid_categories:
        return f"❌ Invalid category '{category}'. Must be one of: {valid_categories}"

    with get_db() as conn:
        upsert_memory(conn, DEFAULT_USER_ID, key, value, category)

    return f"💾 Remembered: [{category}] {key} = {value}"


# Export all tools for the agent
ALL_TOOLS = [
    log_meal,
    update_meal,
    delete_meal,
    get_meals,
    get_daily_totals,
    lookup_nutrition,
    get_user_memory,
    set_user_memory,
]
