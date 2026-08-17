"""
SupportPilot AI — Phase 2 (Agent State) + Phase 6 (Vector Search) +
Phase 7 (Memory) + Phase 8 (Tools) + Phase 9 (MCP, built but not live) +
Phase 10 (Guardrails)

The flow is now:

    conversation_id -> get_recent_messages() -> history
    message -> [guardrail: sensitive request? escalate, skip Gemini]
             -> search_kb(message) -> retrieved docs   [Pinecone]
             -> prompt (system + history + KB context + question)
             -> llm_answer + tool_calls   [Gemini, tools=TOOLS directly]
             -> [guardrails: citation required? unsupported commitment?]
             -> response
             -> save this turn to SQLite

Only run_agent() (and the call_llm()/search_kb()/memory/guardrail
functions it uses) touches the network or disk. build_prompt() stays a
pure function — same inputs, same output, no I/O — so it's still
testable without any API keys. That's what test_agent.py checks.

WHAT CHANGED THIS PHASE: run_agent() now calls guardrails.py's
check_sensitive_request() before Gemini (can skip the LLM call entirely)
and check_response() after Gemini (can override the answer). See
guardrails.py's module docstring for the three specific rules and why
each one is checked where it is.

STATUS NOTE (Phase 9): run_agent() calls call_llm() — Phase 8's direct
tools=TOOLS path — not call_llm_via_mcp(). We built and proved the MCP
path works at the protocol level (mcp_server.py + mcp_client.py,
confirmed via mcp_diagnostic.py and MCP Inspector: real handshake, real
tool call, real data back). But google-genai's "pass a live MCP session
as tools=[session]" support is explicitly experimental, and it currently
fails with `TypeError: cannot pickle '_asyncio.Future' object` — a bug
in the SDK's own session-handling, not in this project's code (our usage
matches Google's documented example exactly). Rather than build a manual
tool-calling loop to work around an experimental, still-settling SDK
feature, we're keeping the live path on Phase 8's proven call_llm() and
leaving mcp_server.py/mcp_client.py in place, tested, ready to flip back
on (see call_llm_via_mcp() below) once the SDK matures. "Simple and
working over clever and fragile" — same principle this project has
followed since Phase 1.
"""

import asyncio
import os
from dataclasses import dataclass, field
from typing import List, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types

from crm import TOOLS
from crm import init_db as init_crm_db
from guardrails import check_response, check_sensitive_request, is_smalltalk
from kb import KBDoc
from mcp_client import call_llm_via_mcp_async
from memory import Message, add_message, create_conversation, get_recent_messages, init_db
from vector_search import search_kb

load_dotenv()
init_db()
init_crm_db()


def describe_exception(exc: BaseException) -> str:
    """Turn an exception into a readable message for the CLI/API.

    Needed because of Phase 9: the MCP client SDK uses asyncio.TaskGroup
    internally, which wraps failures in an ExceptionGroup. Printing that
    directly just says "unhandled errors in a TaskGroup (1 sub-exception)"
    with no useful detail — this walks into the group and returns the
    actual underlying error(s) instead.
    """
    if hasattr(exc, "exceptions"):  # ExceptionGroup / BaseExceptionGroup (Python 3.11+)
        return "; ".join(describe_exception(sub) for sub in exc.exceptions)
    return f"{type(exc).__name__}: {exc}"

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

SYSTEM_PROMPT = (
    "You are SupportPilot, a helpful and concise customer support assistant. "
    "Answer clearly and directly. If you are not sure of an answer, say so "
    "honestly instead of guessing. You have tools available to look up a "
    "customer's account, check whether their plan includes a feature, and "
    "open a support ticket — use them when the question needs a real "
    "account lookup or can't be resolved from the knowledge base alone. "
    "If you need a customer id to use a tool and don't have one, ask for it "
    "rather than guessing one."
)


