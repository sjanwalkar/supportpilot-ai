"""
SupportPilot AI — Phase 8: seed fake customer/order data

Loads 15 hand-authored fake customers (and their orders) into SQLite, so
get_customer_profile() / check_feature_access() have real records to
look up. Run once, and again any time you want to reset back to this
known set of customers:

    uv run python seed_crm.py

Clears and reinserts customers/orders only. Support tickets created by
actually using the app (create_support_ticket) are left alone.

Why hand-authored instead of pulling a real e-commerce dataset (e.g.
from Hugging Face)? See PHASE_PLAN.md's Phase 8 note — in short:
plan/feature rules are inherently made up for a fictional company, no
public dataset gives you those for free, and 15 readable rows are more
useful for learning than wiring up a large relational dataset on top of
the tool-calling problem this phase is actually about.
"""

from crm import get_connection, init_db

CUSTOMERS = [
    # (id, name, email, plan, signup_date)
    ("CUST-001", "Priya Shah", "priya.shah@example.com", "pro", "2024-03-11"),
    ("CUST-002", "Marcus Webb", "marcus.webb@example.com", "free", "2025-01-22"),
    ("CUST-003", "Elena Volkov", "elena.volkov@example.com", "business", "2023-11-02"),
    ("CUST-004", "Tom O'Brien", "tom.obrien@example.com", "free", "2025-06-14"),
    ("CUST-005", "Aiko Tanaka", "aiko.tanaka@example.com", "pro", "2024-08-30"),
    ("CUST-006", "Diego Ramirez", "diego.ramirez@example.com", "free", "2025-03-05"),
    ("CUST-007", "Sarah Kim", "sarah.kim@example.com", "business", "2022-09-19"),
    ("CUST-008", "Liam Chen", "liam.chen@example.com", "pro", "2024-12-01"),
    ("CUST-009", "Fatima Al-Sayed", "fatima.alsayed@example.com", "free", "2025-05-27"),
    ("CUST-010", "Nadia Petrova", "nadia.petrova@example.com", "business", "2023-04-08"),
    ("CUST-011", "James Whitfield", "james.whitfield@example.com", "pro", "2024-02-17"),
    ("CUST-012", "Grace Adeyemi", "grace.adeyemi@example.com", "free", "2025-07-09"),
    ("CUST-013", "Hiroshi Sato", "hiroshi.sato@example.com", "pro", "2024-10-23"),
    ("CUST-014", "Isabelle Laurent", "isabelle.laurent@example.com", "business", "2023-07-14"),
    ("CUST-015", "Noah Fischer", "noah.fischer@example.com", "free", "2025-02-28"),
]

ORDERS = [
    # (id, customer_id, product, status, order_date, amount)
    ("ORD-0001", "CUST-001", "Mechanical Keyboard", "delivered", "2024-04-02", 89.99),
    ("ORD-0002", "CUST-001", "USB-C Hub", "delivered", "2024-09-18", 34.50),
    ("ORD-0003", "CUST-002", "Wireless Mouse", "shipped", "2025-06-30", 24.99),
    ("ORD-0004", "CUST-003", "Standing Desk", "delivered", "2023-12-05", 349.00),
    ("ORD-0005", "CUST-003", "Ergonomic Chair Cushion", "delivered", "2024-05-11", 45.00),
    ("ORD-0006", "CUST-004", "Desk Lamp", "processing", "2025-07-01", 29.99),
    ("ORD-0007", "CUST-005", "Noise-Cancelling Headphones", "delivered", "2024-09-14", 199.00),
    ("ORD-0008", "CUST-006", "Webcam", "canceled", "2025-03-20", 59.99),
    ("ORD-0009", "CUST-007", "Monitor Stand", "delivered", "2022-10-02", 42.00),
    ("ORD-0010", "CUST-007", "Mechanical Keyboard", "delivered", "2024-01-19", 89.99),
    ("ORD-0011", "CUST-008", "Laptop Sleeve", "shipped", "2025-01-05", 22.50),
    ("ORD-0012", "CUST-009", "Wireless Mouse", "delivered", "2025-06-02", 24.99),
    ("ORD-0013", "CUST-010", "Standing Desk", "delivered", "2023-05-15", 349.00),
    ("ORD-0014", "CUST-010", "Noise-Cancelling Headphones", "delivered", "2024-02-27", 199.00),
    ("ORD-0015", "CUST-011", "USB-C Hub", "delivered", "2024-03-09", 34.50),
    ("ORD-0016", "CUST-012", "Desk Lamp", "processing", "2025-07-15", 29.99),
    ("ORD-0017", "CUST-013", "Monitor Stand", "delivered", "2024-11-08", 42.00),
    ("ORD-0018", "CUST-014", "Ergonomic Chair Cushion", "delivered", "2023-08-22", 45.00),
    ("ORD-0019", "CUST-014", "Mechanical Keyboard", "shipped", "2024-06-30", 89.99),
    ("ORD-0020", "CUST-015", "Webcam", "delivered", "2025-03-10", 59.99),
]


def main():
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM customers")
        conn.execute("DELETE FROM orders")
        conn.executemany(
            "INSERT INTO customers (id, name, email, plan, signup_date) "
            "VALUES (?, ?, ?, ?, ?)",
            CUSTOMERS,
        )
        conn.executemany(
            "INSERT INTO orders (id, customer_id, product, status, order_date, amount) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ORDERS,
        )
    print(f"Seeded {len(CUSTOMERS)} customers and {len(ORDERS)} orders.")
    print("(Tickets table left untouched.)")


if __name__ == "__main__":
    main()