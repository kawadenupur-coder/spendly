"""
tests/test_06_date_filter_profile.py

Spec behaviors under test (from .claude/specs/06-date-filter-profile.md):

 1. Auth guard: unauthenticated GET /profile redirects to /login (with and without
    date query params)
 2. GET /profile with no query params returns HTTP 200 and shows all expenses
    (unfiltered); "All Time" preset button carries the active CSS class
 3. GET /profile with valid date_from + date_to filters all three data sections:
    summary stats, recent transactions, and category breakdown
 4. Boundary-inclusive filter: expenses on exactly date_from and date_to are shown
 5. Expenses outside the date range are excluded from all three sections
 6. "This Month" preset dates render in the page; applying them highlights the button
 7. "Last 3 Months" preset dates are rendered and the button activates correctly
 8. "Last 6 Months" preset dates are rendered and the button activates correctly
 9. "All Time" preset links to clean /profile URL with no query params
10. Custom date range: date inputs pre-filled with active filter values
11. date_from > date_to: flash "Start date must be before end date." + unfiltered fallback
12. date_from == date_to (single-day range): treated as valid, error NOT flashed
13. Malformed date string for either param: no crash, silently falls back to unfiltered
    (parametrized over multiple bad-date formats including SQL-injection attempts)
14. Only one param supplied (partial filter): filter not applied, unfiltered view shown
15. Empty period (no expenses in range): HTTP 200, ₹0.00 total, 0 transactions,
    "—" top category, "No expenses found for this period." empty-state message
16. ₹ symbol present in all rendered amounts regardless of active filter state
17. Query helper unit tests (get_summary_stats, get_recent_transactions,
    get_category_breakdown): accept date_from/date_to kwargs, filter correctly,
    return correct shapes, percentages sum to 100, SQL injection is safely handled
"""

import calendar
import os
import re
import tempfile
from datetime import date, datetime, timedelta

import pytest
from werkzeug.security import generate_password_hash

# ---------------------------------------------------------------------------
# DB isolation: redirect all connections to a temp file before importing app
# so that init_db() / seed_db() at module level do not touch spendly.db.
# ---------------------------------------------------------------------------
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()


@pytest.fixture(scope="session", autouse=True)
def _cleanup_tmp_db():
    yield
    try:
        os.unlink(_tmp_db.name)
    except OSError:
        pass


import database.db as _db_module  # noqa: E402

_db_module.DB_PATH = _tmp_db.name  # patch before app import

from app import app  # noqa: E402
from database.db import create_user, get_db, init_db  # noqa: E402
from database.queries import (  # noqa: E402
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
)

# ---------------------------------------------------------------------------
# Date constants (computed once at module load; all relative to today so the
# tests remain valid regardless of when they run)
# ---------------------------------------------------------------------------
TODAY = date.today()
TODAY_STR = TODAY.isoformat()

THIS_MONTH_FROM = TODAY.replace(day=1).isoformat()
THIS_MONTH_TO = TODAY.replace(
    day=calendar.monthrange(TODAY.year, TODAY.month)[1]
).isoformat()


def _months_ago_first(n: int) -> str:
    """Return the ISO date of the first day of the month n months ago.
    Mirrors app.py:_months_ago — kept here for test-file isolation.
    """
    m, y = TODAY.month - n, TODAY.year
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1).isoformat()


LAST_3_FROM = _months_ago_first(3)
LAST_6_FROM = _months_ago_first(6)

