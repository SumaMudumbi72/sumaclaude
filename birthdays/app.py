import calendar
import os
import smtplib
import sqlite3
from datetime import date
from email.message import EmailMessage

import click
from flask import Flask, abort, flash, g, redirect, render_template, request, url_for

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["DATABASE"] = os.environ.get(
    "DATABASE", os.path.join(app.root_path, "birthdays.db")
)

UPCOMING_DAYS = 30
MONTHS = list(calendar.month_name)[1:]


# --- Database ------------------------------------------------------------


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS birthdays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
            day INTEGER NOT NULL CHECK (day BETWEEN 1 AND 31),
            year INTEGER,
            notes TEXT NOT NULL DEFAULT ''
        );
        -- Remembers which reminders went out, so none are sent twice.
        CREATE TABLE IF NOT EXISTS reminders_sent (
            birthday_id INTEGER NOT NULL REFERENCES birthdays(id) ON DELETE CASCADE,
            occurrence TEXT NOT NULL,
            days_before INTEGER NOT NULL,
            PRIMARY KEY (birthday_id, occurrence, days_before)
        );
        """
    )
    db.commit()


with app.app_context():
    init_db()


# --- Dates ---------------------------------------------------------------


def birthday_in_year(month, day, year):
    # Feb 29 birthdays are celebrated on Feb 28 in non-leap years.
    if month == 2 and day == 29 and not calendar.isleap(year):
        return date(year, 2, 28)
    return date(year, month, day)


def next_birthday(month, day, today):
    this_year = birthday_in_year(month, day, today.year)
    return this_year if this_year >= today else birthday_in_year(month, day, today.year + 1)


def with_next_dates(rows, today):
    """Add next date, days until, and upcoming age to each birthday, soonest first."""
    result = []
    for row in rows:
        upcoming = next_birthday(row["month"], row["day"], today)
        result.append(
            {
                **dict(row),
                "next_date": upcoming,
                "days_until": (upcoming - today).days,
                "turning": upcoming.year - row["year"] if row["year"] else None,
            }
        )
    return sorted(result, key=lambda b: (b["days_until"], b["name"].lower()))


def all_birthdays(today):
    return with_next_dates(get_db().execute("SELECT * FROM birthdays").fetchall(), today)


@app.template_filter("when")
def when(days):
    if days == 0:
        return "Today!"
    if days == 1:
        return "Tomorrow"
    return f"In {days} days"


@app.template_filter("pretty_date")
def pretty_date(d):
    return f"{d:%a}, {d:%b} {d.day}"


def ordinal(n):
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


app.jinja_env.filters["ordinal"] = ordinal


# --- Form handling -------------------------------------------------------


def parse_form(form, today):
    errors = []
    name = form.get("name", "").strip()
    notes = form.get("notes", "").strip()
    if not name or len(name) > 100:
        errors.append("Name is required (100 characters max).")
    if len(notes) > 200:
        errors.append("Notes must be 200 characters or fewer.")

    try:
        month = int(form.get("month", ""))
        day = int(form.get("day", ""))
        # 2000 is a leap year, so Feb 29 counts as a valid birthday.
        date(2000, month, day)
    except ValueError:
        month = day = None
        errors.append("Choose a valid month and day.")

    # The birth year is optional; it's only used to show ages.
    year_raw = form.get("year", "").strip()
    year = None
    if year_raw:
        try:
            year = int(year_raw)
        except ValueError:
            errors.append("Year must be a number.")
        else:
            if not 1900 <= year <= today.year:
                errors.append(f"Year must be between 1900 and {today.year}.")
            elif month and (month, day) == (2, 29) and not calendar.isleap(year):
                errors.append(f"{year} wasn't a leap year, so there was no Feb 29.")
            elif month and date(year, month, day) > today:
                errors.append("That birthday is in the future.")

    data = {"name": name, "month": month, "day": day, "year": year, "notes": notes}
    return data, errors


# --- Email reminders -----------------------------------------------------


def email_settings():
    env = os.environ.get
    try:
        lead_days = sorted(
            {int(d) for d in env("REMINDER_DAYS", "7,1,0").split(",") if d.strip()},
            reverse=True,
        )
    except ValueError:
        lead_days = [7, 1, 0]
    try:
        port = int(env("SMTP_PORT", "587"))
    except ValueError:
        port = 587
    settings = {
        "host": env("SMTP_HOST", ""),
        "port": port,
        "user": env("SMTP_USER", ""),
        "password": env("SMTP_PASSWORD", ""),
        "sender": env("REMINDER_FROM") or env("SMTP_USER", ""),
        "to": env("REMINDER_TO", ""),
        "lead_days": lead_days,
    }
    settings["configured"] = bool(settings["host"] and settings["sender"] and settings["to"])
    return settings


def due_reminders(today, lead_days):
    """Birthdays that need a reminder today and haven't had this one yet."""
    db = get_db()
    due = []
    for b in all_birthdays(today):
        if b["days_until"] not in lead_days:
            continue
        already = db.execute(
            "SELECT 1 FROM reminders_sent WHERE birthday_id = ? AND occurrence = ? AND days_before = ?",
            (b["id"], b["next_date"].isoformat(), b["days_until"]),
        ).fetchone()
        if not already:
            due.append(b)
    return due


