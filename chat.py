"""
SupportPilot AI — CLI (Phases 2, 5/6 RAG, 7 memory, 8 tools, 10 guardrails)

Same terminal loop as before, plus one addition: a single conversation_id
is created once at the start of the session and passed to run_agent() on
every turn, so follow-up questions ("what about a refund instead?") have
the prior turns as context. Also prints which tool(s), if any, Gemini
used, and flags when a Phase 10 guardrail overrode the answer.

Run: uv run chat.py
"""

from agent import run_agent, MODEL, describe_exception
from memory import create_conversation


def _format_tool_calls(tool_calls):
    parts = []
    for call in tool_calls:
        args_str = ", ".join(f"{k}={v!r}" for k, v in call["args"].items())
        parts.append(f"{call['name']}({args_str})")
    return ", ".join(parts)


def main():
    print("SupportPilot AI — Phase 10 (guardrails)")
    print(f"Model: {MODEL}")

    conversation_id = create_conversation()
    print(f"Conversation: {conversation_id}")
    print("Type a support question. Type 'exit' or 'quit' to stop.\n")

    while True:
        user_message = input("You: ").strip()

        if user_message.lower() in {"exit", "quit"}:
            print("Goodbye!")
            break

        if not user_message:
            continue

        try:
            # Same conversation_id every turn -- this is what makes
            # follow-up questions work.
            state = run_agent(user_message, conversation_id=conversation_id)
        except SystemExit:
            # Missing API key — let the clear message from agent.py
            # reach the user instead of getting swallowed below.
            raise
        except Exception as e:
            print(f"[Error calling Gemini: {describe_exception(e)}]\n")
            continue

        print(f"Bot: {state.response}")
        if state.guardrail_triggered:
            print(f"[Guardrail: {state.guardrail_triggered}]")
        if state.tool_calls:
            print(f"Tools used: {_format_tool_calls(state.tool_calls)}")
        if state.citations:
            print(f"Sources: {', '.join(state.citations)}")
        print()


if __name__ == "__main__":
    main()