# Expense dates chosen so their placement relative to presets is unambiguous:
#   EXPENSE_DATE_CURRENT_MONTH  → first day of current month (in "This Month")
#   EXPENSE_DATE_4M_AGO         → first day 4 months ago    (in "Last 6 Months", may or
#                                  may not be in "Last 3 Months" depending on calendar)
#   EXPENSE_DATE_8M_AGO         → first day 8 months ago    (only in "All Time")
EXPENSE_DATE_CURRENT_MONTH = TODAY.replace(day=1).isoformat()
EXPENSE_DATE_4M_AGO = _months_ago_first(4)
EXPENSE_DATE_8M_AGO = _months_ago_first(8)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _reset_db():
    """Wipe and rebuild tables; return the new test user_id."""
    init_db()
    conn = get_db()
    conn.execute("DELETE FROM expenses")
    conn.execute("DELETE FROM users")
    conn.commit()

    cur = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Test User", "test@spendly.com", generate_password_hash("password123")),
    )
    user_id = cur.lastrowid

    expenses = [
        # current month: 500 + 200 = 700, categories Food + Transport
        (user_id, 500.00, "Food",      EXPENSE_DATE_CURRENT_MONTH, "Groceries this month"),
        (user_id, 200.00, "Transport", EXPENSE_DATE_CURRENT_MONTH, "Metro this month"),
        # 4 months ago: 1000, category Bills
        (user_id, 1000.00, "Bills",    EXPENSE_DATE_4M_AGO,        "Old electricity bill"),
        # 8 months ago: 750, category Shopping (only visible in All Time)
        (user_id, 750.00, "Shopping",  EXPENSE_DATE_8M_AGO,        "Ancient shopping"),
    ]
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) "
        "VALUES (?, ?, ?, ?, ?)",
        expenses,
    )
    conn.commit()
    conn.close()
    return user_id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    """
    Fresh Flask test client backed by a clean temp-file DB.
    Yields (flask_test_client, user_id) and tears down DB state after each test.
    """
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False

    with app.test_client() as c:
        with app.app_context():
            user_id = _reset_db()
        yield c, user_id

    # Cleanup after each test
    with app.app_context():
        conn = get_db()
        conn.execute("DELETE FROM expenses")
        conn.execute("DELETE FROM users")
        conn.commit()
        conn.close()


def _login(c, email="test@spendly.com", password="password123"):
    return c.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=True,
    )


# ===========================================================================
# 1. Auth guard
# ===========================================================================

