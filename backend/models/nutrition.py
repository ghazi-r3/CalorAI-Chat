"""
Hardcoded nutrition lookup table.

Design decision: We use a hardcoded table of ~50 common foods rather than
a nutrition API. The PDF explicitly states "nutrition data can come from a
small hardcoded table or the model itself" and "we're not evaluating your
nutrition database." This table gives consistent numbers for frequently
mentioned foods (especially South Asian items from the test conversation set);
for anything not in the table, the agent uses its own knowledge to estimate.

Trade-off vs. a real API (e.g., USDA FoodData Central):
  + No external dependency / no API key / no latency hit
  + Deterministic results for common foods
  - Limited coverage (~50 items)
  - No compound recipe decomposition
"""

from backend.models.schemas import NutritionInfo

# Per-serving nutrition data.
# Sources: approximate values from USDA / IFCT (Indian Food Composition Tables).
# Values are intentionally rounded — accuracy is not being evaluated.

NUTRITION_DB: dict[str, dict] = {
    # ── South Asian staples ──────────────────────────────────────────────
    "paratha": {
        "calories": 260, "protein_g": 5, "carbs_g": 30, "fat_g": 14,
        "fiber_g": 1.5, "serving_size": "1 piece (~60g)",
    },
    "roti": {
        "calories": 100, "protein_g": 3, "carbs_g": 18, "fat_g": 2,
        "fiber_g": 2, "serving_size": "1 piece (~30g)",
    },
    "chapati": {  # alias for roti
        "calories": 100, "protein_g": 3, "carbs_g": 18, "fat_g": 2,
        "fiber_g": 2, "serving_size": "1 piece (~30g)",
    },
    "naan": {
        "calories": 260, "protein_g": 8, "carbs_g": 45, "fat_g": 5,
        "fiber_g": 2, "serving_size": "1 piece (~90g)",
    },
    "rice": {
        "calories": 205, "protein_g": 4, "carbs_g": 45, "fat_g": 0.5,
        "fiber_g": 0.5, "serving_size": "1 cup cooked (~160g)",
    },
    "biryani": {
        "calories": 350, "protein_g": 15, "carbs_g": 45, "fat_g": 12,
        "fiber_g": 2, "serving_size": "1 serving (~250g)",
    },
    "pulao": {
        "calories": 280, "protein_g": 6, "carbs_g": 42, "fat_g": 9,
        "fiber_g": 1.5, "serving_size": "1 serving (~200g)",
    },
    "khichdi": {
        "calories": 200, "protein_g": 8, "carbs_g": 32, "fat_g": 4,
        "fiber_g": 3, "serving_size": "1 serving (~200g)",
    },
    "dal": {
        "calories": 180, "protein_g": 12, "carbs_g": 30, "fat_g": 1,
        "fiber_g": 8, "serving_size": "1 cup (~200g)",
    },
    "rajma": {
        "calories": 210, "protein_g": 13, "carbs_g": 35, "fat_g": 1.5,
        "fiber_g": 9, "serving_size": "1 cup (~200g)",
    },
    "chole": {
        "calories": 220, "protein_g": 12, "carbs_g": 34, "fat_g": 4,
        "fiber_g": 8, "serving_size": "1 cup (~200g)",
    },
    "sambar": {
        "calories": 130, "protein_g": 6, "carbs_g": 20, "fat_g": 3,
        "fiber_g": 4, "serving_size": "1 cup (~200g)",
    },
    "idli": {
        "calories": 60, "protein_g": 2, "carbs_g": 12, "fat_g": 0.5,
        "fiber_g": 0.5, "serving_size": "1 piece (~40g)",
    },
    "dosa": {
        "calories": 120, "protein_g": 3, "carbs_g": 18, "fat_g": 4,
        "fiber_g": 1, "serving_size": "1 piece (~50g)",
    },
    "poha": {
        "calories": 180, "protein_g": 4, "carbs_g": 32, "fat_g": 5,
        "fiber_g": 2, "serving_size": "1 serving (~150g)",
    },
    "upma": {
        "calories": 200, "protein_g": 5, "carbs_g": 28, "fat_g": 7,
        "fiber_g": 2, "serving_size": "1 serving (~150g)",
    },

    # ── South Asian proteins ─────────────────────────────────────────────
    "paneer": {
        "calories": 265, "protein_g": 18, "carbs_g": 3.5, "fat_g": 20,
        "fiber_g": 0, "serving_size": "100g",
    },
    "chicken curry": {
        "calories": 240, "protein_g": 20, "carbs_g": 8, "fat_g": 14,
        "fiber_g": 1, "serving_size": "1 serving (~200g)",
    },
    "butter chicken": {
        "calories": 300, "protein_g": 22, "carbs_g": 10, "fat_g": 20,
        "fiber_g": 1, "serving_size": "1 serving (~200g)",
    },
    "egg curry": {
        "calories": 220, "protein_g": 14, "carbs_g": 8, "fat_g": 15,
        "fiber_g": 1, "serving_size": "1 serving (2 eggs + gravy)",
    },
    "fish curry": {
        "calories": 200, "protein_g": 22, "carbs_g": 6, "fat_g": 10,
        "fiber_g": 0.5, "serving_size": "1 serving (~200g)",
    },
    "paneer butter masala": {
        "calories": 320, "protein_g": 15, "carbs_g": 12, "fat_g": 24,
        "fiber_g": 1, "serving_size": "1 serving (~200g)",
    },

    # ── South Asian drinks & snacks ──────────────────────────────────────
    "chai": {
        "calories": 120, "protein_g": 3, "carbs_g": 15, "fat_g": 5,
        "fiber_g": 0, "serving_size": "1 cup (~200ml)",
    },
    "lassi": {
        "calories": 170, "protein_g": 5, "carbs_g": 28, "fat_g": 4,
        "fiber_g": 0, "serving_size": "1 glass (~250ml)",
    },
    "buttermilk": {
        "calories": 40, "protein_g": 3, "carbs_g": 5, "fat_g": 1,
        "fiber_g": 0, "serving_size": "1 glass (~250ml)",
    },
    "raita": {
        "calories": 60, "protein_g": 3, "carbs_g": 5, "fat_g": 3,
        "fiber_g": 0.5, "serving_size": "1 serving (~100g)",
    },

    # ── South Asian desserts ─────────────────────────────────────────────
    "gulab jamun": {
        "calories": 150, "protein_g": 2, "carbs_g": 22, "fat_g": 6,
        "fiber_g": 0, "serving_size": "1 piece (~40g)",
    },
    "halwa": {
        "calories": 250, "protein_g": 3, "carbs_g": 35, "fat_g": 12,
        "fiber_g": 1, "serving_size": "1 serving (~80g)",
    },
    "jalebi": {
        "calories": 150, "protein_g": 1, "carbs_g": 30, "fat_g": 4,
        "fiber_g": 0, "serving_size": "1 piece (~30g)",
    },

    # ── Common proteins ──────────────────────────────────────────────────
    "chicken breast": {
        "calories": 165, "protein_g": 31, "carbs_g": 0, "fat_g": 3.6,
        "fiber_g": 0, "serving_size": "100g cooked",
    },
    "egg": {
        "calories": 72, "protein_g": 6, "carbs_g": 0.5, "fat_g": 5,
        "fiber_g": 0, "serving_size": "1 large (~50g)",
    },
    "salmon": {
        "calories": 208, "protein_g": 20, "carbs_g": 0, "fat_g": 13,
        "fiber_g": 0, "serving_size": "100g cooked",
    },
    "tofu": {
        "calories": 144, "protein_g": 15, "carbs_g": 3, "fat_g": 8,
        "fiber_g": 1, "serving_size": "100g",
    },

    # ── Western staples ──────────────────────────────────────────────────
    "bread": {
        "calories": 75, "protein_g": 3, "carbs_g": 13, "fat_g": 1,
        "fiber_g": 1, "serving_size": "1 slice (~30g)",
    },
    "oatmeal": {
        "calories": 150, "protein_g": 5, "carbs_g": 27, "fat_g": 3,
        "fiber_g": 4, "serving_size": "1 cup cooked (~240g)",
    },
    "pasta": {
        "calories": 220, "protein_g": 8, "carbs_g": 43, "fat_g": 1.3,
        "fiber_g": 2.5, "serving_size": "1 cup cooked (~140g)",
    },
    "pizza": {
        "calories": 285, "protein_g": 12, "carbs_g": 36, "fat_g": 10,
        "fiber_g": 2.5, "serving_size": "1 slice (~110g)",
    },

    # ── Dairy ────────────────────────────────────────────────────────────
    "milk": {
        "calories": 120, "protein_g": 8, "carbs_g": 12, "fat_g": 5,
        "fiber_g": 0, "serving_size": "1 cup (~240ml, whole)",
    },
    "yogurt": {
        "calories": 100, "protein_g": 6, "carbs_g": 12, "fat_g": 3,
        "fiber_g": 0, "serving_size": "1 cup (~170g)",
    },
    "cheese": {
        "calories": 110, "protein_g": 7, "carbs_g": 0.5, "fat_g": 9,
        "fiber_g": 0, "serving_size": "1 slice (~28g)",
    },
    "greek yogurt": {
        "calories": 130, "protein_g": 12, "carbs_g": 8, "fat_g": 5,
        "fiber_g": 0, "serving_size": "1 cup (~170g)",
    },

    # ── Fruits ───────────────────────────────────────────────────────────
    "banana": {
        "calories": 105, "protein_g": 1.3, "carbs_g": 27, "fat_g": 0.3,
        "fiber_g": 3, "serving_size": "1 medium (~120g)",
    },
    "apple": {
        "calories": 95, "protein_g": 0.5, "carbs_g": 25, "fat_g": 0.3,
        "fiber_g": 4, "serving_size": "1 medium (~180g)",
    },
    "mango": {
        "calories": 100, "protein_g": 1, "carbs_g": 25, "fat_g": 0.5,
        "fiber_g": 2.5, "serving_size": "1 cup sliced (~165g)",
    },
    "orange": {
        "calories": 62, "protein_g": 1.2, "carbs_g": 15, "fat_g": 0.2,
        "fiber_g": 3, "serving_size": "1 medium (~130g)",
    },

    # ── Nuts & seeds ─────────────────────────────────────────────────────
    "almonds": {
        "calories": 164, "protein_g": 6, "carbs_g": 6, "fat_g": 14,
        "fiber_g": 3.5, "serving_size": "1 oz (~28g)",
    },
    "peanuts": {
        "calories": 170, "protein_g": 7, "carbs_g": 5, "fat_g": 14,
        "fiber_g": 2.5, "serving_size": "1 oz (~28g)",
    },

    # ── Beverages ────────────────────────────────────────────────────────
    "coffee": {
        "calories": 5, "protein_g": 0.3, "carbs_g": 0.5, "fat_g": 0,
        "fiber_g": 0, "serving_size": "1 cup black (~240ml)",
    },
    "green tea": {
        "calories": 2, "protein_g": 0, "carbs_g": 0.5, "fat_g": 0,
        "fiber_g": 0, "serving_size": "1 cup (~240ml)",
    },
    "protein shake": {
        "calories": 200, "protein_g": 30, "carbs_g": 10, "fat_g": 4,
        "fiber_g": 1, "serving_size": "1 scoop + water (~350ml)",
    },

    # ── Vegetables / salads ──────────────────────────────────────────────
    "mixed vegetables": {
        "calories": 80, "protein_g": 3, "carbs_g": 15, "fat_g": 1,
        "fiber_g": 4, "serving_size": "1 cup cooked (~160g)",
    },
    "salad": {
        "calories": 50, "protein_g": 2, "carbs_g": 8, "fat_g": 1,
        "fiber_g": 3, "serving_size": "1 bowl (~150g, no dressing)",
    },
}

