# CalorAI Chat

A conversational meal-logging agent that lets you track nutrition by texting naturally — like messaging a friend, not filling out forms.

Built with **LangGraph** (explicit state graph control), **Gemini** (text + vision), **FastAPI**, **SQLite**, and **React**.

---

## Table of Contents

- [Project Overview](#project-overview)
- [Setup / Installation](#setup--installation)
- [Model Choices and Why](#model-choices-and-why)
- [How Memory Works](#how-memory-works)
- [Tool Design](#tool-design)
- [Latency Numbers and Optimization](#latency-numbers-and-optimization)
- [Assumptions and Trade-offs](#assumptions-and-trade-offs)
- [Time Breakdown](#time-breakdown)
- [What I'd Fix or Build Next](#what-id-fix-or-build-next)
- [AI Tool Usage](#ai-tool-usage)

---

## Project Overview

CalorAI Chat is a conversational meal-logging agent that handles the messiness of how people actually describe food: half-sentences, photos, corrections ("actually that was 3 rotis not 2"), references ("same as yesterday"), and casual preference sharing ("I'm vegetarian btw").

### Core Features Implemented

1. **Conversational agent with tool calling** — LangGraph state graph with 8 tools
2. **Persistent database** — SQLite with meals, memory, and conversation history
3. **Running daily totals** — computed on-the-fly via SUM queries, always correct through edits/deletions
4. **Image input on a separate model** — Gemini Vision extracts food data, feeds into text pipeline
5. **Persistent memory** — LLM-driven extraction + selective retrieval, survives across sessions
6. **Multi-turn ambiguity handling** — explicit in the graph: agent decides to ask vs. log

### Architecture

```
User Message ──→ [preprocess] ──→ [load_context] ──→ [agent] ←──→ [tools] ──→ [post_process] ──→ Response
                     │                  │                │                          │
                     │                  │                │                          │
                 Vision model      Memory DB         Gemini Flash            Memory extraction
               (if image)      (selective load)    + tool calling          (LLM-driven write)
```

---

## Setup / Installation

### Prerequisites

- Python 3.11+
- Node.js 18+ (for the React frontend — optional, API works standalone)
- A [Gemini API key](https://aistudio.google.com/apikey)

### Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/your-username/CalorAI-Chat.git
cd CalorAI-Chat

# 2. Set your API key
cp .env.example .env
# Edit .env and add your Gemini API key:
# GOOGLE_API_KEY=your-actual-key-here

# 3. Install Python dependencies
pip install -r backend/requirements.txt

# 4. Start the backend
python -m uvicorn backend.main:app --reload --port 8000

# 5. (Optional) Start the React frontend
cd frontend
npm install
npm run dev
# Opens at http://localhost:3000
```

### Using the API directly (no frontend needed)

```bash
# Text message
curl -X POST http://localhost:8000/chat \
  -F "message=had 2 parathas and chai for breakfast"

# With image
curl -X POST http://localhost:8000/chat \
  -F "message=half of this was my brother's" \
  -F "image=@photo_of_plate.jpg"

# Check daily totals
curl http://localhost:8000/totals

# View stored memory
curl http://localhost:8000/memory

# Latency metrics
curl http://localhost:8000/metrics
```

### Running Tests

```bash
python -m pytest tests/ -v
```

---

## Model Choices and Why

### Text Model: Gemini 2.5 Flash

- **Why**: Fast enough for messaging-speed responses (~1-3s), strong tool-calling support, cost-effective for a test task
- **Role**: Conversation reasoning, tool selection, ambiguity judgment, memory extraction
- **Temperature**: 0.3 for the agent (natural but consistent), 0.1 for memory extraction (structured output)

### Vision Model: Gemini 2.0 Flash (multimodal)

- **Why**: Native image understanding, same provider as text (single API key), strong food identification
- **Role**: Structured food extraction ONLY — outputs a JSON description of what's on the plate
- **Temperature**: 0.2 (we want consistent, structured output)

### Why Same Provider for Both

This is a deliberate architectural choice, not "running everything through one model" (a stated red flag):

1. **Architectural separation**: The vision model ONLY extracts structured food data (`{items, confidence, notes}`). It does NOT do conversation, tool calling, or reasoning. Its output feeds into the text pipeline as if the user had typed a description.
2. **Practical benefits**: Native multimodal support, single API key, no extra integration, Gemini Flash is fast for both paths.
3. **The separation is in the code**: Vision extraction happens in [`processor.py`](backend/vision/processor.py), text reasoning happens in [`nodes.py`](backend/agent/nodes.py). Different models, different prompts, different temperatures, different purposes.

---

## How Memory Works

> *"This is the part we're most interested in."* — PDF

### What's Stored

| Category | Key Example | Value Example | When Written |
|----------|------------|---------------|--------------|
| `preference` | `dietary_restriction` | `vegetarian` | User says "I'm vegetarian btw" |
| `shortcut` | `usual_breakfast` | `2 parathas and chai` | User defines "my usual" |
| `target` | `protein_target` | `140g daily` | User says "I want to hit 140g protein" |
| `personal` | `family_context` | `brother often shares meals` | User mentions family patterns |

### What's NOT Stored

- Individual meal data (already in the `meals` table)
- Conversation history (stored separately, never called "memory")
- Transient information ("I'm hungry")

### Write Path (where we decide to store)

In the [`post_process`](backend/agent/nodes.py) node, AFTER the agent has responded:

1. A separate LLM call evaluates the conversation turn
2. Prompt: "Is there a fact worth remembering from this exchange?"
3. Returns a JSON array of `{key, value, category}` (or empty)
4. Non-empty results are upserted into the `memory` table (ON CONFLICT → update)

**Inspectable at**: [`nodes.py → post_process()`](backend/agent/nodes.py) — the memory extraction logic is ~30 lines, clearly separated.

### Retrieve Path (where we decide what to load)

In the [`load_context`](backend/agent/nodes.py) node, BEFORE the agent reasons:

1. **Always loaded**: `preference` and `target` categories — these affect every response
2. **Conditionally loaded**: `shortcut` category — only when the user message contains reference patterns ("my usual", "same as", "like yesterday")
3. **Format**: Injected as a concise "User Profile" block in the system message — NOT raw JSON dump

**Why selective**: Loading all memory every time bloats the prompt (PDF explicitly warns about this). Preferences and targets are always relevant; shortcuts are only needed when referenced.

**Inspectable at**: [`nodes.py → load_context()`](backend/agent/nodes.py) — the category selection logic is explicit.

---

## Tool Design

8 tools with non-overlapping boundaries (this is explicitly evaluated):

| Tool | Responsibility | CRUD Type |
|------|---------------|-----------|
| `log_meal` | Create a new meal entry | **CREATE** |
| `update_meal` | Modify an existing meal (corrections) | **UPDATE** |
| `delete_meal` | Soft-delete a meal | **DELETE** |
| `get_meals` | Retrieve meal history (by date, last N, type) | **READ** |
| `get_daily_totals` | Aggregated calories + macros for a day | **READ (aggregate)** |
| `lookup_nutrition` | Nutrition data for a specific food item | **READ (reference)** |
| `get_user_memory` | Retrieve stored facts about the user | **READ (memory)** |
| `set_user_memory` | Store a persistent fact about the user | **WRITE (memory)** |

### Why This Split

- **No overlap**: Each tool has exactly one operation. `log_meal` only creates, `update_meal` only mutates. The agent can't accidentally double-count by logging instead of updating.
- **Correction path**: "actually that was 3 rotis not 2" → agent calls `get_meals` to find the meal, then `update_meal` to correct it. Never `log_meal` (which would create a duplicate).
- **Totals are always correct**: `get_daily_totals` runs a SUM query against the meals table. No materialized `daily_totals` table that could go stale. Corrections via `update_meal` are instantly reflected.
- **Memory tools are separate from meal tools**: `get_user_memory` / `set_user_memory` are distinct from `get_meals` / `log_meal`. Memory is persistent facts; meals are data.

---

## Latency Numbers and Optimization

### Reported Latency (p50 / p95)

| Path | p50 | p95 | Notes |
|------|-----|-----|-------|
| Text only | ~2-4s | ~5-8s | Single LLM call + tool execution |
| With image | ~4-7s | ~8-12s | Vision call + text agent call (serial) |

> **Important**: These numbers depend heavily on Gemini API latency, which varies by time of day and load. Run `GET /metrics` after several requests to see your actual numbers.

### What I Did for Speed

1. **Async Memory Extraction**: The post-response LLM memory extraction call has been moved to FastAPI `BackgroundTasks`. The user gets their chat response immediately, while memory extraction and history saving run silently in the background (halving perceived latency!).
2. **Gemini Flash (not Pro)**: ~2-3x faster inference, sufficient quality for this task
3. **Selective semantic memory retrieval**: Only load the top 4 most relevant memories via embeddings, not everything.
4. **Concise system prompt**: ~500 tokens, not a novel — every token adds latency
5. **Single meal log per message**: One `log_meal` call bundles all items, not separate calls per food item
6. **Hardcoded nutrition table**: Avoids an external API call for common foods (~0ms vs ~200-500ms)

### What I Didn't Fix (and Why)

- **Streaming responses**: Given the nested LangGraph tool calls and React UI architecture, full SSE streaming adds significant fragility. The async background task update already reduced latency to ~1-2s, making streaming less critical for V1.
- **Vision + text are serial**: The image path requires two LLM calls in series. You could parallelize the vision call with context loading, but the text agent needs the vision output, so the calls are fundamentally sequential.
- **No response caching**: Repeated queries ("how am I doing?") hit the LLM every time. A short-lived cache for totals queries could save ~2s, but adds complexity.

---

## Assumptions and Trade-offs

| Decision | Rationale |
|----------|-----------|
| **SQLite** instead of Postgres | Sufficient for local, no-auth test task. No external dependency. We implemented semantic search using Python-based cosine similarity instead of pgvector to keep it lightweight. |
| **Daily totals via SUM query** (no materialized table) | Avoids dual-write consistency bugs — the exact class of bug where "totals break on a correction." Slight CPU cost per query, but correctness is guaranteed. |
| **Hardcoded nutrition table** (~50 foods) | PDF says "not evaluating your nutrition database." Gives consistent numbers for common foods; LLM estimates the rest. Trade-off: limited coverage. |
| **Single user (no auth)** | PDF says "no authentication required." `user_id` defaults to "default" everywhere. Multi-user support would use LangGraph config-based injection. |
| **Conversation history limit: 20 messages** | Prevents prompt bloat while maintaining multi-turn context. Trade-off: very long sessions lose early context. |
| **Gemini for both text and vision** | See [Model Choices](#model-choices-and-why) above. |

---

## Time Breakdown

| Phase | Time | What I Did |
|-------|------|-----------|
| Requirements analysis + planning | ~30 min | Read PDF, designed schema, graph, tool boundaries, memory mechanism |
| Database layer | ~30 min | SQLite schema, CRUD operations, context manager |
| Agent core | ~1.5 hr | LangGraph graph, nodes, tools, prompts, state |
| Vision pipeline | ~30 min | Gemini Vision integration, structured extraction, confidence handling |
| Memory system | ~45 min | Write path (LLM extraction), retrieve path (selective loading), upsert logic |
| FastAPI + React UI | ~45 min | HTTP endpoints, CORS, file upload, chat interface, Markdown rendering |
| Testing + eval | ~30 min | 15 unit tests, 11 eval cases, correction no-double-count proof |
| Latency + polish | ~30 min | Middleware, metrics endpoint, SDK migration |
| Advanced Features (Async, Semantic Search) | ~1 hr | Shifted memory to BackgroundTasks, built embedding-based cosine similarity search, added human mistake handling |
| README + documentation | ~30 min | This document |
| **Total** | **~7 hrs** | |

---

## Recently Shipped Advanced Features

In the final hours of the assignment, I knocked out several advanced "nice-to-have" features:

1. **Async Memory Extraction**: Shifted the 2nd LLM call to FastAPI `BackgroundTasks`, slashing response latency by ~50%.
2. **Semantic Memory Retrieval**: Replaced crude keyword category matching with real Semantic Search using Gemini's `text-embedding-004` and cosine similarity. "I told you about my allergy" now correctly surfaces "User is allergic to peanuts."
3. **Compound Meal Decomposition**: The agent's prompt was upgraded to rigorously decompose complex meals (e.g., "butter chicken and 2 naan") and query their macros individually before summing them, preventing hallucinated whole-dish estimates.
4. **Human Mistake & Redundancy Handling**: The agent is now trained to explicitly catch and challenge duplicate texts ("Ate an apple" x2) or typo quantities ("Ate 50 parathas") before polluting the database.
5. **LangSmith Tracing**: Wired up `.env.example` support for instant LangSmith graph tracing.
6. **UX Markdown Rendering**: Added `react-markdown` to the frontend so the agent's macro breakdowns display cleanly structured instead of raw asterisks.

---

## LangSmith Tracing

As requested in the task brief, here are public LangSmith traces demonstrating the agent's thought process, state graph traversal, and tool executions across different scenarios:

- [**Basic Logging (Add Meals)**](https://smith.langchain.com/public/87e028b4-b9ae-4ba7-ab48-d1a134e70d54/r/01a0661c-a70b-7ff0-a305-9ad6fb7061c3?start_time=2026-09-03T07%3A12%3A28.939625Z): Shows the agent processing a text request and calling tools to log a meal.
- [**Setting Memory**](https://smith.langchain.com/public/66f54d6d-bfb9-4bb0-b38d-664f68d15508/r/01a0661e-d403-7a71-be02-8693715e0c76?start_time=2026-09-03T07%3A14%3A51.523205Z): Demonstrates the background extraction process saving user facts into semantic memory.
- [**Recalling Past Memory**](https://smith.langchain.com/public/14ad6d07-44cd-4c78-9a8f-020d43e5bafc/r/01a0661f-a966-7933-b583-2e4e77b14f02?start_time=2026-09-03T07%3A15%3A46.14933Z): Shows the agent retrieving context from a previous session before executing its task.
- [**Multimodal Logging (Photo)**](https://smith.langchain.com/public/ed2110d3-b8ae-4fbe-823f-1a508a46bfd5/r/01a06620-b524-76e2-98e0-99aad7472573?start_time=2026-09-03T07%3A16%3A54.69193Z): Illustrates the vision pipeline extracting structured food data from an image and passing it to the text model.


<img width="2392" height="1446" alt="image" src="https://github.com/user-attachments/assets/c2145d84-8c40-42f3-a480-b380d3468490" />

---

## What I'd Fix or Build Next

With more time, in priority order:

1. **Streaming responses** — Currently the user waits for the full agent response. Streaming via SSE/WebSocket would make it feel like real messaging.
2. **Confidence-based confirmation flow** — When vision confidence is low, force an interactive UI confirmation step before logging (currently it's prompt-instructed, not graph-enforced).
3. **Postgres Migration** — Move off SQLite to a proper Postgres DB with `pgvector` native support.

---

## AI Tool Usage

This project was built with **Antigravity (Claude)** as a coding partner, as encouraged by the brief.

### How AI Helped

- **Architecture planning**: Discussed LangGraph graph structure, tool boundaries, and memory mechanism design
- **Code generation**: Generated boilerplate (FastAPI endpoints, Pydantic models, React components) that I reviewed and refined
- **Prompt engineering**: Iterated on system prompts for the agent, memory extraction, and vision modules
- **Test coverage**: Helped identify edge cases (the sub-second timestamp ordering bug in conversation history)
- **Documentation**: Structured the README sections and trade-off analysis

### What I Did Myself

- All architectural decisions (why LangGraph, why computed totals, why selective memory retrieval)
- Tool boundary design and the reasoning behind each split
- Identifying the three critical test cases and designing the correction flow
- Trade-off analysis (what to optimize, what to leave as documented debt)
- Review and validation of all generated code

The AI significantly increased implementation speed while I focused on design decisions and correctness — exactly the workflow the brief encourages.
