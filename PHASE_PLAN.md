# SupportPilot AI — Phase Plan

A customer support chatbot, built up one small phase at a time.
LLM: **Gemini** (via the `google-genai` SDK). Stack starts as plain Python
scripts — no web framework, no React — and only grows a piece at a time,
once the piece before it is understood and working.

Dataset (starting Phase 5): **Bitext Customer Support LLM Chatbot Training
Dataset** (Hugging Face: `bitext/Bitext-customer-support-llm-chatbot-training-dataset`).
~26.9k question/answer pairs across 27 support intents (Reset Password, Check
Order Status, Cancel Subscription, etc.), grouped into categories like
Billing, Technical Issues, and Account Management. It's a clean fit because
it doubles as your RAG knowledge base *and* your eval golden set later
(the intent labels become your "expected intent" answer key).

Rule for every phase: it only adds the thing named in its goal. Nothing is
pre-built early "to save time later."

---

### Phase 1 — Plain Gemini Chat (CLI) ✅ done
Goal: prove the absolute basic loop works.
- One script, one function, one Gemini call.
- Terminal input/output loop.
- No state object, no RAG, no memory, no UI, no tests.

### Phase 2 — Agent State ✅ done
Goal: make the flow visible and debuggable before adding anything else.
- Introduce a small state object: `message -> prompt -> llm_answer -> response`.
- Add a short system prompt / persona for the support bot.
- Add tests that check prompt construction — without calling Gemini.
- Implemented in `agent.py` (state + prompt building + LLM call) and
  `test_agent.py` (prompt-construction tests, no API key needed).

### Phase 3 — Wrap It as an API ✅ done
Goal: turn the working script into something other things (a UI, later
phases) can call.
- FastAPI app, one route: `POST /api/chat`.
- Reuses the Phase 2 agent function as-is — no logic changes.
- Test with `curl`, no frontend yet.
- Implemented in `api.py`. `agent.py` was not touched.

### Phase 4 — Minimal Frontend ✅ done
Goal: a human can use it without a terminal.
- One plain HTML file with a `<script>` tag calling `fetch()` — no React,
  no build step, no npm.
- Talks to the Phase 3 API.
- Implemented in `static/index.html`, served by a new `GET /` route in
  `api.py` (same-origin, so no CORS config needed). `agent.py` untouched.

### Phase 5 — Local Knowledge Base (RAG v1) ✅ done
Goal: answers grounded in real support content, no vector DB yet.
- `data/kb/*.md` — 7 original help-center-style articles for a fictional
  company ("Northwind"), covering account, orders, shipping, payments,
  refunds, newsletter, and contacting support.
- `kb.py` — loads the markdown files and does simple keyword-overlap
  search (`search_kb()`), no embeddings.
- `agent.py` — `run_agent()` now retrieves KB docs before building the
  prompt; `build_prompt()` includes them as context and asks Gemini to
  cite article ids. `AgentState` gains `retrieved_docs`/`citations`.
- Citations flow through everywhere: CLI prints "Sources: ...", the API
  response includes a `citations` list, the frontend shows them under
  the bot's reply.
- `test_kb.py` — retrieval tests, no API key or network needed.

Note: I don't have real network access to pull the actual Bitext dataset
in this environment, so the KB is original content covering the same
categories (account, orders, shipping, payments, refunds, newsletter,
contact) rather than a reproduction of Bitext's Q&A pairs. That's
arguably more realistic anyway — a production KB is policy docs, not
training data.

### Phase 6 — Pinecone Vector Search (RAG v2) ✅ done
Goal: replace keyword search with real semantic search.
- `vector_search.py` — embeds text with Gemini (`gemini-embedding-001`)
  and queries Pinecone for the closest KB doc vectors. Exposes
  `search_kb()` with the exact same signature/return type as Phase 5's
  keyword version.
- `ingest_kb.py` — standalone script: embeds every `data/kb/*.md` file
  and upserts it into Pinecone. Creates the index on first run. Not part
  of the request path — the chat app only ever queries Pinecone.
- `agent.py` — **only the import line changed** (`from kb import search_kb`
  → `from vector_search import search_kb`). Everything else — state,
  prompt building, citations — is untouched.
- `test_vector_search.py` — tests the pure metadata↔KBDoc conversion.
  Embedding/Pinecone calls themselves aren't unit tested (they need real
  credentials and a live index) — that's what running the app is for.