@dataclass
class AgentState:
    """One support request, tracked step by step.

    Printing/inspecting this at any point tells you exactly what the agent
    has done so far. Phase 10 adds guardrail_triggered: None if nothing
    fired, or "sensitive_escalation" / "missing_citation" /
    "unsupported_commitment" if a guardrail overrode the answer. When
    it's "sensitive_escalation", the turn never reached Gemini at all —
    prompt/llm_answer/tool_calls stay empty, which is itself useful to
    see when inspecting a state.
    """
    message: str
    conversation_id: Optional[str] = None
    history: List[Message] = field(default_factory=list)
    retrieved_docs: List[KBDoc] = field(default_factory=list)
    citations: List[str] = field(default_factory=list)
    tool_calls: List[dict] = field(default_factory=list)
    guardrail_triggered: Optional[str] = None
    prompt: Optional[str] = None
    llm_answer: Optional[str] = None
    response: Optional[str] = None


def build_prompt(
    message: str,
    docs: Optional[List[KBDoc]] = None,
    history: Optional[List[Message]] = None,
    system_prompt: str = SYSTEM_PROMPT,
) -> str:
    """Turn the raw user message (plus any retrieved KB docs and recent
    conversation history) into the full prompt sent to Gemini.

    Pure function: same inputs always give the same output, no network
    call, no API key needed. Deliberately separate from call_llm() so it
    can be unit tested on its own.

    With no docs and no history (the Phase 2 case), this produces exactly
    the same prompt as before — verified by test_agent.py. Docs add a
    knowledge-base context block (Phase 5/6); history adds a short
    "recent conversation" block so follow-up questions have context
    (Phase 7).
    """
    docs = docs or []
    history = history or []

    parts = [system_prompt]

    if history:
        history_text = "\n".join(f"{m.role}: {m.content}" for m in history)
        parts.append(
            "Recent conversation so far (use this for context on "
            "follow-up questions, e.g. \"what about a refund instead?\"):\n"
            f"{history_text}"
        )

    if docs:
        context_block = "\n\n".join(f"[{doc.doc_id}]\n{doc.text}" for doc in docs)
        parts.append(
            "Answer using ONLY the knowledge base articles below if they are "
            "relevant. When you use information from an article, cite it by "
            "its id in square brackets, e.g. [orders]. If the articles don't "
            "cover the question, say you don't know instead of guessing.\n\n"
            f"--- Knowledge Base ---\n{context_block}\n--- End Knowledge Base ---"
        )

    parts.append(f"Customer question: {message}\n\nAnswer:")

    return "\n\n".join(parts)


_client = None


def get_client() -> genai.Client:
    """Create (once) and return the Gemini client.

    Kept out of build_prompt()'s path on purpose: importing this module
    for tests must not require an API key. The key is only checked when
    we actually need to call Gemini.
    """
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise SystemExit(
                "Missing GEMINI_API_KEY.\n"
                "Copy .env.example to .env and paste your key in there."
            )
        _client = genai.Client(api_key=api_key)
    return _client


def extract_tool_calls(response) -> List[dict]:
    """Turn a Gemini response's automatic_function_calling_history into a
    plain list of {name, args, result} dicts.

    This only reads data the SDK already fetched during call_llm() — no
    extra network call — so it's safe to unit test with a fake response
    object (see test_agent.py). Returns [] if no tools were called, or if
    the response doesn't have the field at all (e.g. a stub in a test).
    """
    history = getattr(response, "automatic_function_calling_history", None) or []

    calls: List[dict] = []
    for content in history:
        for part in getattr(content, "parts", None) or []:
            function_call = getattr(part, "function_call", None)
            if function_call is not None:
                calls.append(
                    {"name": function_call.name, "args": dict(function_call.args or {}), "result": None}
                )
                continue

            function_response = getattr(part, "function_response", None)
            if function_response is not None:
                # Pair this result with the most recent matching call that
                # doesn't have one yet.
                for call in reversed(calls):
                    if call["name"] == function_response.name and call["result"] is None:
                        call["result"] = function_response.response
                        break

    return calls


