"""
LangGraph node implementations.

Each node modifies the AgentState and returns the updated state.
Nodes are the building blocks of the conversation graph:

  preprocess → load_context → agent ↔ tools → post_process

The graph is inspectable: each node has a single, documented responsibility.
"""

import json
import os
import time
from datetime import date

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

from backend.agent.state import AgentState
from backend.agent.prompts import SYSTEM_PROMPT, MEMORY_EXTRACTION_PROMPT
from backend.agent.tools import ALL_TOOLS
from backend.db.database import get_db
from backend.db.memory import (
    get_memory_by_category,
    get_all_memory,
    upsert_memory,
    save_message,
    get_conversation_history,
)
from backend.vision.processor import extract_food_from_image

load_dotenv()


def preprocess(state: AgentState) -> dict:
    """
    Preprocess the incoming message.

    - If an image is provided, call the vision model to extract food data
    - Merge vision output with any text caption into a single message
    - This ensures photo + caption → ONE meal log (not two)
    """
    image_path = state.get("image_path")
    image_description = None

    if image_path:
        try:
            vision_result = extract_food_from_image(image_path)
            image_description = json.dumps({
                "description": vision_result.description,
                "items": [item.model_dump() for item in vision_result.items],
                "confidence": vision_result.confidence,
                "notes": vision_result.notes,
            })

            # Get the last human message and merge vision data into it
            messages = list(state["messages"])
            if messages and isinstance(messages[-1], HumanMessage):
                original_text = messages[-1].content
                confidence = vision_result.confidence

                # Build merged message
                if confidence < 0.7:
                    vision_prefix = (
                        f"[📸 Image analysis (low confidence {confidence:.0%})]\n"
                        f"I see what might be: {vision_result.description}\n"
                        f"Items detected: {', '.join(f'{i.quantity} {i.unit} {i.name}' for i in vision_result.items)}\n"
                        f"⚠️ Notes: {vision_result.notes}\n"
                    )
                else:
                    vision_prefix = (
                        f"[📸 Image analysis (confidence {confidence:.0%})]\n"
                        f"Detected: {vision_result.description}\n"
                        f"Items: {', '.join(f'{i.quantity} {i.unit} {i.name}' for i in vision_result.items)}\n"
                    )

                if original_text and original_text.strip():
                    merged = f"{vision_prefix}\nUser caption: {original_text}"
                else:
                    merged = vision_prefix

                # Replace the last message with the merged one
                messages[-1] = HumanMessage(content=merged)
                return {
                    "messages": messages,
                    "image_description": image_description,
                }

        except Exception as e:
            # If vision fails, proceed with text only
            image_description = json.dumps({
                "error": str(e),
                "confidence": 0.0,
            })

    return {"image_description": image_description}


def load_context(state: AgentState) -> dict:
    """
    Load relevant memory and conversation history into context.

    THIS IS THE MEMORY RETRIEVE PATH — where we decide what memory
    to pull into the agent's context.

    Strategy:
      - Always load: preferences (dietary restrictions) + targets (nutrition goals)
      - Conditionally: shortcuts (when user references "my usual", "same as", etc.)
      - Format as a concise "User Profile" block in the system message
    """
    user_id = state.get("user_id", "default")
    session_id = state.get("session_id", "default")

    # Determine which memory categories to load
    categories = ["preference", "target"]  # Always loaded

    # Check if user message contains reference-like patterns
    messages = state.get("messages", [])
    last_user_msg = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_user_msg = msg.content.lower()
            break

    reference_patterns = [
        "my usual", "same as", "like yesterday", "like last",
        "the usual", "what i had", "what i ate", "again",
    ]
    if any(p in last_user_msg for p in reference_patterns):
        categories.append("shortcut")

    # Also load shortcuts if user says "my" + food reference
    if "my " in last_user_msg:
        categories.append("shortcut")

    # Deduplicate
    categories = list(set(categories))

    # Load memory
    with get_db() as conn:
        memories = get_memory_by_category(conn, user_id, categories)

    # Format memory context
    if memories:
        memory_lines = []
        for m in memories:
            memory_lines.append(f"- [{m['category']}] {m['key']}: {m['value']}")
        memory_context = (
            "\n## User Profile (from memory)\n"
            + "\n".join(memory_lines)
        )
    else:
        memory_context = "\n## User Profile\nNo stored preferences or goals yet."

    return {"memory_context": memory_context}