### Phase 7 — Memory ✅ done
Goal: support follow-up questions.
- `memory.py` — SQLite (`data/supportpilot.db`), `conversations` and
  `messages` tables, `create_conversation()`, `add_message()`,
  `get_recent_messages()` (last 6 messages, verbatim, no summarization).
- `agent.py` — `run_agent()` now takes a `conversation_id`. Pulls recent
  history before answering, saves both the question and the answer after.
  `build_prompt()` gained a `history` block — with no history (or no
  docs), output is byte-for-byte identical to Phase 2, verified by the
  existing tests passing unmodified.
- `chat.py` — creates one conversation per CLI session, passes it on
  every turn.
- `api.py` — `ChatRequest`/`ChatResponse` gained `conversation_id`, since
  HTTP is stateless and the client has to carry it across requests.
- `static/index.html` — stores `conversation_id` after the first reply,
  sends it back on every message; added a "New chat" button to reset it.
- `test_memory.py` — 4 tests against a temp SQLite file, no API key or
  network needed (these actually run for real, not stubbed, since
  sqlite3 is a standard library module).

### Phase 8 — Tools ✅ done
Goal: let the agent do things, not just answer.
- `crm.py` — plain Python functions: `get_customer_profile`,
  `check_feature_access`, `create_support_ticket`. Type-hinted with
  Google-style docstrings, passed to Gemini as `tools=[...]` — the
  google-genai SDK's automatic function calling handles deciding when to
  call them, executing them, and feeding results back to the model.
- `seed_crm.py` — 15 hand-authored fake customers + 20 orders (decision
  from our earlier discussion: no external dataset for this — plan
  entitlement rules are inherently invented for a fictional company, and
  a small readable seed keeps this phase about tool-calling, not data
  wrangling).
- `agent.py` — `call_llm()` now passes `crm.TOOLS` and returns
  `(text, tool_calls)` instead of just text. New `extract_tool_calls()`
  turns the SDK's `automatic_function_calling_history` into plain
  `{name, args, result}` dicts, stored on `AgentState.tool_calls`.
- Tool usage surfaces everywhere citations already did: CLI prints
  "Tools used: ...", API response includes `tool_calls`, frontend shows
  it under the bot's reply.
- `test_crm.py` — 8 tests against a temp DB, no API key or network
  needed. `test_agent.py` gained `extract_tool_calls()` tests using
  plain duck-typed fakes (no SDK import needed for the test itself).
- Tickets are stored in the same SQLite file as Phase 7 (`data/supportpilot.db`),
  in their own `tickets` table.

### Phase 9 — MCP ⚠️ built, not live (see status note)
Goal: expose the same tools over MCP instead of calling them as plain functions.
- `mcp_server.py` — local MCP server (stdio transport). Registers the
  exact same function objects from `crm.py` as MCP tools — no
  reimplementation. Point MCP Inspector at it to browse/call the tools
  directly, no Gemini involved: `npx @modelcontextprotocol/inspector uv
  run python mcp_server.py` (requires Node.js).
- `mcp_client.py` — the MCP client. Spawns `mcp_server.py` as a
  subprocess and does a real MCP handshake — **proven working** via
  `mcp_diagnostic.py`, which connects, lists all three tools, and
  successfully calls `get_customer_profile` over the real protocol.
- `mcp_diagnostic.py` — standalone script that exercises the MCP
  connection with no Gemini involved, used to isolate exactly where a
  failure is (protocol layer vs. the Gemini/MCP glue).
- `test_mcp_server.py` — confirms `mcp_server.py` wraps the *same*
  function objects from `crm.py` (identity checks), satisfying "plain
  Python tool functions remain testable."

**Status: `run_agent()` uses Phase 8's `call_llm()` (direct `tools=TOOLS`),
not MCP, for the live chat.** We built `call_llm_via_mcp()` — a
synchronous wrapper that calls Gemini with `tools=[mcp_session]` — and
verified the MCP connection itself is solid. But `google-genai`'s support
for passing a live MCP session this way is explicitly documented as
experimental, and it currently fails with
`TypeError: cannot pickle '_asyncio.Future' object` — confirmed to be a
bug in the SDK's session-handling, not our code (our usage matches
Google's own documented example exactly). Rather than write a manual
tool-calling loop to route around an experimental, still-settling SDK
feature, we're keeping the live path on the proven Phase 8 approach.
`call_llm_via_mcp()` stays in `agent.py`, ready to flip `run_agent()`
back onto once the SDK matures — see agent.py's module docstring.

