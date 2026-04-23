import pytest
from werkzeug.security import generate_password_hash

import database.db as db_module
from database.db import get_db, init_db


@pytest.fixture
def app(monkeypatch, tmp_path):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    # Prevent seed_db() from running on first module import so tests control all data
    monkeypatch.setattr(db_module, "seed_db", lambda: None)

    from app import app as flask_app
    flask_app.config["TESTING"] = True

    with flask_app.app_context():
        init_db()

    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def seed_user(app):
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Demo User", "demo@spendly.com", generate_password_hash("demo123")),
    )
    user_id = cursor.lastrowid

    expenses = [
        (user_id, 450.00,  "Food",          "2026-04-01", "Groceries from D-Mart"),
        (user_id, 120.00,  "Transport",     "2026-04-02", "Metro card recharge"),
        (user_id, 1200.00, "Bills",         "2026-04-03", "Electricity bill"),
        (user_id, 350.00,  "Health",        "2026-04-05", "Pharmacy — vitamins"),
        (user_id, 500.00,  "Entertainment", "2026-04-06", "Movie tickets"),
        (user_id, 800.00,  "Shopping",      "2026-04-07", "New earphones"),
        (user_id, 200.00,  "Other",         "2026-04-08", "Miscellaneous"),
        (user_id, 180.00,  "Food",          "2026-04-08", "Lunch with colleagues"),
    ]
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        expenses,
    )
    conn.commit()
    conn.close()

    return {"id": user_id, "name": "Demo User", "email": "demo@spendly.com"}


@pytest.fixture
def empty_user(app):
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("New User", "new@spendly.com", generate_password_hash("pass123")),
    )
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"id": user_id, "name": "New User", "email": "new@spendly.com"}
