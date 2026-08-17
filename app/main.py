"""
FastAPI service wrapping the multiagent_support customer support platform.

Week 7 LLMOps — Provides /chat (SSE streaming), /health, /metrics, and /dashboard.
"""

import asyncio
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from multiagent_support.agents import get_agent

# Import from the existing multiagent_support package (unchanged)
from multiagent_support.classifier import classify_ticket

# Conditional HuggingFace imports
ENABLE_HF_MODELS = os.getenv("ENABLE_HF_MODELS", "false").lower() == "true"

if ENABLE_HF_MODELS:
    from multiagent_support.proactive import suggest_next_action
    from multiagent_support.sentiment import analyze_sentiment
else:
    def analyze_sentiment(text: str) -> str:
        """Stub: HF models disabled. Returns UNKNOWN."""
        return "UNKNOWN"

    def suggest_next_action(text: str) -> str:
        """Stub: HF models disabled."""
        return "N/A (HuggingFace models disabled)"

# Import our new LLMOps modules
from app.dashboard import render_dashboard
from app.guardrails import RateLimiter, check_content_filter, redact_pii
from app.logging_middleware import (
    get_hourly_stats,
    get_metrics,
    get_recent_requests,
    init_log_db,
    log_request,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
LOG_DB_PATH = os.getenv("LOG_DB_PATH", "data/logs.db")
RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "10"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))
STREAM_DELAY_MS = int(os.getenv("STREAM_DELAY_MS", "50"))

rate_limiter = RateLimiter(max_requests=RATE_LIMIT_MAX, window_seconds=RATE_LIMIT_WINDOW)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup."""
    init_log_db(LOG_DB_PATH)
    yield


app = FastAPI(
    title="Multi-Agent Customer Support — LLMOps API",
    description="Week 7: Observable, containerized API wrapping the existing agent pipeline.",
    version="0.7.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    customer_id: str = Field(..., description="Unique customer identifier")
    query: str = Field(..., description="Customer support query")
    thread_id: str | None = Field(
        default=None,
        description="Optional thread ID for conversation continuity",
    )


class HealthResponse(BaseModel):
    status: str
    version: str
    hf_models_enabled: bool


# ---------------------------------------------------------------------------
# POST /chat — SSE streaming
# ---------------------------------------------------------------------------
@app.post("/chat")
async def chat(request: ChatRequest):
    """
    Process a customer support query through the agent pipeline.

    Returns a Server-Sent Events stream that delivers the response
    word-by-word (simulated streaming — see ARCHITECTURE.md).
    """
    # --- Rate limiting ---
    if not rate_limiter.is_allowed(request.customer_id):
        retry_after = rate_limiter.get_retry_after(request.customer_id)
        return JSONResponse(
            status_code=429,
            content={
                "detail": (
                    f"Rate limit exceeded for customer '{request.customer_id}'. "
                    f"Max {RATE_LIMIT_MAX} requests per {RATE_LIMIT_WINDOW}s. "
                    f"Retry after {retry_after}s."
                ),
                "retry_after": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )

    # --- Input guardrails ---
    block_reason = check_content_filter(request.query)
    if block_reason:
        return JSONResponse(
            status_code=400,
            content={"detail": f"Request blocked: {block_reason}"},
        )

    # --- Agent pipeline (unchanged logic) ---
    start = time.perf_counter()

    thread_id = request.thread_id or str(uuid.uuid4())
    category = classify_ticket(request.query)
    agent = get_agent(category)
    agent_response = agent.respond(request.query)
    sentiment = analyze_sentiment(request.query)
    was_escalated = category == "escalation"
    status = "escalated" if was_escalated else "resolved"

    latency_ms = (time.perf_counter() - start) * 1000

    # --- Log (PII-redacted) ---
    log_request(
        db_path=LOG_DB_PATH,
        customer_id=request.customer_id,
        thread_id=thread_id,
        input_query=redact_pii(request.query),
        final_answer=redact_pii(agent_response),
        category=category,
        agent_name=agent.name,
        sentiment=sentiment,
        was_escalated=int(was_escalated),
        latency_ms=round(latency_ms, 2),
    )

    # --- SSE streaming (simulated word-by-word) ---
    async def generate_sse():
        # Send metadata event first
        import json

        metadata = {
            "thread_id": thread_id,
            "category": category,
            "agent": agent.name,
            "sentiment": sentiment,
            "status": status,
            "latency_ms": round(latency_ms, 2),
        }
        yield f"event: metadata\ndata: {json.dumps(metadata)}\n\n"

        # Stream response word by word
        words = agent_response.split()
        for i, word in enumerate(words):
            token = word if i == len(words) - 1 else word + " "
            yield f"data: {token}\n\n"
            await asyncio.sleep(STREAM_DELAY_MS / 1000)

        yield "event: done\ndata: [DONE]\n\n"

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Thread-ID": thread_id,
        },
    )


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------
@app.get("/health", response_model=HealthResponse)
async def health():
    """Basic liveness check."""
    return HealthResponse(
        status="ok",
        version="0.7.0",
        hf_models_enabled=ENABLE_HF_MODELS,
    )


# ---------------------------------------------------------------------------
# GET /metrics
# ---------------------------------------------------------------------------
@app.get("/metrics")
async def metrics():
    """Return aggregate statistics from the request log."""
    return get_metrics(LOG_DB_PATH)


# ---------------------------------------------------------------------------
# GET /dashboard
# ---------------------------------------------------------------------------
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Server-rendered observability dashboard."""
    m = get_metrics(LOG_DB_PATH)
    recent = get_recent_requests(LOG_DB_PATH, limit=10)
    hourly = get_hourly_stats(LOG_DB_PATH, hours=24)
    return render_dashboard(metrics=m, recent_requests=recent, hourly_stats=hourly)
