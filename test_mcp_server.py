"""
Tests for Phase 9's MCP server wiring.

These check that mcp_server.py registers the SAME function objects from
crm.py — not reimplementations — as MCP tools, and that those functions
are still directly callable/testable as plain Python. That's this
phase's acceptance bar: "plain Python tool functions remain testable."

What ISN'T tested here: an actual MCP client/server round trip over
stdio, or Gemini calling a tool through MCP. Those need a live
subprocess, async I/O, and a real API key/model call — more of an
integration test than something a fast, offline unit test should do.
Exercise that by actually running the app (see README) or MCP Inspector.

Run:
    uv run pytest
"""

import crm
import mcp_server


def test_mcp_server_registers_get_customer_profile_unchanged():
    assert mcp_server.get_customer_profile is crm.get_customer_profile


def test_mcp_server_registers_check_feature_access_unchanged():
    assert mcp_server.check_feature_access is crm.check_feature_access


def test_mcp_server_registers_create_support_ticket_unchanged():
    assert mcp_server.create_support_ticket is crm.create_support_ticket


def test_wrapped_tools_are_still_directly_callable():
    # Same functions, same behavior, whether called directly (Phase 8,
    # test_crm.py) or through MCP (Phase 9) -- this is what "remains
    # testable" means in practice.
    profile = mcp_server.get_customer_profile("CUST-DOES-NOT-EXIST")
    assert "error" in profile