def build_system_message(state: AgentState) -> SystemMessage:
    """Build the system message with memory context injected."""
    memory_context = state.get("memory_context", "")
    current_date = date.today().isoformat()

    prompt = SYSTEM_PROMPT.format(
        memory_context=memory_context,
        current_date=current_date,
    )
    return SystemMessage(content=prompt)


def agent_node(state: AgentState) -> dict:
    """
    Core agent node — invokes the LLM with tools bound.

    Uses Gemini Flash for fast text reasoning + tool calling.
    The LLM decides whether to:
      (a) call a tool (the graph loops back through tool execution)
      (b) respond to the user (the graph exits the loop)

    This IS the ambiguity decision point — the LLM judges whether it has
    enough info to log or needs to ask a clarifying question.
    """
    # Build the full message list with system prompt
    system_msg = build_system_message(state)
    messages = [system_msg] + list(state["messages"])

    # Create the LLM with tools bound
    llm = ChatGoogleGenerativeAI(
        model="gemini-3.1-flash-lite",
        temperature=0.3,
        max_output_tokens=2048,
    )
    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    # Invoke
    response = llm_with_tools.invoke(messages)

    return {"messages": [response]}


def post_process(state: AgentState) -> dict:
    """
    Post-process after the agent responds.

    THIS IS THE MEMORY WRITE PATH — where we decide what facts to persist.

    1. Extract any facts worth remembering from the conversation turn
    2. Save conversation history for multi-turn context
    """
    user_id = state.get("user_id", "default")
    session_id = state.get("session_id", "default")
    messages = state.get("messages", [])

    # Find the last user message and last assistant message
    last_user_msg = ""
    last_assistant_msg = ""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not last_assistant_msg and not msg.tool_calls:
            content = msg.content
            if isinstance(content, list):
                last_assistant_msg = " ".join([p.get("text", "") for p in content if isinstance(p, dict)])
            else:
                last_assistant_msg = content
        elif isinstance(msg, HumanMessage) and not last_user_msg:
            last_user_msg = msg.content
        if last_user_msg and last_assistant_msg:
            break

    if not last_user_msg or not last_assistant_msg:
        return {}

    # ── Memory extraction (LLM-driven) ──────────────────────────────────
    try:
        extraction_prompt = MEMORY_EXTRACTION_PROMPT.format(
            user_message=last_user_msg,
            assistant_message=last_assistant_msg,
        )

        llm = ChatGoogleGenerativeAI(
            model="gemini-3.1-flash-lite",
            temperature=0.1,
            max_output_tokens=512,
        )
        response = llm.invoke([HumanMessage(content=extraction_prompt)])
        raw = response.content.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            lines = raw.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            raw = "\n".join(lines)

        extracted = json.loads(raw)

        if extracted and isinstance(extracted, list):
            with get_db() as conn:
                for entry in extracted:
                    if all(k in entry for k in ("key", "value", "category")):
                        upsert_memory(
                            conn,
                            user_id,
                            entry["key"],
                            entry["value"],
                            entry["category"],
                        )
    except (json.JSONDecodeError, Exception):
        # Memory extraction is best-effort — don't break the response
        pass

    # ── Save conversation history ────────────────────────────────────────
    try:
        with get_db() as conn:
            save_message(conn, user_id, session_id, "user", last_user_msg)
            save_message(conn, user_id, session_id, "assistant", last_assistant_msg)
    except Exception:
        pass

    return {}
