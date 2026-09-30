import csv
import io
import os
import sqlite3
from datetime import date
from decimal import Decimal, InvalidOperation

from flask import (
    Flask,
    Response,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["DATABASE"] = os.environ.get(
    "DATABASE", os.path.join(app.root_path, "expenses.db")
)

TYPES = ("income", "expense")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    # Amounts are stored as integer cents to avoid floating-point rounding.
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
            amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
            category TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            date TEXT NOT NULL
        )
        """
    )
    db.commit()


with app.app_context():
    init_db()


@app.template_filter("money")
def money(cents):
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) / 100:,.2f}"


def parse_amount(raw):
    """Return a positive amount in cents, or None if invalid."""
    try:
        value = Decimal(raw.strip())
    except (InvalidOperation, AttributeError):
        return None
    if value <= 0 or value.as_tuple().exponent < -2 or value >= 1_000_000_000:
        return None
    return int(value * 100)


def fetch_transactions(category):
    query = "SELECT * FROM transactions"
    params = ()
    if category:
        query += " WHERE category = ?"
        params = (category,)
    query += " ORDER BY date DESC, id DESC"
    return get_db().execute(query, params).fetchall()


def totals(rows):
    income = sum(r["amount_cents"] for r in rows if r["type"] == "income")
    expense = sum(r["amount_cents"] for r in rows if r["type"] == "expense")
    return {"income": income, "expense": expense, "balance": income - expense}


@app.route("/")
def index():
    category = request.args.get("category", "").strip()
    db = get_db()
    categories = [
        r["category"]
        for r in db.execute(
            "SELECT DISTINCT category FROM transactions ORDER BY category COLLATE NOCASE"
        )
    ]
    rows = fetch_transactions(category)
    overall = totals(db.execute("SELECT type, amount_cents FROM transactions").fetchall())
    return render_template(
        "index.html",
        transactions=rows,
        categories=categories,
        category=category,
        overall=overall,
        filtered=totals(rows),
        today=date.today().isoformat(),
    )


@app.route("/add", methods=["POST"])
def add():
    form = request.form
    tx_type = form.get("type", "")
    amount = parse_amount(form.get("amount", ""))
    category = form.get("category", "").strip()
    description = form.get("description", "").strip()
    tx_date = form.get("date", "").strip() or date.today().isoformat()

    errors = []
    if tx_type not in TYPES:
        errors.append("Choose income or expense.")
    if amount is None:
        errors.append("Amount must be a positive number with at most 2 decimals.")
    if not category or len(category) > 50:
        errors.append("Category is required (50 characters max).")
    if len(description) > 200:
        errors.append("Description must be 200 characters or fewer.")
    try:
        date.fromisoformat(tx_date)
    except ValueError:
        errors.append("Date must be in YYYY-MM-DD format.")

    if errors:
        for error in errors:
            flash(error, "error")
    else:
        db = get_db()
        db.execute(
            "INSERT INTO transactions (type, amount_cents, category, description, date)"
            " VALUES (?, ?, ?, ?, ?)",
            (tx_type, amount, category, description, tx_date),
        )
        db.commit()
        flash(f"{tx_type.capitalize()} added.", "success")
    return redirect(request.referrer or url_for("index"))


@app.route("/delete/<int:tx_id>", methods=["POST"])
def delete(tx_id):
    db = get_db()
    if db.execute("DELETE FROM transactions WHERE id = ?", (tx_id,)).rowcount == 0:
        abort(404)
    db.commit()
    return redirect(request.referrer or url_for("index"))


def csv_safe(value):
    # Stop spreadsheet apps from interpreting user text as a formula.
    if value and value[0] in "=+-@\t\r":
        return "'" + value
    return value


@app.route("/export")
def export():
    category = request.args.get("category", "").strip()
    rows = fetch_transactions(category)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["date", "type", "category", "description", "amount"])
    for r in rows:
        writer.writerow(
            [
                r["date"],
                r["type"],
                csv_safe(r["category"]),
                csv_safe(r["description"]),
                f"{r['amount_cents'] / 100:.2f}",
            ]
        )

    filename = f"transactions-{category or 'all'}.csv".replace(" ", "_")
    filename = "".join(c for c in filename if c.isalnum() or c in "._-")
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


if __name__ == "__main__":
    app.run(debug=True, port=5002)
