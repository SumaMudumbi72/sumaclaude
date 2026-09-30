# Expense Tracker

A standalone Flask + SQLite app for tracking income and expenses.

## Features

- Add income and expenses with amount, category, description, and date
- See your total balance, income, and expenses at a glance
- Filter transactions by category (with per-category totals)
- Export all transactions, or the current category, to CSV
- Delete transactions

## Getting started

Requires Python 3.9+. Run these from the `expenses/` folder:

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5002 in your browser. (It uses port 5002 so it can
run alongside the Todo app on 5001.)

## Configuration

| Environment variable | Default                 | Description                   |
|----------------------|-------------------------|-------------------------------|
| `SECRET_KEY`         | `dev-secret-change-me`  | Flask session/flash secret    |
| `DATABASE`           | `./expenses.db`         | Path to the SQLite database   |

Set a real `SECRET_KEY` before deploying anywhere other than your own machine.

## Notes

- Amounts are stored as whole cents, so totals never drift from rounding.
- CSV export prefixes text that starts with `=`, `+`, `-`, or `@` with a `'`
  so spreadsheet apps don't run it as a formula.
