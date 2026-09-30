# Password Generator

A standalone Flask app for generating random passwords.

## Features

- Choose a password length (4–128 characters, default 16)
- Include any mix of uppercase, lowercase, numbers, and symbols
- Copy the password to the clipboard with one click

Every generated password contains at least one character from each type you
select. Passwords come from Python's `secrets` module, which uses the
operating system's cryptographically secure random source. Nothing is stored,
and the page is sent with `Cache-Control: no-store` so the browser doesn't
cache it.

## Getting started

Requires Python 3.9+. Run these from the `passwords/` folder:

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5003 in your browser. (It uses port 5003 so it can
run alongside the Todo app on 5001 and the Expense Tracker on 5002.)

The copy button needs a secure context, which `127.0.0.1` and `localhost`
count as. If you serve the app over plain HTTP on another address, the button
falls back to an older copy method that some browsers block.
