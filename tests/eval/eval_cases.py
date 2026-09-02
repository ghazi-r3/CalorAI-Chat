"""
Eval cases for CalorAI Chat.

These define "correct" behavior for the test conversation set from the PDF.
Each case specifies:
  - input: what the user sends
  - expected_behavior: what the agent SHOULD do (tools called, response properties)
  - critical: whether this is one of the three "separating" cases

This is a structured eval set (a green flag per the PDF) rather than a
full automated eval pipeline — we define what "correct" means and can
verify it manually or semi-automatically.
"""

EVAL_CASES = [
    # ── Case 1: Simple meal logging ──────────────────────────────────────
    {
        "id": "simple_meal",
        "input": "had 2 parathas and chai for breakfast",
        "expected_behavior": {
            "tools_called": ["lookup_nutrition", "log_meal"],
            "response_contains": ["logged", "paratha", "chai"],
            "meal_logged": True,
            "meal_type": "breakfast",
            "items_include": ["paratha", "chai"],
        },
        "critical": False,
        "notes": "Straightforward logging. Agent should look up nutrition, then log.",
    },

    # ── Case 2: Vague quantity ───────────────────────────────────────────
    {
        "id": "vague_quantity",
        "input": "leftover biryani, maybe two thirds of the box",
        "expected_behavior": {
            "tools_called": ["lookup_nutrition", "log_meal"],
            "response_contains": ["biryani"],
            "meal_logged": True,
            "should_estimate_portion": True,
        },
        "critical": False,
        "notes": "Agent should estimate ~2/3 serving and mention the assumption.",
    },

    # ── Case 3: Too vague — should ask ───────────────────────────────────
    {
        "id": "too_vague",
        "input": "skipped lunch but grazed all afternoon",
        "expected_behavior": {
            "tools_called": [],
            "should_ask_clarification": True,
            "should_not_log": True,
        },
        "critical": False,
        "notes": "Agent should ask what they snacked on, not log 'grazed' with 0 cal.",
    },

    # ── Case 4: CRITICAL — "same as yesterday" ──────────────────────────
    {
        "id": "same_as_yesterday",
        "input": "same as yesterday",
        "expected_behavior": {
            "tools_called": ["get_meals"],
            "should_lookup_history": True,
            "should_replicate_meal": True,
        },
        "critical": True,
        "notes": (
            "CRITICAL: Must resolve via memory/history lookup, not parsing. "
            "Agent should call get_meals(date='yesterday') and replicate."
        ),
    },

    # ── Case 5: CRITICAL — Correction without double-count ───────────────
    {
        "id": "correction_rotis",
        "input": "actually that was 3 rotis not 2",
        "precondition": "A meal with '2 rotis' must exist in today's meals",
        "expected_behavior": {
            "tools_called": ["get_meals", "update_meal"],
            "should_NOT_call": ["log_meal"],
            "total_should_reflect_update": True,
        },
        "critical": True,
        "notes": (
            "CRITICAL: Must use update_meal (not log_meal). "
            "Daily totals must show corrected value, not original + corrected."
        ),
    },

    # ── Case 6: Protein check ────────────────────────────────────────────
    {
        "id": "protein_check",
        "input": "how much protein have I had today?",
        "expected_behavior": {
            "tools_called": ["get_daily_totals"],
            "response_contains": ["protein"],
            "should_show_totals": True,
        },
        "critical": False,
        "notes": "Should call get_daily_totals and report protein.",
    },

    # ── Case 7: Calorie check ────────────────────────────────────────────
    {
        "id": "calorie_check",
        "input": "how am I doing on calories?",
        "expected_behavior": {
            "tools_called": ["get_daily_totals"],
            "response_contains": ["calories", "kcal"],
            "should_show_totals": True,
        },
        "critical": False,
        "notes": "Should call get_daily_totals and show calorie progress.",
    },

    # ── Case 8: CRITICAL — Photo + caption → one meal ────────────────────
    {
        "id": "photo_with_caption",
        "input": "half of this was my brother's",
        "image_path": "test_food_photo.jpg",
        "expected_behavior": {
            "tools_called": ["log_meal"],
            "should_NOT_call": [],
            "vision_used": True,
            "single_meal_logged": True,
            "portions_adjusted": True,
        },
        "critical": True,
        "notes": (
            "CRITICAL: Photo goes to vision model, caption adjusts portions. "
            "Must result in ONE meal log (half portion), not two."
        ),
    },

    # ── Case 9: Photo only (no caption) ──────────────────────────────────
    {
        "id": "photo_only",
        "input": "",
        "image_path": "test_food_photo.jpg",
        "expected_behavior": {
            "tools_called": ["log_meal"],
            "vision_used": True,
            "single_meal_logged": True,
        },
        "critical": False,
        "notes": "Photo with no caption. Vision model identifies food, agent logs.",
    },

    # ── Case 10: "my usual" ──────────────────────────────────────────────
    {
        "id": "my_usual",
        "input": "my usual",
        "precondition": "Memory entry 'usual_breakfast' or similar must exist",
        "expected_behavior": {
            "tools_called": ["get_user_memory"],
            "should_lookup_memory": True,
            "should_resolve_shortcut": True,
        },
        "critical": False,
        "notes": "Should resolve via memory lookup. If no memory exists, should ask what 'my usual' means.",
    },

    # ── Case 11: Preference storage ──────────────────────────────────────
    {
        "id": "vegetarian_preference",
        "input": "i'm vegetarian btw",
        "expected_behavior": {
            "tools_called": ["set_user_memory"],
            "memory_stored": True,
            "memory_key": "dietary_restriction",
            "memory_value_contains": "vegetarian",
            "memory_category": "preference",
        },
        "critical": False,
        "notes": "Should store as preference memory AND acknowledge naturally.",
    },
]


def print_eval_summary():
    """Print a summary of all eval cases."""
    print(f"\n{'='*60}")
    print(f"CalorAI Eval Cases: {len(EVAL_CASES)} total")
    print(f"{'='*60}\n")

    critical = [c for c in EVAL_CASES if c.get("critical")]
    print(f"🔴 CRITICAL cases ({len(critical)}):")
    for c in critical:
        print(f"   {c['id']}: {c['notes'][:80]}")

    print(f"\n🟢 Standard cases ({len(EVAL_CASES) - len(critical)}):")
    for c in EVAL_CASES:
        if not c.get("critical"):
            print(f"   {c['id']}: {c['input'][:50]}")

    print(f"\n{'='*60}")


if __name__ == "__main__":
    print_eval_summary()
