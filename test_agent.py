"""
Tests for prompt construction (Phase 2) and tool-call extraction (Phase 8).

None of these call Gemini or need an API key in .env — build_prompt() is
pure, and extract_tool_calls() is tested against plain duck-typed fakes
that mimic the shape of a Gemini response, not a real SDK object.

Run:
    uv run pytest
"""

from types import SimpleNamespace

from agent import SYSTEM_PROMPT, build_prompt, extract_tool_calls


def test_prompt_includes_system_prompt():
    prompt = build_prompt("How do I reset my password?")
    assert SYSTEM_PROMPT in prompt


def test_prompt_includes_user_message():
    prompt = build_prompt("How do I reset my password?")
    assert "How do I reset my password?" in prompt


def test_prompt_puts_system_prompt_before_question():
    prompt = build_prompt("How do I reset my password?")
    assert prompt.index(SYSTEM_PROMPT) < prompt.index("How do I reset my password?")


def test_prompt_accepts_custom_system_prompt():
    prompt = build_prompt("Hi", system_prompt="Be brief.")
    assert "Be brief." in prompt
    assert SYSTEM_PROMPT not in prompt


def _fake_call_part(name, args):
    """A duck-typed stand-in for one Part of a Gemini response's
    automatic_function_calling_history — no google-genai import needed.
    """
    return SimpleNamespace(function_call=SimpleNamespace(name=name, args=args), function_response=None)


def _fake_response_part(name, response):
    return SimpleNamespace(function_call=None, function_response=SimpleNamespace(name=name, response=response))


def test_extract_tool_calls_pairs_call_with_result():
    fake_response = SimpleNamespace(
        automatic_function_calling_history=[
            SimpleNamespace(parts=[_fake_call_part("get_customer_profile", {"customer_id": "CUST-001"})]),
            SimpleNamespace(
                parts=[_fake_response_part("get_customer_profile", {"name": "Priya Shah", "plan": "pro"})]
            ),
        ]
    )
    calls = extract_tool_calls(fake_response)
    assert len(calls) == 1
    assert calls[0]["name"] == "get_customer_profile"
    assert calls[0]["args"] == {"customer_id": "CUST-001"}
    assert calls[0]["result"] == {"name": "Priya Shah", "plan": "pro"}


def test_extract_tool_calls_empty_when_history_is_none():
    fake_response = SimpleNamespace(automatic_function_calling_history=None)
    assert extract_tool_calls(fake_response) == []


def test_extract_tool_calls_empty_when_field_missing():
    fake_response = SimpleNamespace()  # no automatic_function_calling_history attribute at all
    assert extract_tool_calls(fake_response) == []


def test_extract_tool_calls_handles_multiple_calls():
    fake_response = SimpleNamespace(
        automatic_function_calling_history=[
            SimpleNamespace(
                parts=[
                    _fake_call_part("get_customer_profile", {"customer_id": "CUST-001"}),
                    _fake_call_part("check_feature_access", {"customer_id": "CUST-001", "feature": "api_access"}),
                ]
            ),
            SimpleNamespace(
                parts=[
                    _fake_response_part("get_customer_profile", {"plan": "pro"}),
                    _fake_response_part("check_feature_access", {"has_access": False}),
                ]
            ),
        ]
    )
    calls = extract_tool_calls(fake_response)
    assert len(calls) == 2
    assert calls[0]["name"] == "get_customer_profile"
    assert calls[0]["result"] == {"plan": "pro"}
    assert calls[1]["name"] == "check_feature_access"
    assert calls[1]["result"] == {"has_access": False}