def call_llm(prompt: str):
    """Send the built prompt to Gemini, with the Phase 8 tools available
    directly as plain functions (tools=TOOLS).

    Returns (answer_text, tool_calls) — tool_calls is [] if the model
    answered without needing any tool. This is the live path run_agent()
    uses (see the module docstring's Phase 9 status note for why).
    """
    client = get_client()
    result = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(tools=TOOLS),
    )
    return result.text, extract_tool_calls(result)


def call_llm_via_mcp(prompt: str):
    """Phase 9: same as call_llm(), but the tools are called through MCP
    (mcp_server.py) instead of directly as plain functions.

    Synchronous wrapper around mcp_client.call_llm_via_mcp_async() (via
    asyncio.run) — the MCP client SDK is async-only, but wrapping it here
    means run_agent(), chat.py, and api.py could all stay synchronous and
    unchanged if this were the live path. Returns (answer_text, tool_calls),
    the same shape as call_llm(). Not currently called by run_agent() — see
    the module docstring's Phase 9 status note. The underlying MCP
    connection is proven to work (mcp_diagnostic.py); this function itself
    hits the google-genai SDK's experimental-MCP bug when actually used.
    """
    answer_text, raw_response = asyncio.run(call_llm_via_mcp_async(prompt))
    return answer_text, extract_tool_calls(raw_response)


def run_agent(message: str, conversation_id: Optional[str] = None) -> AgentState:
    """Run the full flow for one message:

        conversation_id -> history (memory)
        message -> [guardrail 1: sensitive request? escalate, skip Gemini]
                 -> search_kb (Pinecone) -> retrieved_docs/citations
                 -> prompt -> llm_answer + tool_calls (Gemini, tools=TOOLS)
                 -> [guardrails 2/3: citation required? unsupported commitment?]
                 -> response
                 -> save this turn to memory

    If conversation_id is None, a brand-new conversation is created —
    useful for a one-off call or a test. For an actual multi-turn chat,
    the caller must pass the SAME conversation_id on every turn (chat.py
    and api.py both do this).

    Returns the filled-in AgentState so a caller can see every
    intermediate step, not just the final answer.
    """
    if conversation_id is None:
        conversation_id = create_conversation()

    state = AgentState(message=message, conversation_id=conversation_id)
    state.history = get_recent_messages(conversation_id)

    # Guardrail 1: sensitive requests are escalated before Gemini is ever
    # called — see guardrails.py for why this one is checked up front
    # instead of after the fact. history is passed so a customer id
    # given earlier in the conversation is found without asking again.
    sensitive = check_sensitive_request(message, history=state.history)
    if sensitive.triggered:
        state.guardrail_triggered = sensitive.triggered
        state.response = sensitive.response
        add_message(conversation_id, "user", state.message)
        add_message(conversation_id, "assistant", state.response)
        return state

    # Small talk ("thank you", "hi", ...) never needs KB grounding — skip
    # retrieval entirely rather than relying only on the relevance score
    # cutoff, which alone wasn't reliable enough (see guardrails.py).
    state.retrieved_docs = [] if is_smalltalk(state.message) else search_kb(state.message)
    state.citations = [doc.doc_id for doc in state.retrieved_docs]
    state.prompt = build_prompt(
        state.message, docs=state.retrieved_docs, history=state.history
    )
    state.llm_answer, state.tool_calls = call_llm(state.prompt)
    state.response = state.llm_answer.strip()

    # Guardrails 2 & 3: checked against Gemini's actual answer before the
    # customer ever sees it. tool_calls is passed so a tool-call
    # confirmation (e.g. "I opened ticket #4") isn't wrongly treated as
    # an uncited KB claim.
    response_check = check_response(state.response, state.retrieved_docs, state.tool_calls)
    if response_check.triggered:
        state.guardrail_triggered = response_check.triggered
        state.response = response_check.response

    add_message(conversation_id, "user", state.message)
    add_message(conversation_id, "assistant", state.response)

    return state