def build_email(due, settings):
    def line(b):
        age = f", turning {b['turning']}" if b["turning"] else ""
        note = f" ({b['notes']})" if b["notes"] else ""
        return f"- {b['name']}: {when(b['days_until'])}, {pretty_date(b['next_date'])}{age}{note}"

    summary = ", ".join(f"{b['name']} {when(b['days_until']).lower()}" for b in due)
    msg = EmailMessage()
    msg["Subject"] = f"Birthday reminder: {summary}"
    msg["From"] = settings["sender"]
    msg["To"] = settings["to"]
    msg.set_content(
        "Upcoming birthdays:\n\n" + "\n".join(line(b) for b in due) + "\n\n— Birthday Reminder\n"
    )
    return msg


def send_email(msg, settings):
    if settings["port"] == 465:
        server = smtplib.SMTP_SSL(settings["host"], settings["port"], timeout=20)
    else:
        server = smtplib.SMTP(settings["host"], settings["port"], timeout=20)
    with server:
        if settings["port"] != 465:
            server.starttls()
        if settings["user"]:
            server.login(settings["user"], settings["password"])
        server.send_message(msg)


def send_reminders(today=None):
    """Email any reminders due today. Returns a message describing what happened."""
    today = today or date.today()
    settings = email_settings()
    if not settings["configured"]:
        return False, "Email isn't set up. See the README for the SMTP settings."

    due = due_reminders(today, settings["lead_days"])
    if not due:
        return True, "No reminders due today."

    try:
        send_email(build_email(due, settings), settings)
    except (smtplib.SMTPException, OSError) as exc:
        return False, f"Couldn't send the email: {exc}"

    db = get_db()
    db.executemany(
        "INSERT OR IGNORE INTO reminders_sent (birthday_id, occurrence, days_before) VALUES (?, ?, ?)",
        [(b["id"], b["next_date"].isoformat(), b["days_until"]) for b in due],
    )
    db.commit()
    names = ", ".join(b["name"] for b in due)
    return True, f"Sent a reminder to {settings['to']} for {names}."


@app.cli.command("send-reminders")
def send_reminders_command():
    """Email reminders for upcoming birthdays (run once a day)."""
    ok, message = send_reminders()
    click.echo(message)
    if not ok:
        raise SystemExit(1)


# --- Routes --------------------------------------------------------------


@app.route("/")
def index():
    today = date.today()
    birthdays = all_birthdays(today)
    settings = email_settings()
    return render_template(
        "index.html",
        birthdays=birthdays,
        upcoming=[b for b in birthdays if b["days_until"] <= UPCOMING_DAYS],
        upcoming_days=UPCOMING_DAYS,
        months=MONTHS,
        email=settings,
        form={},
    )


@app.route("/add", methods=["POST"])
def add():
    data, errors = parse_form(request.form, date.today())
    if errors:
        for error in errors:
            flash(error, "error")
    else:
        db = get_db()
        db.execute(
            "INSERT INTO birthdays (name, month, day, year, notes) VALUES (:name, :month, :day, :year, :notes)",
            data,
        )
        db.commit()
        flash(f"Added {data['name']}'s birthday.", "success")
    return redirect(url_for("index"))


def get_birthday(birthday_id):
    row = get_db().execute("SELECT * FROM birthdays WHERE id = ?", (birthday_id,)).fetchone()
    if row is None:
        abort(404)
    return row


@app.route("/edit/<int:birthday_id>", methods=["GET", "POST"])
def edit(birthday_id):
    row = get_birthday(birthday_id)
    form = dict(row)
    if request.method == "POST":
        data, errors = parse_form(request.form, date.today())
        if not errors:
            db = get_db()
            db.execute(
                "UPDATE birthdays SET name = :name, month = :month, day = :day, year = :year,"
                " notes = :notes WHERE id = :id",
                {**data, "id": birthday_id},
            )
            db.commit()
            flash(f"Updated {data['name']}'s birthday.", "success")
            return redirect(url_for("index"))
        for error in errors:
            flash(error, "error")
        form = request.form
    return render_template("edit.html", birthday=row, form=form, months=MONTHS)


@app.route("/delete/<int:birthday_id>", methods=["POST"])
def delete(birthday_id):
    row = get_birthday(birthday_id)
    db = get_db()
    db.execute("DELETE FROM birthdays WHERE id = ?", (birthday_id,))
    db.commit()
    flash(f"Deleted {row['name']}'s birthday.", "success")
    return redirect(url_for("index"))


@app.route("/send-reminders", methods=["POST"])
def send_reminders_now():
    ok, message = send_reminders()
    flash(message, "success" if ok else "error")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True, port=5006)
