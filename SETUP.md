# SupportPilot AI — Full Setup & Reference

[← Back to README](README.md)

Detailed setup, per-feature run instructions, and the full file
reference. For the short version, the phase-by-phase build story, and
the architecture diagram, see [README.md](README.md). For the
phase-by-phase roadmap and what was adapted along the way, see
`PHASE_PLAN.md`.

**Current phase: Phase 12 (Docker & Deployment)** — see the "Current
State" section in `PHASE_PLAN.md` for the full story (including Phase
9's MCP status), and `DEPLOYMENT.md` for local Docker + Cloud Run setup.

## Setup (uv — recommended)

```bash
uv python install 3.12   # uv fetches its own interpreter, no Homebrew needed
uv sync                  # installs main deps + dev deps (pytest), creates .venv
cp .env.example .env
```

Open `.env` and paste your Gemini API key in place of `your-key-here`. Get
one at https://aistudio.google.com/apikey if you don't have one yet.

Also add a Pinecone API key (needed starting Phase 6) — get a free one at
https://app.pinecone.io, then paste it in as `PINECONE_API_KEY`.

## Load the knowledge base into Pinecone (Phase 6, run once)

```bash
uv run python ingest_kb.py
```

This creates the Pinecone index (if it doesn't exist yet) and embeds +
uploads every article in `data/kb/`. Re-run it any time you add or edit a
KB file. You only need to do this once before chatting — the chat app
itself only ever queries Pinecone, never writes to it.

## Load fake customer data (Phase 8, run once)

```bash
uv run python seed_crm.py
```

Loads 15 hand-authored fake customers (and their orders) so the bot can
actually look someone up. Re-run any time to reset back to this known
set — it clears and reloads customers/orders, but leaves any support
tickets you've created alone. Try asking the bot something like "look up
account CUST-003 and tell me if they have API access" once this is done.

## Browse the tools with MCP Inspector (Phase 9, optional)

Requires Node.js. With nothing else running:

```bash
npx @modelcontextprotocol/inspector uv run python mcp_server.py
```

Open the local URL it prints — you'll see all three tools
(`get_customer_profile`, `check_feature_access`, `create_support_ticket`)
and can call them directly with test arguments, no Gemini involved. This
is the quickest way to confirm the MCP server itself is working before
worrying about whether Gemini is using it correctly.

## Run the chat (CLI)

```bash
uv run chat.py
```

Type a question, type `exit` or `quit` to stop. Try a follow-up in the
same session — e.g. "what's your refund policy?" then "what about for
perishable goods?" — the second answer should use the first as context.
Each `chat.py` run is its own conversation; start a new run for a fresh one.

To see the Phase 10 guardrails fire: try "CUST-002 here, someone accessed
my account without my permission" (should escalate immediately, no
Gemini call, and open a real ticket) versus just "someone accessed my
account" (should ask for your customer id instead of guessing).

## Run the API

```bash
uv run uvicorn api:app --reload
```

