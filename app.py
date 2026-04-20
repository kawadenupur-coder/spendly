import sqlite3

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database.db import create_user, get_db, get_user_by_email, init_db, seed_db

app = Flask(__name__)
app.secret_key = "dev-secret-key"

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("profile"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not all([name, email, password, confirm_password]):
            flash("All fields are required.", "error")
            return render_template("register.html")

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("register.html")

        try:
            create_user(name, email, password)
        except sqlite3.IntegrityError:
            flash("Email already registered.", "error")
            return render_template("register.html")

        flash("Account created! Please sign in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        user = get_user_by_email(email)
        if not user or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "error")
            return render_template("login.html")

        session["user_id"] = user["id"]
        session["user_name"] = user["name"]
        return redirect(url_for("profile"))

    return render_template("login.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("landing"))


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user = {
        "name": "Demo User",
        "email": "demo@spendly.com",
        "initials": "DU",
        "member_since": "15 Jan 2025",
    }
    stats = {
        "total": "12,450.75",
        "count": 8,
        "top_category": "Food",
    }
    expenses = [
        {"date": "12 Apr 2025", "description": "Groceries",            "category": "Food",          "amount": "850.00"},
        {"date": "11 Apr 2025", "description": "Metro card recharge",  "category": "Transport",     "amount": "500.00"},
        {"date": "10 Apr 2025", "description": "Electricity bill",     "category": "Bills",         "amount": "2,200.00"},
        {"date": "09 Apr 2025", "description": "Doctor visit",         "category": "Health",        "amount": "800.00"},
        {"date": "08 Apr 2025", "description": "Netflix subscription", "category": "Entertainment", "amount": "649.00"},
        {"date": "07 Apr 2025", "description": "New shoes",            "category": "Shopping",      "amount": "3,200.00"},
        {"date": "05 Apr 2025", "description": "Dinner with friends",  "category": "Food",          "amount": "1,450.00"},
        {"date": "01 Apr 2025", "description": "Miscellaneous",        "category": "Other",         "amount": "2,801.75"},
    ]
    categories = [
        {"name": "Shopping",      "amount": "3,200.00", "percent": 100},
        {"name": "Other",         "amount": "2,801.75", "percent": 88},
        {"name": "Food",          "amount": "2,300.00", "percent": 72},
        {"name": "Bills",         "amount": "2,200.00", "percent": 69},
        {"name": "Health",        "amount": "800.00",   "percent": 25},
        {"name": "Entertainment", "amount": "649.00",   "percent": 20},
        {"name": "Transport",     "amount": "500.00",   "percent": 16},
    ]
    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        expenses=expenses,
        categories=categories,
    )


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
