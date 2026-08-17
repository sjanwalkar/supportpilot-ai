"""
SupportPilot AI — Phase 3 (API) + Phase 4 (frontend) + Phase 7 (memory) +
Phase 8 (tools) + Phase 10 (guardrails)

No agent logic changes here beyond passing conversation_id through and
returning tool_calls/guardrail_triggered. This file adds:
  - POST /api/chat  — wraps agent.run_agent(), same function chat.py uses
  - GET  /health    — liveness check
  - GET  /          — serves static/index.html (the Phase 4 frontend)

The frontend is served from this same app (not a separate dev server) so
its fetch() calls to /api/chat are same-origin — no CORS setup needed.

Phase 7 note: HTTP requests are stateless, so the client (static/index.html)
holds the conversation_id after the first response and sends it back on
every following request. Without that, every message would look like a
brand-new conversation and follow-ups wouldn't work.

Run: uv run uvicorn api:app --reload
Then open: http://localhost:8000
"""

from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from agent import run_agent, MODEL, describe_exception

app = FastAPI(title="SupportPilot AI", version="0.1.0")

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/")
def index():
    """Serve the Phase 4 frontend."""
    return FileResponse(STATIC_DIR / "index.html")


class ChatRequest(BaseModel):
    message: str
    # None on a client's first message -- run_agent() creates a new
    # conversation in that case and returns its id in the response, so
    # the client can send it back on every message after that.
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    citations: List[str] = []
    tool_calls: List[dict] = []
    guardrail_triggered: Optional[str] = None
    conversation_id: str


@app.get("/health")
def health():
    """Liveness check — also useful to confirm which model is configured."""
    return {"status": "ok", "model": MODEL}


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="message must not be empty")

    try:
        state = run_agent(request.message, conversation_id=request.conversation_id)
    except SystemExit as e:
        # agent.get_client() raises SystemExit when GEMINI_API_KEY is
        # missing — that's the right call for a CLI script (Phase 1/2),
        # but SystemExit must never be allowed to propagate out of a
        # request handler in a long-running server, or it can take the
        # whole process down instead of just failing one request. We
        # catch it here and turn it into a normal HTTP error.
        raise HTTPException(status_code=500, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gemini call failed: {describe_exception(e)}") from e

    return ChatResponse(
        answer=state.response,
        citations=state.citations,
        tool_calls=state.tool_calls,
        guardrail_triggered=state.guardrail_triggered,
        conversation_id=state.conversation_id,
    )
