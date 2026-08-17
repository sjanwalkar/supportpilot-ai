"""
Tests for Phase 8 CRM tool functions.

Uses a temporary database file (same pattern as test_memory.py) so these
never touch your real data/supportpilot.db and don't need any API key or
network access — get_customer_profile/check_feature_access/
create_support_ticket are plain SQLite reads and writes, no LLM call
involved.

Run:
    uv run pytest
"""

import tempfile
from pathlib import Path

import crm


def _use_temp_db():
    """Point crm.DB_PATH at a fresh temp file with two seeded customers."""
    tmp_dir = tempfile.mkdtemp()
    crm.DB_PATH = Path(tmp_dir) / "test.db"
    crm.init_db()
    with crm.get_connection() as conn:
        conn.execute(
            "INSERT INTO customers (id, name, email, plan, signup_date) VALUES (?, ?, ?, ?, ?)",
            ("CUST-001", "Test Customer", "test@example.com", "pro", "2024-01-01"),
        )
        conn.execute(
            "INSERT INTO customers (id, name, email, plan, signup_date) VALUES (?, ?, ?, ?, ?)",
            ("CUST-002", "Free Customer", "free@example.com", "free", "2024-01-01"),
        )


def test_get_customer_profile_found():
    _use_temp_db()
    profile = crm.get_customer_profile("CUST-001")
    assert profile["name"] == "Test Customer"
    assert profile["plan"] == "pro"


def test_get_customer_profile_not_found():
    _use_temp_db()
    profile = crm.get_customer_profile("CUST-999")
    assert "error" in profile


def test_check_feature_access_granted():
    _use_temp_db()
    result = crm.check_feature_access("CUST-001", "priority_support")
    assert result["has_access"] is True
    assert "upgrade_required" not in result


def test_check_feature_access_denied_suggests_upgrade():
    _use_temp_db()
    result = crm.check_feature_access("CUST-002", "priority_support")
    assert result["has_access"] is False
    assert result["upgrade_required"] == "pro"


def test_check_feature_access_unknown_customer():
    _use_temp_db()
    result = crm.check_feature_access("CUST-999", "priority_support")
    assert "error" in result


def test_check_feature_access_unknown_feature():
    _use_temp_db()
    result = crm.check_feature_access("CUST-001", "time_travel")
    assert "error" in result


def test_create_support_ticket():
    _use_temp_db()
    ticket = crm.create_support_ticket(
        "CUST-001", "Broken item", "The keyboard arrived broken."
    )
    assert ticket["status"] == "open"
    assert ticket["customer_id"] == "CUST-001"
    assert isinstance(ticket["ticket_id"], int)


def test_create_support_ticket_persists():
    _use_temp_db()
    crm.create_support_ticket("CUST-001", "Subject A", "Description A")
    with crm.get_connection() as conn:
        rows = conn.execute("SELECT subject FROM tickets").fetchall()
    assert rows == [("Subject A",)]
