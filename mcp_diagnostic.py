"""
Diagnostic for the Phase 9 MCP wiring — NOT part of the app itself.

Tests ONLY the MCP client <-> server connection (spawn, handshake, list
tools, call one tool) with no Gemini involved at all. This isolates
where a failure actually is:

  - If THIS script fails -> the problem is in mcp_server.py or the
    stdio connection itself. Fix that first.
  - If THIS script succeeds but the real app (chat.py) still fails ->
    the problem is specific to how google-genai's experimental
    "pass an MCP session as a tool" feature uses the session, not the
    MCP connection itself.

Run:
    uv run python mcp_diagnostic.py

Expected output ends with the three tool names and a successful
get_customer_profile call for CUST-001.
"""

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

MCP_SERVER_PATH = Path(__file__).parent / "mcp_server.py"


async def main():
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(MCP_SERVER_PATH)],
    )
    print(f"Spawning: {sys.executable} {MCP_SERVER_PATH}")

    async with stdio_client(server_params) as (read, write):
        print("stdio_client connected.")

        async with ClientSession(read, write) as session:
            await session.initialize()
            print("Session initialized OK.")

            tools_result = await session.list_tools()
            tool_names = [t.name for t in tools_result.tools]
            print(f"Tools found: {tool_names}")

            assert set(tool_names) == {
                "get_customer_profile",
                "check_feature_access",
                "create_support_ticket",
            }, f"Unexpected tool set: {tool_names}"

            print("\nCalling get_customer_profile(customer_id='CUST-001') directly...")
            result = await session.call_tool(
                "get_customer_profile", {"customer_id": "CUST-001"}
            )
            print("Result:", result)

    print("\nAll checks passed — the MCP connection itself works correctly.")


if __name__ == "__main__":
    asyncio.run(main())
