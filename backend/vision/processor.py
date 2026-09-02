"""
Gemini Vision processor — extracts structured food descriptions from images.

This is architecturally separated from the text conversation model:
  - Vision path: Gemini multimodal — extracts structured food data ONLY
  - Text path: Gemini text — handles conversation, reasoning, tool-calling

Both use the same provider (Gemini) but are logically distinct pipelines.
The vision model's output feeds INTO the text pipeline as if the user had
typed the description. This separation is a deliberate architectural choice,
not "running everything through one model" (which is a stated red flag).

Why Gemini for both:
  - Native multimodal support (no separate image-to-text service needed)
  - Single API key / single provider simplifies deployment
  - Gemini Flash is fast enough for both paths
  - Cost-effective for a test task
"""

import json
import os
import time
import base64
from pathlib import Path

from google import genai
from google.genai import types
from dotenv import load_dotenv

from backend.agent.prompts import VISION_PROMPT
from backend.models.schemas import VisionResult, MealItem

load_dotenv()
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))


def extract_food_from_image(image_path: str) -> VisionResult:
    """
    Send an image to Gemini Vision and extract a structured food description.

    This is a SEPARATE model call from the conversation agent. Its output
    is a structured VisionResult that gets merged with any text caption
    before being passed to the conversation agent.

    Args:
        image_path: Path to the image file

    Returns:
        VisionResult with description, items, confidence, and notes

    Raises:
        FileNotFoundError: If the image file doesn't exist
        ValueError: If the image can't be processed
    """
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    # Read and prepare the image
    image_data = path.read_bytes()

    # Determine MIME type
    suffix = path.suffix.lower()
    mime_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    mime_type = mime_types.get(suffix, "image/jpeg")

    # Use Gemini Flash for vision (fast, multimodal-capable)
    start_time = time.time()

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=[
            VISION_PROMPT,
            types.Part.from_bytes(
                data=image_data,
                mime_type=mime_type,
            ),
        ],
        config=types.GenerateContentConfig(
            temperature=0.2,  # Low temperature for structured extraction
            max_output_tokens=1024,
        ),
    )

    vision_latency_ms = (time.time() - start_time) * 1000

    # Parse the response
    raw_text = response.text.strip()

    # Strip markdown code fences if present
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        # Remove first line (```json) and last line (```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw_text = "\n".join(lines)

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        # If parsing fails, create a basic result from the raw text
        return VisionResult(
            description=raw_text[:200],
            items=[],
            confidence=0.3,
            notes=f"Vision model returned non-JSON response. Raw: {raw_text[:100]}",
        )

    # Build VisionResult
    items = []
    for item in data.get("items", []):
        items.append(MealItem(
            name=item.get("name", "unknown"),
            quantity=float(item.get("quantity", 1.0)),
            unit=item.get("unit", "serving"),
        ))

    result = VisionResult(
        description=data.get("description", "Food detected in image"),
        items=items,
        confidence=float(data.get("confidence", 0.5)),
        notes=data.get("notes", ""),
    )

    return result