This satisfies "MCP Inspector can see the tools" and "plain Python tool
functions remain testable" fully. "Backend can call tools through MCP"
is proven true at the protocol level (`mcp_diagnostic.py`), just not
wired into the live chat today.

Known simplification (for whenever the live path is flipped back on):
each turn would spawn a fresh server subprocess and tear it down —
simple and correct, not efficient. A persistent MCP connection is a
Phase 13 concern, not something to solve here.

### Phase 10 — Guardrails ✅ done
Goal: stop unsafe or made-up answers.
- `guardrails.py` — three plain, keyword/pattern-based rules (no ML
  classifier), in the same spirit as Phase 5's keyword search:
  1. **Sensitive request → escalate before Gemini is even called.**
     `is_sensitive_request()` checks for specific multi-word phrases
     (account deletion, fraud, security compromise, legal threats).
     If a customer id is found in the message, a real ticket is opened
     immediately (`crm.create_support_ticket()`); if not, the bot asks
     for one rather than guessing.
  2. **KB answers must cite what they used.** If `search_kb()` returned
     docs but Gemini's answer doesn't reference any of their `[doc_id]`
     citations, the answer is replaced with an honest "I don't know."
  3. **No unsupported commitments.** If the answer contains phrases like
     "I guarantee" or "legally binding," it's replaced with a safer
     fallback.
- `agent.py` — `run_agent()` calls `check_sensitive_request()` *before*
  building a prompt or calling Gemini at all (can skip the LLM call
  entirely), and `check_response()` *after* Gemini answers, before the
  customer sees it. `AgentState` gained `guardrail_triggered` (None, or
  which rule fired) for the same transparency `citations`/`tool_calls`
  already have.
- Surfaced everywhere those already were: CLI prints `[Guardrail: ...]`,
  API response includes `guardrail_triggered`, frontend shows it in an
  accent-colored note under the bot's reply.
- `test_guardrails.py` — 19 tests, all pure logic or real SQLite against
  a temp DB (same pattern as `test_crm.py`/`test_memory.py`). No API key
  or network needed. Verified manually too: a stubbed ungrounded answer
  really does get replaced before reaching `state.response`, and a
  sensitive request with a customer id really does create a ticket and
  skip Gemini entirely (`state.prompt`/`state.llm_answer` stay `None`).

Known, stated trade-off: rule #2 can occasionally reject a correct
answer that just forgot its citation bracket — a formatting slip, not a
substance problem. Accepted deliberately: for this app, occasionally
being overly cautious is a better failure mode than ever showing an
ungrounded claim as if it were verified. Also worth knowing: the
citation rule only applies when the KB actually returned candidate docs
— an off-KB question (small talk, "what can you help with") is not
forced through this check, since a blanket "always cite or refuse" rule
would break ordinary conversation.

**Bug found during live testing, fixed:** a follow-up message that was
just a bare customer id (e.g. "CUST-002", given in reply to the bot
asking for one) correctly triggered `create_support_ticket` via memory +
tools — but the citation guardrail then wrongly overrode that *correct*
response. Root cause was two compounding issues:
1. `vector_search.search_kb()` had no relevance floor — Pinecone always
   returns its `top_k` nearest neighbors no matter how irrelevant, so a
   near-meaningless query like a bare customer id still came back with
   "closest available" docs. Fixed by adding `MIN_RELEVANCE_SCORE = 0.5`
   in `vector_search.py` (a starting heuristic, not empirically tuned).
2. `check_response()` didn't know the difference between "an uncited
   factual claim" and "a report that a tool already ran" — a ticket
   confirmation isn't a KB claim and was never supposed to need a
   citation. Fixed by passing `tool_calls` into `check_response()` and
   skipping the citation check whenever a tool was used.
Both fixes are covered by new tests in `test_guardrails.py`, and
verified end-to-end by reproducing the exact scenario against a stub.