# ── Aliases: map common variations to canonical names ────────────────────────

_ALIASES: dict[str, str] = {
    "chapathi": "chapati",
    "roti": "roti",
    "rotis": "roti",
    "parathas": "paratha",
    "paranthas": "paratha",
    "parantha": "paratha",
    "tea": "chai",
    "chai tea": "chai",
    "eggs": "egg",
    "daal": "dal",
    "dhal": "dal",
    "naans": "naan",
    "idlis": "idli",
    "dosas": "dosa",
    "chicken": "chicken breast",
}


def lookup_nutrition(
    food_item: str,
    quantity: float = 1.0,
    unit: str = "serving",
) -> NutritionInfo | None:
    """
    Look up nutrition data for a food item.

    Returns NutritionInfo if found in the hardcoded table, None otherwise.
    When None, the agent should use its own knowledge to estimate.

    Quantities are multiplied into the base per-serving values.
    """
    key = food_item.strip().lower()

    # Resolve aliases
    key = _ALIASES.get(key, key)

    entry = NUTRITION_DB.get(key)
    if entry is None:
        return None

    return NutritionInfo(
        food_item=food_item,
        calories=round(entry["calories"] * quantity, 1),
        protein_g=round(entry["protein_g"] * quantity, 1),
        carbs_g=round(entry["carbs_g"] * quantity, 1),
        fat_g=round(entry["fat_g"] * quantity, 1),
        fiber_g=round(entry["fiber_g"] * quantity, 1),
        serving_size=f"{quantity} x {entry['serving_size']}",
        source="hardcoded",
    )
