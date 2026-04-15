# Spec: Login and Logout

## Overview

Implement user login and logout so registered users can authenticate into Spendly.
This step wires the existing `GET /login` form to a `POST /login` handler that looks
up the user by email, verifies the password hash, and stores the user's id in the
Flask session. It also implements `GET /logout` (currently a raw-string stub) which
clears the session and redirects to the landing page. The navbar in `base.html` is
updated to show session-aware links — logged-in users see a logout link instead of
"Sign in / Get started".

## Depends on

- Step 1 — Database Setup (`get_db()`, `users` table)
- Step 2 — Registration (`create_user()`, `app.secret_key` already set)

## Routes

- `GET /login` — render the login form — public (already exists, needs POST added)
- `POST /login` — validate credentials, set session, redirect to `/` — public
- `GET /logout` — clear session, redirect to `/` — public (stub exists, needs implementation)

## Database changes

No new tables or columns. A new helper `get_user_by_email(email)` is needed to look
up a user row — no schema changes required.

## Templates

- **Modify:** `templates/login.html`
  - Fix hardcoded `action="/login"` → `action="{{ url_for('login') }}"`
  - Add sticky `value="{{ email or '' }}"` on the email input for failed submissions

- **Modify:** `templates/base.html`
  - Navbar currently always shows "Sign in" and "Get started"
  - When `session.user_id` is set, replace those links with a "Sign out" link pointing to `url_for('logout')`
  - When not logged in, keep existing links

## Files to change

- `app.py` — add `POST` to `/login`; implement `/logout`; import `session`, `check_password_hash`
- `database/db.py` — add `get_user_by_email(email)` helper
- `templates/login.html` — fix hardcoded action URL; add sticky email input
- `templates/base.html` — session-aware navbar links

## Files to create

None.

## New dependencies

No new pip packages. `check_password_hash` is already available from `werkzeug.security`.

## Rules for implementation

- No SQLAlchemy or ORMs — raw `sqlite3` only
- Parameterised queries only — never f-strings in SQL
- Passwords verified with `werkzeug.security.check_password_hash` — never compare plaintext
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- `get_user_by_email()` lives in `database/db.py`, not in `app.py`
- Store only `session['user_id']` (the integer id) — never store the full user row or password in the session
- On login failure, do not reveal whether the email exists or the password is wrong — use a single generic error: `"Invalid email or password."`
- On successful login → `redirect(url_for('landing'))` (home page, not profile — profile is Step 4)
- On logout → `session.clear()` then `redirect(url_for('landing'))`
- Use `abort(405)` if any route receives an unexpected method

## Definition of done

- [ ] `POST /login` with correct email and password sets `session['user_id']` and redirects to `/`
- [ ] `POST /login` with wrong password re-renders the form with "Invalid email or password." error
- [ ] `POST /login` with unknown email re-renders the form with the same generic error (no email-enumeration)
- [ ] Email field retains its value after a failed login attempt (sticky input)
- [ ] `GET /logout` clears the session and redirects to `/`
- [ ] After logout, visiting `/` does not show the user as logged in
- [ ] Navbar shows "Sign out" link when logged in, and "Sign in / Get started" when logged out
- [ ] Form action in `login.html` uses `url_for('login')`, not a hardcoded URL
- [ ] No raw SQL strings in `app.py` — all DB logic in `database/db.py`
- [ ] App starts without errors after all changes
