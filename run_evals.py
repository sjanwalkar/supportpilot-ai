"""
SupportPilot AI — Phase 11: Eval runner

Runs every question in data/eval/golden_questions.json through the REAL
agent (agent.run_agent()) and scores each with evals.score_question().

Unlike every `uv run pytest` test in this project, this makes real
Gemini + Pinecone calls — it needs GEMINI_API_KEY and PINECONE_API_KEY
in .env, and costs whatever those calls cost. That's deliberate: an eval
suite is meant to check the real, live system end to end, not a stubbed
one — that's the whole point versus the unit tests.

Run:
    uv run python run_evals.py

Known side effect: escalation questions that include a customer id
create a REAL row in the tickets table each run, same as an actual user
triggering escalation would. Harmless, just noise in
data/supportpilot.db — a production eval suite would likely point at a
separate database for this; keeping it simple here, consistent with
every other "known simplification" noted elsewhere in this project.
"""

import json
from pathlib import Path

from agent import run_agent
from evals import score_question, summarize

GOLDEN_QUESTIONS_PATH = Path(__file__).parent / "data" / "eval" / "golden_questions.json"


def load_questions():
    with open(GOLDEN_QUESTIONS_PATH) as f:
        return json.load(f)


def main():
    questions = load_questions()
    print(f"Running {len(questions)} eval questions against the live agent...\n")

    results = []
    for question in questions:
        state = run_agent(question["message"])  # fresh conversation each time
        result = score_question(question, state)
        results.append(result)

        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.question_id}: {question['message']!r}")
        for note in result.notes:
            print(f"       {note}")

    summary = summarize(results)

    print("\n" + "=" * 50)
    print("SupportPilot AI — Eval Scorecard")
    print("=" * 50)
    for metric, value in summary.items():
        if value is None:
            continue
        passed, total = value
        pct = (passed / total * 100) if total else 0.0
        label = metric.replace("_", " ").title()
        print(f"{label:<24} {passed}/{total}  ({pct:.1f}%)")

    failures = [r for r in results if not r.passed]
    if failures:
        print(f"\n{len(failures)} question(s) failed:")
        for r in failures:
            print(f"  - {r.question_id}: {r.message!r}")
    else:
        print("\nAll questions passed.")


if __name__ == "__main__":
    main()
