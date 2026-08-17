"""
SupportPilot AI — Phase 8: Tools (customer/order data + tool functions)

Goal: let the agent DO things, not just answer from the knowledge base —
look up a real customer, check what their plan includes, or open a
support ticket.

This file holds:
  - customers/orders/tickets tables (same SQLite file as Phase 7's
    memory.py — data/supportpilot.db — just different tables)
  - PLAN_FEATURES: the (hand-authored, not from any dataset) rule for
    which plan includes which feature
  - the three tool functions themselves: get_customer_profile,
    check_feature_access, create_support_ticket

These are PLAIN Python functions — type-hinted, with Google-style
docstrings, nothing MCP or framework-specific yet. agent.py passes them
directly to Gemini as `tools=[...]`; the google-genai SDK's automatic
function calling reads the type hints/docstrings to build the schema,
decides when to call them, executes them, and feeds the result back to
the model. Phase 9 wraps these same functions behind MCP — the functions
themselves won't change.

Customer/order data is seeded by seed_crm.py (run once). This file only
reads/writes what's actually in the database — it never invents records
at request time.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "supportpilot.db"

# Which features come with which plan. Hand-authored on purpose — this
# is exactly the kind of business rule no public dataset can give you
# for free (see PHASE_PLAN.md's note on why Phase 8 uses hand-written
# seed data instead of a real e-commerce dataset).
PLAN_FEATURES = {
    "free": [],
    "pro": ["priority_support", "bulk_orders"],
    "business": [
        "priority_support",
        "bulk_orders",
        "dedicated_account_manager",
        "api_access",
    ],
}

# Cheapest -> most capable. Used to suggest which plan a customer would
# need to upgrade to for a feature they don't currently have.
PLAN_ORDER = ["free", "pro", "business"]

ALL_FEATURES = {feature for features in PLAN_FEATURES.values() for feature in features}


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    """Create the customers/orders/tickets tables if they don't exist yet.
    Cheap and idempotent — safe to call on every app start.
    """
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                plan TEXT NOT NULL,
                signup_date TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                product TEXT NOT NULL,
                status TEXT NOT NULL,
                order_date TEXT NOT NULL,
                amount REAL NOT NULL,
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id TEXT NOT NULL,
                subject TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


# ---------------------------------------------------------------------
# Tools. These three functions are passed directly to Gemini as
# tools=[...] in agent.py. Keep their docstrings accurate — the MODEL
# reads them (not this file's comments) to decide when and how to call
# each one.
# ---------------------------------------------------------------------


def get_customer_profile(customer_id: str) -> dict:
    """Look up a customer's account profile by their customer id.

    Args:
        customer_id: The customer's id, e.g. "CUST-001".

    Returns:
        A dictionary with the customer's name, email, plan, and signup
        date. If no customer with that id exists, returns a dictionary
        with an "error" key instead.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, name, email, plan, signup_date FROM customers WHERE id = ?",
            (customer_id,),
        ).fetchone()

    if row is None:
        return {"error": f"No customer found with id '{customer_id}'."}

    return {
        "customer_id": row[0],
        "name": row[1],
        "email": row[2],
        "plan": row[3],
        "signup_date": row[4],
    }


def check_feature_access(customer_id: str, feature: str) -> dict:
    """Check whether a customer's current plan includes a given feature.

    Args:
        customer_id: The customer's id, e.g. "CUST-001".
        feature: The feature to check. One of: "priority_support",
            "bulk_orders", "dedicated_account_manager", "api_access".

    Returns:
        A dictionary with has_access (bool), the customer's current
        plan, and — if they don't have access — which plan they'd need
        to upgrade to. Returns an "error" key if the customer id or
        feature name isn't recognized.
    """
    customer = get_customer_profile(customer_id)
    if "error" in customer:
        return customer

    if feature not in ALL_FEATURES:
        return {"error": f"Unknown feature '{feature}'."}

    plan = customer["plan"]
    has_access = feature in PLAN_FEATURES.get(plan, [])

    result = {
        "customer_id": customer_id,
        "plan": plan,
        "feature": feature,
        "has_access": has_access,
    }

    if not has_access:
        for candidate_plan in PLAN_ORDER:
            if feature in PLAN_FEATURES.get(candidate_plan, []):
                result["upgrade_required"] = candidate_plan
                break

    return result


def create_support_ticket(customer_id: str, subject: str, description: str) -> dict:
    """Create a support ticket for a customer.

    Use this when a customer's issue genuinely needs a human agent to
    follow up — not for questions the knowledge base already answers.

    Args:
        customer_id: The customer's id, e.g. "CUST-001".
        subject: A short, few-word summary of the issue.
        description: The full issue, in enough detail for a human agent
            to pick it up without needing to re-ask the customer.

    Returns:
        A dictionary with the new ticket's id and status.
    """
    created_at = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO tickets (customer_id, subject, description, status, created_at) "
            "VALUES (?, ?, ?, 'open', ?)",
            (customer_id, subject, description, created_at),
        )
        ticket_id = cursor.lastrowid

    return {
        "ticket_id": ticket_id,
        "customer_id": customer_id,
        "subject": subject,
        "status": "open",
    }


# Passed directly to Gemini in agent.py's call_llm() as `tools=TOOLS`.
TOOLS = [get_customer_profile, check_feature_access, create_support_ticket]