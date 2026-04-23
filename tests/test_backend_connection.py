from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
)


# ── get_user_by_id ────────────────────────────────────────────────────────────

def test_get_user_by_id_valid(seed_user):
    user = get_user_by_id(seed_user["id"])
    assert user is not None
    assert user["name"] == "Demo User"
    assert user["email"] == "demo@spendly.com"
    assert user["initials"] == "DU"
    assert user["member_since"] != ""


def test_get_user_by_id_nonexistent(app):
    result = get_user_by_id(99999)
    assert result is None


# ── get_summary_stats ─────────────────────────────────────────────────────────

def test_get_summary_stats_with_expenses(seed_user):
    stats = get_summary_stats(seed_user["id"])
    assert stats["count"] == 8
    assert stats["total"] == "3,800.00"
    assert stats["top_category"] == "Bills"


def test_get_summary_stats_no_expenses(empty_user):
    stats = get_summary_stats(empty_user["id"])
    assert stats["total"] == "0.00"
    assert stats["count"] == 0
    assert stats["top_category"] == "—"


# ── get_recent_transactions ───────────────────────────────────────────────────

def test_get_recent_transactions_with_expenses(seed_user):
    txs = get_recent_transactions(seed_user["id"])
    assert len(txs) == 8
    for tx in txs:
        assert "date" in tx
        assert "description" in tx
        assert "category" in tx
        assert "amount" in tx
    # newest-first: 2026-04-08 rows come before 2026-04-01
    dates = [tx["date"] for tx in txs]
    assert dates[0] in ("08 Apr 2026",)
    assert dates[-1] == "01 Apr 2026"


def test_get_recent_transactions_no_expenses(empty_user):
    txs = get_recent_transactions(empty_user["id"])
    assert txs == []


# ── get_category_breakdown ────────────────────────────────────────────────────

def test_get_category_breakdown_with_expenses(seed_user):
    cats = get_category_breakdown(seed_user["id"])
    assert len(cats) == 7
    for cat in cats:
        assert "name" in cat
        assert "amount" in cat
        assert "percent" in cat
        assert isinstance(cat["percent"], int)
    # percentages must sum to 100
    assert sum(c["percent"] for c in cats) == 100
    # ordered by amount descending — Bills (1200) is highest
    assert cats[0]["name"] == "Bills"


def test_get_category_breakdown_no_expenses(empty_user):
    cats = get_category_breakdown(empty_user["id"])
    assert cats == []


# ── Route: GET /profile ───────────────────────────────────────────────────────

def test_profile_redirects_unauthenticated(client):
    response = client.get("/profile")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_profile_authenticated(client, seed_user):
    with client.session_transaction() as sess:
        sess["user_id"] = seed_user["id"]
        sess["user_name"] = seed_user["name"]

    response = client.get("/profile")
    assert response.status_code == 200

    body = response.data.decode()
    assert "Demo User" in body
    assert "demo@spendly.com" in body
    assert "₹" in body
    assert "3,800.00" in body
    assert "Bills" in body