**Two more bugs found in the same live-testing session, both fixed:**
1. `"thank you."` alone still returned KB matches even above the new
   0.5 relevance floor — confirming a numeric threshold alone isn't
   reliable when the whole KB is topically narrow (everything is
   "customer support"-adjacent). Fixed with a deterministic backstop:
   `guardrails.is_smalltalk()` skips KB retrieval entirely for
   greetings/thanks/acknowledgments, checked with exact-phrase matching
   at first.
2. That exact-phrase version then broke on `"ok, Thankyou."` — a
   compound, unspaced, comma-joined variant no fixed phrase list can
   fully enumerate. Replaced with word-level matching instead: a message
   counts as small talk when *every* word in it (after stripping
   punctuation) belongs to a narrow greeting/thanks/closing vocabulary —
   this generalizes to any spacing/punctuation/combination automatically,
   rather than needing each variant added by hand. Deliberately excludes
   common filler words ("i", "a", "the", "is", "do", ...), which is what
   keeps real questions from accidentally matching, since they almost
   always contain at least one word outside the vocabulary.
3. `check_sensitive_request()` also gained conversation-history lookup
   (`find_customer_id()`) — a customer id given earlier in the chat is
   now found automatically on a later sensitive message, instead of
   being asked for again.
Covered by 15 additional tests in `test_guardrails.py` (34 total for
this phase), including specific regression tests for both the exact
reported inputs and adjacent real-question phrasings that must NOT match.

### Phase 11 — Evals ✅ done
Goal: measure quality instead of eyeballing it.
- `data/eval/golden_questions.json` — 17 hand-authored questions (not
  Bitext-derived — same reasoning as Phase 5/8: no live network access
  to pull the real dataset, and hand-authored questions tied to our
  actual 7 KB articles/2 tools/guardrails are more directly useful than
  a generic set anyway). Covers all 7 KB articles, both tools, sensitive
  escalation (with/without a customer id, and a natural-language fraud
  phrasing), two guardrail-negative cases (the exact "stolen package"
  false-positive guardrails.py was built to avoid), and three small-talk
  cases — including the literal `"ok, Thankyou."` regression from
  Phase 10's live debugging.
- `evals.py` — pure scoring logic (`score_question()`, `summarize()`).
  Reads only `state.citations`/`tool_calls`/`guardrail_triggered` — the
  same AgentState fields every earlier phase already exposes. No network
  calls, fully unit-testable.
- `run_evals.py` — the actual command: `uv run python run_evals.py`.
  Runs every golden question through the REAL `agent.run_agent()` (real
  Gemini + Pinecone calls, needs both API keys) and prints a scorecard.