class TestAuthGuard:
    def test_unauthenticated_get_profile_redirects_to_login(self, client):
        """Unauthenticated GET /profile must 302-redirect to /login."""
        c, _ = client
        resp = c.get("/profile", follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_unauthenticated_get_profile_with_date_params_redirects_to_login(self, client):
        """Auth guard must apply even when date filter params are present."""
        c, _ = client
        resp = c.get(
            f"/profile?date_from={THIS_MONTH_FROM}&date_to={THIS_MONTH_TO}",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]


# ===========================================================================
# 2. Unfiltered / All Time view (no query params)
# ===========================================================================

class TestUnfilteredView:
    def test_no_params_returns_200(self, client):
        c, _ = client
        _login(c)
        assert c.get("/profile").status_code == 200

    def test_no_params_shows_all_four_seeded_expenses(self, client):
        c, _ = client
        _login(c)
        body = c.get("/profile").data.decode()
        for desc in ("Groceries this month", "Metro this month",
                     "Old electricity bill", "Ancient shopping"):
            assert desc in body, f"Expected '{desc}' in unfiltered profile body"

    def test_no_params_all_time_button_carries_active_class(self, client):
        """The 'All Time' preset button must be marked active when no filter is set."""
        c, _ = client
        _login(c)
        body = c.get("/profile").data.decode()
        # Find the active-class marker and check 'All Time' is nearby
        assert "filter-preset-btn--active" in body
        idx = body.index("filter-preset-btn--active")
        assert "All Time" in body[idx: idx + 100]

    def test_no_params_total_spent_is_sum_of_all_expenses(self, client):
        """Total: 500 + 200 + 1000 + 750 = 2 450.00."""
        c, _ = client
        _login(c)
        body = c.get("/profile").data.decode()
        assert "2,450.00" in body

    def test_no_params_transaction_count_is_four(self, client):
        c, _ = client
        _login(c)
        body = c.get("/profile").data.decode()
        counts = re.findall(r'class="stat-value">\s*(\d+)\s*<', body)
        assert "4" in counts

    def test_all_time_clean_url_produces_same_result_as_no_params(self, client):
        """The 'All Time' preset link points to /profile with no date params."""
        c, _ = client
        _login(c)
        body = c.get("/profile").data.decode()
        # The clean /profile href must appear (All Time preset link)
        assert 'href="/profile"' in body


# ===========================================================================
# 3 & 4 & 5. Valid date range — filtering, boundaries, exclusions
# ===========================================================================

class TestValidDateRange:
    def test_expenses_outside_range_are_excluded(self, client):
        c, _ = client
        _login(c)
        resp = c.get(f"/profile?date_from={THIS_MONTH_FROM}&date_to={THIS_MONTH_TO}")
        body = resp.data.decode()
        assert "Groceries this month" in body
        assert "Metro this month" in body
        assert "Old electricity bill" not in body
        assert "Ancient shopping" not in body

    def test_boundary_inclusive_date_from_is_included(self, client):
        """An expense on exactly date_from must be returned."""
        c, _ = client
        _login(c)
        resp = c.get(
            f"/profile?date_from={EXPENSE_DATE_CURRENT_MONTH}"
            f"&date_to={EXPENSE_DATE_CURRENT_MONTH}"
        )
        body = resp.data.decode()
        assert "Groceries this month" in body
        assert "Metro this month" in body

    def test_boundary_exclusive_day_before_from_is_excluded(self, client):
        """An expense one day before date_from must not appear."""
        c, _ = client
        _login(c)
        # Use a range starting one day after current month start
        day_after = (date.fromisoformat(EXPENSE_DATE_CURRENT_MONTH) + timedelta(days=1)).isoformat()
        resp = c.get(f"/profile?date_from={day_after}&date_to={THIS_MONTH_TO}")
        body = resp.data.decode()
        # Expenses seeded on the first of the month should not appear
        assert "Groceries this month" not in body

    def test_filtered_total_matches_only_in_range_amounts(self, client):
        """Total Spent must equal only the sum of in-range expenses."""
        c, _ = client
        _login(c)
        resp = c.get(
            f"/profile?date_from={EXPENSE_DATE_CURRENT_MONTH}"
            f"&date_to={EXPENSE_DATE_CURRENT_MONTH}"
        )
        body = resp.data.decode()
        # 500 + 200 = 700
        assert "700.00" in body
        # The all-time total 2,450.00 must not appear as the filtered total
        assert "2,450.00" not in body

    def test_filtered_transaction_count_reflects_in_range_rows(self, client):
        c, _ = client
        _login(c)
        resp = c.get(
            f"/profile?date_from={EXPENSE_DATE_CURRENT_MONTH}"
            f"&date_to={EXPENSE_DATE_CURRENT_MONTH}"
        )
        body = resp.data.decode()
        counts = re.findall(r'class="stat-value">\s*(\d+)\s*<', body)
        assert "2" in counts

    def test_category_breakdown_scoped_to_active_filter(self, client):
        """Category breakdown must only include categories present in the filtered range."""
        c, _ = client
        _login(c)
        resp = c.get(
            f"/profile?date_from={EXPENSE_DATE_CURRENT_MONTH}"
            f"&date_to={EXPENSE_DATE_CURRENT_MONTH}"
        )
        body = resp.data.decode()
        assert "Food" in body
        assert "Transport" in body
        assert "Bills" not in body
        assert "Shopping" not in body

    def test_custom_date_inputs_pre_filled_when_filter_active(self, client):
        """Active date_from and date_to must pre-populate the custom date input fields."""
        c, _ = client
        _login(c)
        d_from = EXPENSE_DATE_4M_AGO
        d_to = EXPENSE_DATE_CURRENT_MONTH
        resp = c.get(f"/profile?date_from={d_from}&date_to={d_to}")
        body = resp.data.decode()
        assert f'value="{d_from}"' in body
        assert f'value="{d_to}"' in body


# ===========================================================================
# 6–8. Preset buttons — dates in page and active-class highlighting
# ===========================================================================

class TestPresetButtons:
    def test_this_month_preset_dates_appear_in_page(self, client):
        """Preset link hrefs must contain the correct first/last day of the month."""
        c, _ = client
        _login(c)
        body = c.get("/profile").data.decode()
        assert THIS_MONTH_FROM in body
        assert THIS_MONTH_TO in body

    def test_this_month_button_active_when_dates_match(self, client):
        c, _ = client
        _login(c)
        resp = c.get(f"/profile?date_from={THIS_MONTH_FROM}&date_to={THIS_MONTH_TO}")
        body = resp.data.decode()
        idx = body.index("filter-preset-btn--active")
        assert "This Month" in body[idx: idx + 100]

    def test_last_3_months_preset_dates_appear_in_page(self, client):
        c, _ = client
        _login(c)
        body = c.get("/profile").data.decode()
        assert LAST_3_FROM in body

    def test_last_3_months_button_active_when_dates_match(self, client):
        c, _ = client
        _login(c)
        resp = c.get(f"/profile?date_from={LAST_3_FROM}&date_to={TODAY_STR}")
        body = resp.data.decode()
        idx = body.index("filter-preset-btn--active")
        assert "Last 3 Months" in body[idx: idx + 120]

    def test_last_6_months_preset_dates_appear_in_page(self, client):
        c, _ = client
        _login(c)
        body = c.get("/profile").data.decode()
        assert LAST_6_FROM in body

    def test_last_6_months_button_active_when_dates_match(self, client):
        c, _ = client
        _login(c)
        resp = c.get(f"/profile?date_from={LAST_6_FROM}&date_to={TODAY_STR}")
        body = resp.data.decode()
        idx = body.index("filter-preset-btn--active")
        assert "Last 6 Months" in body[idx: idx + 120]

    def test_last_6_months_includes_4_month_old_expense(self, client):
        """4-months-ago expense is inside the 6-month window."""
        c, _ = client
        _login(c)
        resp = c.get(f"/profile?date_from={LAST_6_FROM}&date_to={TODAY_STR}")
        body = resp.data.decode()
        assert "Old electricity bill" in body

    def test_last_6_months_excludes_8_month_old_expense(self, client):
        """8-months-ago expense is outside the 6-month window."""
        c, _ = client
        _login(c)
        resp = c.get(f"/profile?date_from={LAST_6_FROM}&date_to={TODAY_STR}")
        body = resp.data.decode()
        assert "Ancient shopping" not in body

    def test_last_3_months_excludes_8_month_old_expense(self, client):
        c, _ = client
        _login(c)
        resp = c.get(f"/profile?date_from={LAST_3_FROM}&date_to={TODAY_STR}")
        body = resp.data.decode()
        assert "Ancient shopping" not in body


# ===========================================================================
# 11. date_from > date_to — flash error + unfiltered fallback
# ===========================================================================

class TestInvalidDateOrder:
    _URL = "/profile?date_from=2026-12-31&date_to=2026-01-01"

    def _get(self, c):
        return c.get(self._URL, follow_redirects=True)

    def test_inverted_range_returns_200(self, client):
        c, _ = client
        _login(c)
        assert self._get(c).status_code == 200

    def test_inverted_range_flashes_exact_error_message(self, client):
        """Spec requires the exact message 'Start date must be before end date.'"""
        c, _ = client
        _login(c)
        assert "Start date must be before end date." in self._get(c).data.decode()

    def test_inverted_range_falls_back_to_all_expenses(self, client):
        """After the error the unfiltered view must show every expense."""
        c, _ = client
        _login(c)
        body = self._get(c).data.decode()
        for desc in ("Groceries this month", "Metro this month",
                     "Old electricity bill", "Ancient shopping"):
            assert desc in body

    def test_inverted_range_unfiltered_total_is_displayed(self, client):
        """The total after error fallback must be the all-time total 2,450.00."""
        c, _ = client
        _login(c)
        assert "2,450.00" in self._get(c).data.decode()


# ===========================================================================
# 12. date_from == date_to — valid single-day range
# ===========================================================================

class TestSingleDayRange:
    def test_same_day_range_does_not_flash_error(self, client):
        c, _ = client
        _login(c)
        resp = c.get(
            f"/profile?date_from={EXPENSE_DATE_CURRENT_MONTH}"
            f"&date_to={EXPENSE_DATE_CURRENT_MONTH}",
            follow_redirects=True,
        )
        assert "Start date must be before end date." not in resp.data.decode()

    def test_same_day_range_shows_only_that_days_expenses(self, client):
        c, _ = client
        _login(c)
        resp = c.get(
            f"/profile?date_from={EXPENSE_DATE_CURRENT_MONTH}"
            f"&date_to={EXPENSE_DATE_CURRENT_MONTH}",
        )
        body = resp.data.decode()
        assert "Groceries this month" in body
        assert "Old electricity bill" not in body


# ===========================================================================
# 13. Malformed date strings — no crash, unfiltered fallback
# ===========================================================================

class TestMalformedDates:
    def test_malformed_date_from_does_not_crash(self, client):
        c, _ = client
        _login(c)
        resp = c.get(f"/profile?date_from=not-a-date&date_to={TODAY_STR}")
        assert resp.status_code == 200

    def test_malformed_date_to_does_not_crash(self, client):
        c, _ = client
        _login(c)
        resp = c.get(f"/profile?date_from={THIS_MONTH_FROM}&date_to=99999-99-99")
        assert resp.status_code == 200

    def test_both_malformed_does_not_crash(self, client):
        c, _ = client
        _login(c)
        assert c.get("/profile?date_from=abc&date_to=xyz").status_code == 200

    def test_malformed_date_falls_back_to_all_expenses(self, client):
        """Malformed params are silently dropped; all expenses must appear."""
        c, _ = client
        _login(c)
        resp = c.get(f"/profile?date_from=not-a-date&date_to={TODAY_STR}")
        body = resp.data.decode()
        for desc in ("Groceries this month", "Old electricity bill", "Ancient shopping"):
            assert desc in body

    @pytest.mark.parametrize("bad_from,bad_to", [
        ("not-a-date",  TODAY_STR),
        (TODAY_STR,     "not-a-date"),
        ("2026/04/01",  TODAY_STR),
        ("01-04-2026",  TODAY_STR),
        ("20260401",    TODAY_STR),
        ("",            TODAY_STR),
        (TODAY_STR,     ""),
        ("null",        TODAY_STR),
        ("'; DROP TABLE expenses; --", TODAY_STR),
        (TODAY_STR, "'; DROP TABLE users; --"),
    ])
    def test_various_malformed_date_inputs_do_not_crash(self, client, bad_from, bad_to):
        """Each combination of bad date values must return HTTP 200."""
        c, _ = client
        _login(c)
        resp = c.get(
            "/profile",
            query_string={"date_from": bad_from, "date_to": bad_to},
            follow_redirects=True,
        )
        assert resp.status_code == 200


# ===========================================================================
# 14. Partial filter (only one param supplied)
# ===========================================================================

class TestPartialFilter:
    def test_only_date_from_falls_back_to_unfiltered(self, client):
        """Without date_to the filter must not activate; all expenses shown."""
        c, _ = client
        _login(c)
        resp = c.get(f"/profile?date_from={THIS_MONTH_FROM}")
        body = resp.data.decode()
        assert "Groceries this month" in body
        assert "Ancient shopping" in body

    def test_only_date_to_falls_back_to_unfiltered(self, client):
        c, _ = client
        _login(c)
        resp = c.get(f"/profile?date_to={TODAY_STR}")
        body = resp.data.decode()
        assert "Groceries this month" in body
        assert "Ancient shopping" in body


# ===========================================================================
# 15. Empty period — no expenses in selected range
# ===========================================================================

class TestEmptyPeriod:
    _EMPTY_FROM = "2000-01-01"
    _EMPTY_TO   = "2000-01-31"

    def _get(self, c):
        return c.get(
            f"/profile?date_from={self._EMPTY_FROM}&date_to={self._EMPTY_TO}"
        )

    def test_empty_period_returns_200(self, client):
        c, _ = client
        _login(c)
        assert self._get(c).status_code == 200

    def test_empty_period_shows_empty_state_message(self, client):
        c, _ = client
        _login(c)
        assert "No expenses found for this period." in self._get(c).data.decode()

    def test_empty_period_total_spent_is_zero(self, client):
        c, _ = client
        _login(c)
        assert "0.00" in self._get(c).data.decode()

    def test_empty_period_transaction_count_is_zero(self, client):
        c, _ = client
        _login(c)
        body = self._get(c).data.decode()
        counts = re.findall(r'class="stat-value">\s*(\d+)\s*<', body)
        assert "0" in counts

    def test_empty_period_top_category_is_em_dash(self, client):
        """Top Category must display '—' (em dash) when there are no expenses."""
        c, _ = client
        _login(c)
        assert "—" in self._get(c).data.decode()

    def test_user_with_zero_expenses_returns_200(self, client):
        """A brand-new user with no expenses at all must not trigger any error."""
        c, _ = client
        # Register and log in as a second user who has no expenses
        with app.app_context():
            create_user("Empty User", "empty@spendly.com", "test-only-not-real-abc123!")
        c.post(
            "/login",
            data={"email": "empty@spendly.com", "password": "test-only-not-real-abc123!"},
            follow_redirects=True,
        )
        resp = c.get("/profile?date_from=2025-01-01&date_to=2025-12-31")
        assert resp.status_code == 200
        body = resp.data.decode()
        assert "0.00" in body


# ===========================================================================
# 16. ₹ symbol present in all filter states
# ===========================================================================

class TestRupeeSymbol:
    def test_rupee_present_with_no_filter(self, client):
        c, _ = client
        _login(c)
        assert "₹" in c.get("/profile").data.decode()

    def test_rupee_present_with_active_filter(self, client):
        c, _ = client
        _login(c)
        resp = c.get(
            f"/profile?date_from={EXPENSE_DATE_CURRENT_MONTH}"
            f"&date_to={EXPENSE_DATE_CURRENT_MONTH}"
        )
        assert "₹" in resp.data.decode()

    def test_rupee_present_on_empty_period(self, client):
        c, _ = client
        _login(c)
        resp = c.get("/profile?date_from=2000-01-01&date_to=2000-01-31")
        assert "₹" in resp.data.decode()

    def test_dollar_sign_never_appears(self, client):
        c, _ = client
        _login(c)
        assert "$" not in c.get("/profile").data.decode()


# ===========================================================================
# 17. Query helper unit tests (called directly, bypassing HTTP layer)
# ===========================================================================

class TestQueryHelpers:
    """
    Validate the three query functions independently against the same seeded DB.
    These tests confirm signature, return shape, filtering correctness, and
    that parameterized queries survive SQL injection inputs without crashing.
    """

    # --- get_summary_stats ---

    def test_summary_stats_accepts_none_date_kwargs(self, client):
        _, uid = client
        with app.app_context():
            result = get_summary_stats(uid, date_from=None, date_to=None)
        assert {"total", "count", "top_category"} <= result.keys()

    def test_summary_stats_no_filter_returns_all(self, client):
        _, uid = client
        with app.app_context():
            result = get_summary_stats(uid)
        assert result["total"] == "2,450.00"
        assert result["count"] == 4

    def test_summary_stats_filtered_returns_subset(self, client):
        _, uid = client
        with app.app_context():
            result = get_summary_stats(
                uid,
                date_from=EXPENSE_DATE_CURRENT_MONTH,
                date_to=EXPENSE_DATE_CURRENT_MONTH,
            )
        assert result["total"] == "700.00"
        assert result["count"] == 2

    def test_summary_stats_empty_range_returns_zeros(self, client):
        _, uid = client
        with app.app_context():
            result = get_summary_stats(uid, date_from="2000-01-01", date_to="2000-01-31")
        assert result["total"] == "0.00"
        assert result["count"] == 0
        assert result["top_category"] == "—"

    def test_summary_stats_top_category_reflects_filter(self, client):
        """Within the current-month filter the top category by spend is Food (500)."""
        _, uid = client
        with app.app_context():
            result = get_summary_stats(
                uid,
                date_from=EXPENSE_DATE_CURRENT_MONTH,
                date_to=EXPENSE_DATE_CURRENT_MONTH,
            )
        assert result["top_category"] == "Food"

    def test_summary_stats_sql_injection_in_date_param_does_not_crash(self, client):
        """Parameterized queries must silently return 0 rows, not raise an exception."""
        _, uid = client
        with app.app_context():
            result = get_summary_stats(
                uid,
                date_from="'; DROP TABLE expenses; --",
                date_to=TODAY_STR,
            )
        assert result["count"] == 0

    # --- get_recent_transactions ---

    def test_recent_transactions_accepts_none_date_kwargs(self, client):
        _, uid = client
        with app.app_context():
            result = get_recent_transactions(uid, date_from=None, date_to=None)
        assert isinstance(result, list)

    def test_recent_transactions_no_filter_returns_all_four(self, client):
        _, uid = client
        with app.app_context():
            result = get_recent_transactions(uid)
        assert len(result) == 4

    def test_recent_transactions_filtered_returns_correct_rows(self, client):
        _, uid = client
        with app.app_context():
            result = get_recent_transactions(
                uid,
                date_from=EXPENSE_DATE_CURRENT_MONTH,
                date_to=EXPENSE_DATE_CURRENT_MONTH,
            )
        assert len(result) == 2
        descs = {tx["description"] for tx in result}
        assert "Groceries this month" in descs
        assert "Metro this month" in descs

    def test_recent_transactions_has_required_keys(self, client):
        _, uid = client
        with app.app_context():
            result = get_recent_transactions(uid)
        for tx in result:
            assert {"date", "description", "category", "amount"} <= tx.keys()

    def test_recent_transactions_amount_is_formatted_string(self, client):
        """Amounts must be human-readable strings (e.g. '500.00'), not raw floats."""
        _, uid = client
        with app.app_context():
            result = get_recent_transactions(uid)
        for tx in result:
            assert isinstance(tx["amount"], str)
            float(tx["amount"].replace(",", ""))  # must be parseable

    def test_recent_transactions_ordered_date_descending(self, client):
        _, uid = client
        with app.app_context():
            result = get_recent_transactions(uid)
        parsed_dates = [datetime.strptime(tx["date"], "%d %b %Y") for tx in result]
        assert parsed_dates == sorted(parsed_dates, reverse=True)

    def test_recent_transactions_empty_range_returns_empty_list(self, client):
        _, uid = client
        with app.app_context():
            result = get_recent_transactions(
                uid, date_from="2000-01-01", date_to="2000-01-31"
            )
        assert result == []

    def test_recent_transactions_sql_injection_does_not_crash(self, client):
        _, uid = client
        with app.app_context():
            result = get_recent_transactions(
                uid,
                date_from="'; DROP TABLE expenses; --",
                date_to=TODAY_STR,
            )
        assert result == []

    # --- get_category_breakdown ---

    def test_category_breakdown_accepts_none_date_kwargs(self, client):
        _, uid = client
        with app.app_context():
            result = get_category_breakdown(uid, date_from=None, date_to=None)
        assert isinstance(result, list)

    def test_category_breakdown_no_filter_includes_all_categories(self, client):
        _, uid = client
        with app.app_context():
            result = get_category_breakdown(uid)
        names = {cat["name"] for cat in result}
        assert {"Food", "Transport", "Bills", "Shopping"} <= names

    def test_category_breakdown_filtered_excludes_out_of_range_categories(self, client):
        _, uid = client
        with app.app_context():
            result = get_category_breakdown(
                uid,
                date_from=EXPENSE_DATE_CURRENT_MONTH,
                date_to=EXPENSE_DATE_CURRENT_MONTH,
            )
        names = {cat["name"] for cat in result}
        assert "Food" in names
        assert "Transport" in names
        assert "Bills" not in names
        assert "Shopping" not in names

    def test_category_breakdown_has_required_keys(self, client):
        _, uid = client
        with app.app_context():
            result = get_category_breakdown(uid)
        for cat in result:
            assert {"name", "amount", "percent"} <= cat.keys()

    def test_category_breakdown_percentages_sum_to_100(self, client):
        _, uid = client
        with app.app_context():
            result = get_category_breakdown(uid)
        if result:
            assert sum(cat["percent"] for cat in result) == 100

    def test_category_breakdown_amount_is_formatted_string(self, client):
        _, uid = client
        with app.app_context():
            result = get_category_breakdown(uid)
        for cat in result:
            assert isinstance(cat["amount"], str)
            float(cat["amount"].replace(",", ""))

    def test_category_breakdown_empty_range_returns_empty_list(self, client):
        _, uid = client
        with app.app_context():
            result = get_category_breakdown(
                uid, date_from="2000-01-01", date_to="2000-01-31"
            )
        assert result == []

    def test_category_breakdown_sql_injection_does_not_crash(self, client):
        _, uid = client
        with app.app_context():
            result = get_category_breakdown(
                uid,
                date_from="'; DROP TABLE expenses; --",
                date_to=TODAY_STR,
            )
        assert result == []
