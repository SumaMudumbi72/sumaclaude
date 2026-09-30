import os
import sqlite3

from flask import Flask, abort, flash, g, redirect, render_template, request, url_for

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["DATABASE"] = os.environ.get(
    "DATABASE", os.path.join(app.root_path, "todos.db")
)


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
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.commit()


with app.app_context():
    init_db()


def get_todo(todo_id):
    todo = get_db().execute("SELECT * FROM todos WHERE id = ?", (todo_id,)).fetchone()
    if todo is None:
        abort(404)
    return todo


@app.route("/")
def index():
    status = request.args.get("filter", "all")
    query = "SELECT * FROM todos"
    if status == "active":
        query += " WHERE completed = 0"
    elif status == "completed":
        query += " WHERE completed = 1"
    else:
        status = "all"
    query += " ORDER BY completed, created_at DESC"

    db = get_db()
    todos = db.execute(query).fetchall()
    remaining = db.execute("SELECT COUNT(*) FROM todos WHERE completed = 0").fetchone()[0]
    return render_template("index.html", todos=todos, filter=status, remaining=remaining)


@app.route("/add", methods=["POST"])
def add():
    title = request.form.get("title", "").strip()
    if not title:
        flash("Todo cannot be empty.", "error")
    elif len(title) > 200:
        flash("Todo must be 200 characters or fewer.", "error")
    else:
        db = get_db()
        db.execute("INSERT INTO todos (title) VALUES (?)", (title,))
        db.commit()
    return redirect(url_for("index"))


@app.route("/toggle/<int:todo_id>", methods=["POST"])
def toggle(todo_id):
    todo = get_todo(todo_id)
    db = get_db()
    db.execute(
        "UPDATE todos SET completed = ? WHERE id = ?",
        (0 if todo["completed"] else 1, todo_id),
    )
    db.commit()
    return redirect(request.referrer or url_for("index"))


@app.route("/edit/<int:todo_id>", methods=["GET", "POST"])
def edit(todo_id):
    todo = get_todo(todo_id)
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if not title:
            flash("Todo cannot be empty.", "error")
        elif len(title) > 200:
            flash("Todo must be 200 characters or fewer.", "error")
        else:
            db = get_db()
            db.execute("UPDATE todos SET title = ? WHERE id = ?", (title, todo_id))
            db.commit()
            flash("Todo updated.", "success")
            return redirect(url_for("index"))
    return render_template("edit.html", todo=todo)


@app.route("/delete/<int:todo_id>", methods=["POST"])
def delete(todo_id):
    get_todo(todo_id)
    db = get_db()
    db.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
    db.commit()
    return redirect(request.referrer or url_for("index"))


@app.route("/clear-completed", methods=["POST"])
def clear_completed():
    db = get_db()
    db.execute("DELETE FROM todos WHERE completed = 1")
    db.commit()
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True, port=5001)