Test it:

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"How do I reset my password?"}'
```

Expected response:

```json
{
  "answer": "..."
}
```

There's also interactive docs at http://localhost:8000/docs — useful for
trying requests without curl. `GET /health` returns `{"status": "ok", "model": "..."}`,
handy for checking which Gemini model is configured.

## Use the frontend

With the API running (`uv run uvicorn api:app --reload`), just open:

```
http://localhost:8000
```

That's it — no separate server, no `npm install`, no build step. The page
at `static/index.html` is served directly by the FastAPI app and calls
`/api/chat` on the same origin, so there's no CORS setup needed either.

## Run with Docker (Phase 12)

```bash
docker compose up --build
```

Same app, containerized — see `DEPLOYMENT.md` for the full walkthrough,
including a step-by-step guide to deploying this to Google Cloud Run for
free.

## Run the evals (Phase 11)

```bash
uv run python run_evals.py
```

Unlike `uv run pytest`, this makes REAL Gemini + Pinecone calls for all
17 golden questions in `data/eval/golden_questions.json` — it needs both
API keys in `.env`, and costs whatever those calls cost. That's the
point: it's checking the live system, not a stubbed one. Prints a
pass/fail line per question plus a scorecard with 5 metrics (citation
presence, source hit, tool-call correctness, escalation correctness,
no-guardrail-fired). Re-run it after any change to `agent.py`,
`guardrails.py`, `data/kb/*.md`, or the retrieval pipeline to see
whether anything regressed.

## Run the tests

```bash
uv run pytest
```

These test prompt construction in `agent.py` only — no API key needed, no
network call made.

## Setup (pip/venv — alternative)

Only if you're not using `uv`. Needs Python 3.10+ already installed.

```bash
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Run with `python chat.py`, test with `pytest`.

## Files

| File | What it is |
|---|---|
| `agent.py` | Agent state (`conversation_id -> guardrail check -> history -> retrieved docs -> prompt -> llm_answer/tool_calls -> guardrail check -> response`), prompt building, the Gemini call (`call_llm()`, direct — see Phase 9 status note for why not MCP). |
| `memory.py` | SQLite conversation memory — `conversations`/`messages` tables, recent-history lookup. |
| `crm.py` | Customer/order/ticket tables + the three tool functions. Single source of truth — `mcp_server.py` wraps these, doesn't reimplement them. |
| `seed_crm.py` | Script — loads 15 hand-authored fake customers + orders. Run once. |
| `guardrails.py` | Phase 10: sensitive-request escalation, citation enforcement, unsupported-commitment check. |
| `evals.py` | Phase 11: pure eval scoring logic (`score_question()`, `summarize()`). |
| `run_evals.py` | Phase 11: the eval command — runs golden questions through the real agent, prints a scorecard. |
| `data/eval/golden_questions.json` | 17 hand-authored eval questions covering the full KB, both tools, escalation, and small-talk regressions. |
| `mcp_server.py` | Phase 9: local MCP server exposing `crm.py`'s tools. Try it with MCP Inspector. |
| `mcp_client.py` | Phase 9: async MCP client — proven working (`mcp_diagnostic.py`), not currently the live path (see Phase 9 status note). |
| `mcp_diagnostic.py` | Standalone script proving the MCP connection works, independent of Gemini. |
| `kb.py` | Loads `data/kb/*.md`. Also has the original Phase 5 keyword search (kept as reference, no longer used). |
| `vector_search.py` | Phase 6: Gemini embeddings + Pinecone query. This is what `agent.py` actually uses now. |
| `ingest_kb.py` | Script — embeds KB articles and upserts them into Pinecone. Run once, and after editing `data/kb/`. |
| `data/kb/*.md` | The knowledge base — 7 help-center-style articles. |
| `chat.py` | Terminal loop — one conversation per session, passed to `agent.run_agent()` every turn. |
| `api.py` | FastAPI app — `POST /api/chat` (takes/returns `conversation_id`, returns `tool_calls`/`guardrail_triggered`), `GET /health`, `GET /` (serves the frontend). |
| `static/index.html` | Plain HTML/CSS/JS chat UI. Tracks `conversation_id`, shows tool usage/sources/guardrail notes, has a "New chat" button. No build step, no npm. |
| `test_agent.py` | Tests for prompt construction and tool-call extraction. No API key or network needed. |
| `test_kb.py` | Tests for KB loading and keyword search. No API key or network needed. |
| `test_vector_search.py` | Tests for the metadata↔KBDoc conversion. No API key or network needed. |
| `test_memory.py` | Tests for SQLite memory, against a temp DB file. No API key or network needed. |
| `test_crm.py` | Tests for the CRM tool functions, against a temp DB file. No API key or network needed. |
| `test_mcp_server.py` | Confirms the MCP server wraps the same `crm.py` functions unchanged. No API key or network needed. |
| `test_guardrails.py` | Tests for all three guardrail rules. No API key or network needed. |
| `test_evals.py` | Tests for eval scoring logic. No API key or network needed. |
| `PHASE_PLAN.md` | Full phase-by-phase roadmap. |
| `Dockerfile` | Phase 12: single image for the whole app (API + frontend, one FastAPI process). |
| `docker-compose.yml` | Phase 12: local reproducible run — `docker compose up --build`. |
| `DEPLOYMENT.md` | Phase 12: local Docker usage + step-by-step Google Cloud Run deployment guide. |
