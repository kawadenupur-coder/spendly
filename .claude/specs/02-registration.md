# Spec: Registration

## Overview

Implement user registration so new visitors can create a Spendly account. This step upgrades the existing stub GET /register route into a fully functional form that accepts a POST, validates input, hashes the password, and inserts a new row into the users table. On success the user is shown with a success message and then redirected to the login page. This is the entry point for all authenticated features that follow.

## Depends on

- Step 1 — Database Setup (`get_db()`, `users` table, `init_db()`)

## Routes

- `GET /register` — render the registration form — public (already exists, no change needed)
- `POST /register` — validate form data, insert user, redirect to login — public

## Database changes

No new tables or columns. The existing `users` table already has all
required columns (`name`, `email`, `password_hash`, `created_at`).

## Templates

- **Modify:** `templates/register.html`
  - Form action must use `url_for('register')` instead of hardcoded `/register`
  - Re-render with `error` message and sticky field values (`name`, `email`) on validation failure

## Files to change

- `app.py` — add `POST` method to the `register` route; add `secret_key`;
  import `redirect`, `url_for`, `request`, `flash` from Flask
- `database/db.py` — add `create_user(name, email, password)` helper
- `templates/register.html` — fix hardcoded action URL; pass `name`/`email` back into inputs on error

## Files to create

None.

## New dependencies

No new pip packages.

## Rules for implementation

- No SQLAlchemy or ORMs — raw `sqlite3` only
- Parameterised queries only — never f-strings in SQL
- Hash passwords with `werkzeug.security.generate_password_hash` — never store plaintext
- Use CSS variables — never hardcode hex values
- All templates must extend `base.html`
- `create_user()` lives in `database/db.py`, not in `app.py`
- Catch `sqlite3.IntegrityError` (duplicate email) in `create_user()` — return `None`
  so the route can re-render the form with an error message
- `app.secret_key` must be set before any session/flash usage — use a fixed dev string
  (e.g. `"spendly-dev-secret"`) for now; note in a comment that this must be an env var in production
- Validate server-side: name non-empty, valid email format (basic check), password ≥ 8 chars
- On success → `redirect(url_for('login'))` (do not log the user in automatically)
- On failure → re-render `register.html` with `error=` and sticky `name`/`email` values
- Use `abort()` for unexpected server errors, not bare string returns

## Definition of done

- [ ] `POST /register` with valid data inserts a new user and redirects to `/login`
- [ ] Password is stored as a hash — never plaintext — verifiable by inspecting `spendly.db`
- [ ] Registering with an already-used email re-renders the form with "Email already registered" error
- [ ] Submitting with an empty name re-renders the form with a validation error
- [ ] Submitting with a password shorter than 8 characters re-renders the form with a validation error
- [ ] Name and email fields retain their values after a failed submission (sticky inputs)
- [ ] Form action in `register.html` uses `url_for('register')`, not a hardcoded URL
- [ ] App starts without errors after changes to `app.py`
- [ ] No raw SQL strings are used in route functions — all DB logic is in `database/db.py`
