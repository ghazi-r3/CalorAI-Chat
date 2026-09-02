"""
FastAPI application — the HTTP surface for CalorAI Chat.

Endpoints:
  POST /chat     — Main chat endpoint (text + optional image)
  GET  /meals    — List meals for a date
  GET  /totals   — Daily totals
  GET  /memory   — View stored memory
  GET  /metrics  — Latency statistics (p50/p95)
  GET  /health   — Health check
"""

import os
import time
import uuid
import shutil
from pathlib import Path
from datetime import date

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import HumanMessage, AIMessage
from dotenv import load_dotenv

from backend.db.database import init_db, get_db
from backend.db.meals import get_meals as db_get_meals, get_daily_totals as db_get_daily_totals
from backend.db.memory import get_all_memory, get_conversation_history
from backend.agent.graph import agent_graph
from backend.models.schemas import ChatRequest, ChatResponse
from backend.middleware.latency import LatencyMiddleware, latency_tracker

load_dotenv()

# Initialize database on startup
init_db()

app = FastAPI(
    title="CalorAI Chat",
    description="Conversational meal logging agent powered by LangGraph + Gemini",
    version="1.0.0",
)

# CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Latency tracking middleware
app.add_middleware(LatencyMiddleware)

# Directory for uploaded images
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


@app.post("/chat", response_model=ChatResponse)
async def chat(
    message: str = Form(...),
    image: UploadFile | None = File(None),
    user_id: str = Form("default"),
    session_id: str = Form(None),
):
    """
    Main chat endpoint. Accepts text and optional image.

    The image is saved to disk and its path is passed to the agent graph.
    The graph handles vision extraction, context loading, agent reasoning,
    tool execution, and memory extraction.
    """
    start_time = time.time()

    # Generate session ID if not provided
    if not session_id:
        session_id = str(uuid.uuid4())[:8]

    # Handle image upload
    image_path = None
    if image:
        # Save uploaded image
        ext = Path(image.filename).suffix or ".jpg"
        image_filename = f"{uuid.uuid4()}{ext}"
        image_path = str(UPLOAD_DIR / image_filename)
        with open(image_path, "wb") as f:
            content = await image.read()
            f.write(content)

    # Load conversation history for multi-turn context
    history_messages = []
    with get_db() as conn:
        history = get_conversation_history(conn, user_id, session_id, limit=10)
        for h in history:
            if h["role"] == "user":
                history_messages.append(HumanMessage(content=h["content"]))
            elif h["role"] == "assistant":
                history_messages.append(AIMessage(content=h["content"]))

    # Build input state
    input_state = {
        "messages": history_messages + [HumanMessage(content=message)],
        "user_id": user_id,
        "session_id": session_id,
        "image_path": image_path,
        "image_description": None,
        "memory_context": "",
        "response_metadata": {},
    }

    # Invoke the agent graph
    try:
        result = agent_graph.invoke(input_state)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")

    # Extract the final response
    response_text = ""
    for msg in reversed(result.get("messages", [])):
        if isinstance(msg, AIMessage) and not msg.tool_calls:
            response_text = msg.content
            break

    if not response_text:
        response_text = "I'm sorry, I couldn't process that. Could you try again?"

    # Calculate latency
    latency_ms = (time.time() - start_time) * 1000
    has_image = image_path is not None
    latency_tracker.record(latency_ms, has_image=has_image)

    return ChatResponse(
        response=response_text,
        latency_ms=round(latency_ms, 1),
    )


@app.post("/chat/text", response_model=ChatResponse)
async def chat_text(request: ChatRequest):
    """
    Text-only chat endpoint (simpler JSON body, no file upload).
    Useful for testing and programmatic access.
    """
    start_time = time.time()

    session_id = request.session_id or str(uuid.uuid4())[:8]

    # Load conversation history
    history_messages = []
    with get_db() as conn:
        history = get_conversation_history(conn, request.user_id, session_id, limit=10)
        for h in history:
            if h["role"] == "user":
                history_messages.append(HumanMessage(content=h["content"]))
            elif h["role"] == "assistant":
                history_messages.append(AIMessage(content=h["content"]))

    # Build input state
    input_state = {
        "messages": history_messages + [HumanMessage(content=request.message)],
        "user_id": request.user_id,
        "session_id": session_id,
        "image_path": request.image_path,
        "image_description": None,
        "memory_context": "",
        "response_metadata": {},
    }

    try:
        result = agent_graph.invoke(input_state)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")

    # Extract response
    response_text = ""
    for msg in reversed(result.get("messages", [])):
        if isinstance(msg, AIMessage) and not msg.tool_calls:
            response_text = msg.content
            break

    if not response_text:
        response_text = "I'm sorry, I couldn't process that. Could you try again?"

    latency_ms = (time.time() - start_time) * 1000
    has_image = request.image_path is not None
    latency_tracker.record(latency_ms, has_image=has_image)

    return ChatResponse(
        response=response_text,
        latency_ms=round(latency_ms, 1),
    )


@app.get("/meals")
async def list_meals(user_id: str = "default", target_date: str = None):
    """List meals for a given date (defaults to today)."""
    with get_db() as conn:
        meals = db_get_meals(conn, user_id, target_date=target_date)
    return {"meals": meals, "date": target_date or date.today().isoformat()}


@app.get("/totals")
async def daily_totals(user_id: str = "default", target_date: str = None):
    """Get daily nutrition totals."""
    with get_db() as conn:
        totals = db_get_daily_totals(conn, user_id, target_date=target_date)
    return totals


@app.get("/memory")
async def view_memory(user_id: str = "default"):
    """View all stored memory for a user. Useful for debugging/inspection."""
    with get_db() as conn:
        memories = get_all_memory(conn, user_id)
    return {"memories": memories, "count": len(memories)}


@app.get("/metrics")
async def metrics():
    """
    Latency statistics (p50/p95) for text and image paths.
    This is a required deliverable — the PDF says to measure and report these.
    """
    return latency_tracker.get_all_stats()


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "calorai-chat"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
