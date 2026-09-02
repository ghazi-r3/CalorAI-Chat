"""
LangGraph agent state definition.

The state flows through every node in the graph. Fields are updated
by individual nodes — LangGraph's `add_messages` reducer handles
message accumulation automatically.
"""

from typing import Annotated, Any
from langgraph.graph.message import add_messages


class AgentState(dict):
    """
    State for the CalorAI agent graph.

    Fields:
        messages:          Chat message history (managed by LangGraph's add_messages reducer)
        user_id:           Current user identifier
        session_id:        Current session identifier
        image_path:        Path to uploaded image (None for text-only)
        image_description: Structured description from vision model (None if no image)
        memory_context:    Formatted memory string injected into system prompt
        response_metadata: Latency timings, tool calls made, etc.
    """
    pass


# Use TypedDict-style annotations for LangGraph
from typing import TypedDict, Optional


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    user_id: str
    session_id: str
    image_path: str | None
    image_description: str | None
    memory_context: str
    response_metadata: dict
