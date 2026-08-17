"""
SupportPilot AI — Phase 9: MCP client

Phase 8 passed crm.py's tool functions to Gemini directly: tools=TOOLS.
This phase instead spawns mcp_server.py as a subprocess (stdio
transport) and passes the live MCP session as the tool: tools=[session].
The google-genai SDK's built-in (experimental) MCP support discovers the
server's tools, calls them, and feeds results back to the model
automatically — same as it does for plain Python functions.

This file is async because the MCP client SDK is async-only. agent.py
wraps call_llm_via_mcp_async() in a synchronous call_llm_via_mcp()
(via asyncio.run), so chat.py and api.py don't need to change at all.

Simplification worth knowing: every call here spawns a fresh server
subprocess and tears it down afterward — simple and correct, but not
efficient. A production system would keep one long-lived MCP connection
across requests instead of reconnecting per message. That's exactly the
kind of thing Phase 13's modularization pass would be the place to fix,
not something to solve prematurely here.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
MCP_SERVER_PATH = Path(__file__).parent / "mcp_server.py"

# Kept separate from agent.get_client() on purpose — same reason
# vector_search.py has its own get_genai_client(): agent.py imports FROM
# this file, so this file can't import back from agent.py without a
# circular import.
_genai_client = None


def get_genai_client() -> genai.Client:
    global _genai_client
    if _genai_client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise SystemExit(
                "Missing GEMINI_API_KEY.\n"
                "Copy .env.example to .env and paste your key in there."
            )
        _genai_client = genai.Client(api_key=api_key)
    return _genai_client


async def call_llm_via_mcp_async(prompt: str):
    """Spawn mcp_server.py, call Gemini with the live session as a tool,
    and return (answer_text, raw_response).

    Returns the raw SDK response (not pre-extracted tool calls) so
    agent.py can reuse its own extract_tool_calls() on it — one
    extraction implementation, used for both Phase 8's plain-function
    calls and this phase's MCP-backed ones.
    """
    client = get_genai_client()

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(MCP_SERVER_PATH)],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            response = await client.aio.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(tools=[session]),
            )

    return response.text, response