- Five metrics: citation presence, source hit (replaces "intent
  accuracy" — see evals.py's docstring for why), tool-call correctness,
  escalation correctness (two-sided: catches both under- and
  over-triggering), and no-guardrail-fired (direct regression check for
  the small-talk bugs found this session).
- `test_evals.py` — 14 tests for the scoring logic, using a plain
  `SimpleNamespace` stand-in for AgentState. No API key or network
  needed — and unlike other test files, doesn't even need agent.py's
  import chain stubbed, since it never imports agent.py at all.
- Verified the full pipeline end-to-end (load → run → score → scorecard)
  against a stubbed `run_agent()` simulating both correct and incorrect
  answers — confirmed it correctly flags failures with specific notes
  and computes accurate per-metric rates.

Known side effect, stated plainly: escalation questions with a customer
id create a real ticket row each run — same as an actual user would.
Harmless noise in `data/supportpilot.db`; a production eval suite would
likely use a separate database for this. Not solved here, consistent
with every other "keep it simple" tradeoff already in this project.

### Phase 12 — Docker & Deployment ✅ done
Goal: reproducible setup.
- **Adapted from the original plan:** one `Dockerfile`, not separate
  backend/frontend ones. Phase 4 already merged the frontend into the
  FastAPI process (`GET /` serves `static/index.html`) specifically to
  avoid CORS, so there's only one real service to containerize — see
  `Dockerfile`'s comments for the full reasoning.
- `Dockerfile` — uses `uv` inside the container too, consistent with
  local dev. Two-step `uv sync` (deps first, then code) for fast
  rebuilds, following Astral's own documented caching pattern.
- `.dockerignore` — excludes `.venv`, `.env` (secrets never get baked
  into the image), and the local dev `data/supportpilot.db` (the
  container should start clean or use a mounted volume, not ship stale
  local test data).
- `docker-compose.yml` — one service, `env_file: .env`, and a bind mount
  of `./data` so KB edits and the SQLite DB both persist across
  `docker compose down`/`up` cycles locally.
- `DEPLOYMENT.md` — full guide: local Docker Compose usage, plus a
  step-by-step Google Cloud Run deployment (chosen because it's the best
  fit for a single container on GCP's free tier: genuinely ongoing
  "Always Free" allowance, not a time-limited trial, scales to zero, no
  VM to manage).

**Important, stated plainly:** Cloud Run's container filesystem is
ephemeral — local SQLite writes don't survive a restart/scale-to-zero.
Cloud Run's persistent-volume option (Cloud Storage FUSE) explicitly has
no file-locking ("last write wins, previous writes are lost" per
Google's own docs), which is a real corruption risk for a SQLite file
under concurrent access — not something to paper over with a volume
mount. `DEPLOYMENT.md` recommends deploying without solving this:
conversations/tickets reset on restart, which is a fine tradeoff for a
demo/learning deployment, and flags a real managed database (Cloud SQL)
as the correct fix if this app ever needs to keep data past a demo —
explicitly out of scope for this phase, not solved here.

### Phase 13 — Final Modularization
Goal: clean up, now that the whole path works end to end.
- Split into modules: `agent`, `llm`, `rag`, `memory`, `tools`, `mcp`,
  `evals`, `guardrails`.
- Done last on purpose, so the project stays readable while you're
  still learning it.

---

## Why Phase 1 is split into three phases (1, 3, 4) instead of one

Your reference README bundled "React UI → FastAPI → Gemini" into a single
Phase 1. Here it's spread across three phases — plain script, then API,
then UI — so each phase changes exactly one thing and a bug can only be
in the part you just touched.

---

## Current State

Implemented now:
- Phase 1: plain Gemini CLI chat.
- Phase 2: explicit agent state (`agent.py`), prompt-construction tests
  (`test_agent.py`).
- Phase 3: FastAPI wrapper (`api.py`) — `POST /api/chat`, `GET /health`.
  Reuses `agent.run_agent()` unchanged.
- Phase 4: plain HTML/JS frontend (`static/index.html`), served same-origin
  from `api.py` at `GET /`.
- Phase 5: local KB (`data/kb/*.md`) + keyword search (`kb.py`). Kept in
  place as a reference/fallback implementation, no longer used by agent.py.
- Phase 6: Pinecone vector search (`vector_search.py`, `ingest_kb.py`).
  `agent.py` now retrieves via Pinecone instead of keyword overlap — one
  import line changed, nothing else.
- Phase 7: SQLite memory (`memory.py`). `run_agent()` now takes a
  `conversation_id`; chat.py/api.py/frontend all carry it across turns.
- Phase 8: tools (`crm.py`, `seed_crm.py`). Gemini can call
  `get_customer_profile`, `check_feature_access`, `create_support_ticket`
  via automatic function calling. `AgentState.tool_calls` tracks what
  was used, surfaced in CLI/API/frontend.
- Phase 9: MCP built and protocol-proven (`mcp_server.py`, `mcp_client.py`,
  `mcp_diagnostic.py`). **Not the live path** — `run_agent()` still uses
  Phase 8's direct `call_llm()`, due to an experimental google-genai SDK
  bug when passing a live MCP session. See Phase 9's section above for
  the full story.
- Phase 10: guardrails (`guardrails.py`). Sensitive requests escalate
  before Gemini is called; KB answers without a citation, and answers
  with unsupported commitments, get replaced after Gemini answers.
  `AgentState.guardrail_triggered` surfaced in CLI/API/frontend.
- Phase 11: evals (`evals.py`, `run_evals.py`, `data/eval/golden_questions.json`).
  17 golden questions, 5 metrics, one command (`uv run python
  run_evals.py`) prints a scorecard against the real, live system.
- Phase 12: Docker (`Dockerfile`, `docker-compose.yml`) + deployment
  (`DEPLOYMENT.md`, covering local Docker Compose and a step-by-step
  Google Cloud Run guide). One image, not separate frontend/backend —
  matches the Phase 4 architecture. Persistence tradeoff on Cloud Run
  stated plainly, not solved.

Not implemented yet:
- Modularization (Phase 13).

Project structure is intentionally flat — one evolving codebase, no
per-phase folders. Files grow in place as each phase is added.
