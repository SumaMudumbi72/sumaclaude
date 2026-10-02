# Birthday Reminder

A standalone Flask + SQLite app for keeping track of birthdays.

## Features

- **Store birthdays:** name, month and day, plus an optional birth year
  (to show ages) and notes. You can edit and delete them too.
- **Show upcoming birthdays:** the next 30 days, soonest first, with
  "Today!", "Tomorrow", or "In N days" and the age they're turning. The
  full list is sorted by whose birthday comes next.
- **Email reminders (optional):** a daily email listing birthdays that are
  7 days away, 1 day away, and today.

Feb 29 birthdays show up on Feb 28 in non-leap years.

## Getting started

Requires Python 3.9+. Run these from the `birthdays/` folder:

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5006 in your browser. (It uses port 5006 so it can
run alongside the other apps in this repo on 5001–5005.)

## Email reminders (optional)

Everything else works without this. To get reminders by email, set these
environment variables:

| Variable         | Example                  | Notes                                              |
|------------------|--------------------------|----------------------------------------------------|
| `SMTP_HOST`      | `smtp.gmail.com`         | Your email provider's SMTP server                  |
| `SMTP_PORT`      | `587`                    | `587` (STARTTLS, default) or `465` (SSL)           |
| `SMTP_USER`      | `you@gmail.com`          | Login for the SMTP server                          |
| `SMTP_PASSWORD`  | `abcd efgh ijkl mnop`    | For Gmail, use an [app password](https://myaccount.google.com/apppasswords), not your normal password |
| `REMINDER_TO`    | `you@gmail.com`          | Where reminders are sent                           |
| `REMINDER_FROM`  | `you@gmail.com`          | Optional; defaults to `SMTP_USER`                  |
| `REMINDER_DAYS`  | `7,1,0`                  | Optional; how many days ahead to remind (default `7,1,0`) |

Keep the password out of git: put the `export` lines in a file such as
`birthdays/.env` (already ignored by git) and load it with
`source .env` before starting the app.

### Sending reminders

Reminders are sent by a command, not by the web app itself:

```bash
flask --app app send-reminders
```

It emails one message listing every birthday that's due a reminder today.
Each reminder is only sent once, so running it more than once a day is
harmless. The **Send today's reminders now** button on the page does the
same thing.

To run it every morning at 8:00 on macOS or Linux, add a line like this
with `crontab -e` (adjust the path):

```
0 8 * * * cd /path/to/sumaclaude/birthdays && . ./.env && venv/bin/flask --app app send-reminders
```

The computer needs to be on at that time for cron to run it.

## Configuration

| Environment variable | Default                 | Description                   |
|----------------------|-------------------------|-------------------------------|
| `SECRET_KEY`         | `dev-secret-change-me`  | Flask session/flash secret    |
| `DATABASE`           | `./birthdays.db`        | Path to the SQLite database   |
