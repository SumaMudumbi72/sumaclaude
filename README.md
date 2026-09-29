# sumaclaude — Flask Todo App

A simple Todo application built with Flask and SQLite.

## Features

- Add, edit, and delete todos
- Mark todos complete / incomplete
- Filter by All, Active, or Completed
- Clear all completed todos
- Data persisted in a local SQLite database (`todos.db`)

## Project structure

```
app.py              # Flask app, routes, and database setup
requirements.txt    # Python dependencies
templates/          # Jinja2 templates (base, index, edit)
static/             # CSS and JavaScript
```

## Getting started

Requires Python 3.9+.

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000 in your browser.

## Configuration

| Environment variable | Default                 | Description                   |
|----------------------|-------------------------|-------------------------------|
| `SECRET_KEY`         | `dev-secret-change-me`  | Flask session/flash secret    |
| `DATABASE`           | `./todos.db`            | Path to the SQLite database   |

Set a real `SECRET_KEY` before deploying anywhere other than your own machine.
