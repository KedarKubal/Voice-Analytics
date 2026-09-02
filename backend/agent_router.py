"""
agent_router.py  —  Heya AI Voice Analytics
FastAPI router for the ReAct agentic analysis engine.

Endpoints
---------
  POST /agent/analyze/{client_id}   Run agentic analysis on a question
  GET  /agent/tools                 List available tools and their parameters
"""

import time
import threading
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from auth import CurrentUser, get_current_user

router = APIRouter(prefix="/agent", tags=["agent"])


# ═══════════════════════════════════════════════════════════════════════════════
# RATE LIMITING  (shared with main.py pattern — in-memory per user)
# ═══════════════════════════════════════════════════════════════════════════════
_rate_store: dict[str, list[float]] = defaultdict(list)
_rate_lock  = threading.Lock()

def _check_rate_limit(key: str, limit: int = 10, window: int = 60) -> None:
    """Raise 429 if the key has exceeded `limit` requests in `window` seconds."""
    now = time.time()
    with _rate_lock:
        _rate_store[key] = [t for t in _rate_store[key] if now - t < window]
        if len(_rate_store[key]) >= limit:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded — max {limit} agent requests per {window}s.",
            )
        _rate_store[key].append(now)


# ═══════════════════════════════════════════════════════════════════════════════
# SECURITY HELPER
# ═══════════════════════════════════════════════════════════════════════════════
def _require_client_access(user: CurrentUser, client_id: str) -> None:
    if user.is_admin:
        return
    if user.client_id != client_id:
        raise HTTPException(
            status_code=403,
            detail="Access denied — your token does not grant access to this client's data.",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# REQUEST / RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════════════════════
class AgentAnalysisRequest(BaseModel):
    question: str
    mode: str = "auto"    # reserved for future: "quick" | "deep" | "auto"


class ReasoningStep(BaseModel):
    iteration:   int
    thought:     str | None = None
    tool:        str | None = None
    params:      dict | None = None
    observation: str | None = None


class AgentAnalysisResponse(BaseModel):
    question:        str
    answer:          str
    reasoning_steps: list[ReasoningStep]
    tools_used:      list[str]
    sources:         list[str]
    confidence:      str
    iterations:      int
    response_ms:     int


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════════════════════
@router.post("/analyze/{client_id}", response_model=AgentAnalysisResponse)
def agent_analyze(
    client_id: str,
    req:       AgentAnalysisRequest,
    request:   Request,
    user:      CurrentUser = Depends(get_current_user),
):
    """
    Run the ReAct agentic analysis engine on a question.

    The agent breaks down complex analytical questions into tool calls,
    executes them against the database, and synthesises a grounded answer.

    Each response includes:
      answer          — the final synthesised answer
      reasoning_steps — the agent's thought process and tool results
      tools_used      — which tools were called (sql_analytics, agent_performance, …)
      confidence      — HIGH (all data from verified DB queries)
      iterations      — how many ReAct iterations were used (max 3)
    """
    _require_client_access(user, client_id)

    # Agent calls are heavier than RAG — tighter rate limit (10/min per user)
    _check_rate_limit(f"agent:{user.user_id}", limit=10, window=60)

    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    if len(question) > 1000:
        raise HTTPException(status_code=400, detail="Question too long — max 1000 characters.")

    t0 = time.time()

    try:
        from agent import analyze
        result = analyze(question, client_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {e}")

    response_ms = int((time.time() - t0) * 1000)

    # Coerce reasoning_steps into Pydantic models (agent.py returns plain dicts)
    steps = [
        ReasoningStep(
            iteration   = s.get("iteration", 0),
            thought     = s.get("thought"),
            tool        = s.get("tool"),
            params      = s.get("params"),
            observation = s.get("observation"),
        )
        for s in result.get("reasoning_steps", [])
    ]

    try:
        from database import get_db, RAGQueryHistory
        from datetime import datetime
        with get_db() as db:
            db.add(RAGQueryHistory(
                client_id        = client_id,
                user_id          = user.user_id,
                query            = question,
                response         = result.get("answer", ""),
                sources          = result.get("sources", []),
                query_type       = "agent_react",
                response_time_ms = response_ms,
                created_at       = datetime.utcnow(),
            ))
    except Exception:
        pass

    return AgentAnalysisResponse(
        question        = question,
        answer          = result.get("answer", ""),
        reasoning_steps = steps,
        tools_used      = result.get("tools_used", []),
        sources         = result.get("sources", []),
        confidence      = result.get("confidence", "HIGH"),
        iterations      = result.get("iterations", 0),
        response_ms     = response_ms,
    )


@router.get("/tools")
def list_tools():
    """
    Returns the list of tools available to the agent with their descriptions
    and parameter schemas. Useful for the frontend to display tool info.
    """
    return {
        "tools": [
            {
                "name":        "sql_analytics",
                "description": "Run verified SQL analytics queries against call data.",
                "params": {
                    "metric": (
                        "overview | flow_breakdown | sentiment_breakdown | "
                        "peak_hours | topic_breakdown | engagement_trends | silence_interruption"
                    )
                },
            },
            {
                "name":        "agent_performance",
                "description": "Get detailed performance metrics for an AI agent using the agents × calls × audio_insights join.",
                "params": {
                    "persona_name": "agent persona name for this client | all"
                },
            },
            {
                "name":        "semantic_search",
                "description": "Search call records and agent profiles using natural language (pgvector).",
                "params": {
                    "query": "natural language search string"
                },
            },
            {
                "name":        "topic_agent_breakdown",
                "description": "Show each agent's performance broken down by call topic.",
                "params":      {},
            },
        ]
    }
