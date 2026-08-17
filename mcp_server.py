"""
SupportPilot AI — Phase 9: MCP server

Wraps the exact same three tool functions from crm.py as MCP tools — no
reimplementation, no new logic. This file only registers them.

Run directly for a quick sanity check that it starts:

    uv run python mcp_server.py

(It will then sit waiting for stdio input — that's normal; Ctrl+C to stop.
It's meant to be spawned by a client, not run interactively.)

Or point MCP Inspector at it (requires Node.js):

    npx @modelcontextprotocol/inspector uv run python mcp_server.py

Open the local URL Inspector prints — it lists all three tools and lets
you fill in arguments and call them directly, no Gemini involved. That's
what satisfies this phase's "MCP Inspector can see the tools" bar.

Transport is stdio (the default, and the right choice for a server meant
to be spawned locally as a subprocess) — this process talks over
stdin/stdout to whatever spawns it (Inspector, or mcp_client.py in this
project), not over the network.
"""

from mcp.server.fastmcp import FastMCP

from crm import check_feature_access, create_support_ticket, get_customer_profile, init_db

init_db()

mcp = FastMCP("SupportPilot Tools")

# Register the SAME function objects imported from crm.py — nothing is
# redefined here. That's deliberate: there's exactly one place this
# logic lives and is tested (test_crm.py already covers all three as
# plain Python, satisfying this phase's "tools remain testable" bar).
mcp.tool()(get_customer_profile)
mcp.tool()(check_feature_access)
mcp.tool()(create_support_ticket)


if __name__ == "__main__":
    mcp.run()
