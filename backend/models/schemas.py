"""
Pydantic models for CalorAI Chat.

These models define the data contracts between:
  - The FastAPI endpoints and the client
  - The agent tools and the database layer
  - The vision processor and the agent
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ── Meal models ──────────────────────────────────────────────────────────────

class MealItem(BaseModel):
    """A single food item within a meal."""
    name: str
    quantity: float = 1.0
    unit: str = "serving"


class MealCreate(BaseModel):
    """Data required to log a new meal."""
    description: str
    items: list[MealItem] = Field(default_factory=list)
    calories: float = 0
    protein_g: float = 0
    carbs_g: float = 0
    fat_g: float = 0
    fiber_g: float = 0
    meal_type: str | None = None
    source: str = "text"
    raw_input: str | None = None
    image_path: str | None = None


class MealUpdate(BaseModel):
    """Partial update for an existing meal (only non-None fields are applied)."""
    description: str | None = None
    items: list[MealItem] | None = None
    calories: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    fiber_g: float | None = None
    meal_type: str | None = None


class MealResponse(BaseModel):
    """A meal as returned from the database."""
    id: int
    user_id: str
    timestamp: str
    meal_type: str | None = None
    description: str
    items: str  # JSON string
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float
    source: str
    raw_input: str | None = None
    image_path: str | None = None


# ── Daily totals ─────────────────────────────────────────────────────────────

class DailyTotals(BaseModel):
    """Aggregated nutrition totals for a single day."""
    date: str
    total_calories: float = 0
    total_protein_g: float = 0
    total_carbs_g: float = 0
    total_fat_g: float = 0
    total_fiber_g: float = 0
    meal_count: int = 0


# ── Memory ───────────────────────────────────────────────────────────────────

class MemoryEntry(BaseModel):
    """A single persistent memory fact about a user."""
    key: str
    value: str
    category: str  # "preference" | "shortcut" | "target" | "personal"
    confidence: float = 1.0


# ── Nutrition ────────────────────────────────────────────────────────────────

class NutritionInfo(BaseModel):
    """Nutrition data for a single food item."""
    food_item: str
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float
    serving_size: str
    source: str = "hardcoded"  # "hardcoded" | "estimated"


# ── Vision ───────────────────────────────────────────────────────────────────

class VisionResult(BaseModel):
    """Structured output from the vision model."""
    description: str
    items: list[MealItem] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    notes: str = ""  # e.g., "Could not determine portion size"


# ── Chat API ─────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    """Incoming chat message from the client."""
    message: str
    image_path: str | None = None
    user_id: str = "default"
    session_id: str | None = None


class ChatResponse(BaseModel):
    """Response from the agent to the client."""
    response: str
    meals_logged: list[dict] = Field(default_factory=list)
    meals_updated: list[dict] = Field(default_factory=list)
    latency_ms: float = 0
