# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app (http://127.0.0.1:5001)
python app.py

# Run all tests
pytest

# Run a single test file
pytest tests/test_auth.py

# Run a single test
pytest tests/test_auth.py::test_login
```

On this Windows machine, use `python` (not `python3`).

## Architecture

**Spendly** is a Flask expense tracker being built incrementally in steps. Many routes in `app.py` are stubs (e.g., `"coming in Step X"`) awaiting implementation.

### Request flow

1. Browser hits a URL → `app.py` matches the route
2. Route calls `render_template()` → Flask loads HTML from `templates/`
3. All pages extend `templates/base.html` (provides navbar, footer, CSS/JS links)
4. `static/css/style.css` and `static/js/main.js` are served directly to the browser
5. Database access goes through `database/db.py`

### Database layer (`database/db.py`)

Currently a stub. Must implement three functions:
- `get_db()` — returns a SQLite connection with `row_factory` set and foreign keys enabled
- `init_db()` — creates all tables using `CREATE TABLE IF NOT EXISTS`
- `seed_db()` — inserts sample data for development

The database file will be `expense_tracker.db` (already in `.gitignore`).

### Implemented vs. stub routes

Fully rendered (templates exist):
- `GET /` → `landing.html`
- `GET /register` → `register.html`
- `GET /login` → `login.html`
- `GET /terms` → `terms.html`
- `GET /privacy` → `privacy.html`

Stubs to be implemented:
- `GET /logout` (Step 3)
- `GET /profile` (Step 4)
- `GET /expenses/add` (Step 7)
- `GET /expenses/<id>/edit` (Step 8)
- `GET /expenses/<id>/delete` (Step 9)
