import secrets
import string

from flask import Flask, render_template, request

app = Flask(__name__)

MIN_LENGTH = 4
MAX_LENGTH = 128
DEFAULT_LENGTH = 16

CHARSETS = {
    "uppercase": string.ascii_uppercase,
    "lowercase": string.ascii_lowercase,
    "numbers": string.digits,
    "symbols": "!@#$%^&*()-_=+[]{};:,.?/~",
}


def generate_password(length, sets):
    """Generate a password with at least one character from each chosen set.

    Uses the `secrets` module, which draws from the OS's cryptographically
    secure random source.
    """
    chosen = [CHARSETS[name] for name in sets]
    pool = "".join(chosen)
    chars = [secrets.choice(charset) for charset in chosen]
    chars += [secrets.choice(pool) for _ in range(length - len(chars))]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


@app.route("/", methods=["GET", "POST"])
def index():
    form = request.form if request.method == "POST" else {}
    selected = [name for name in CHARSETS if name in form] if form else list(CHARSETS)

    errors = []
    try:
        length = int(form.get("length", DEFAULT_LENGTH))
    except ValueError:
        length = DEFAULT_LENGTH
        errors.append("Length must be a whole number.")
    if not MIN_LENGTH <= length <= MAX_LENGTH:
        errors.append(f"Length must be between {MIN_LENGTH} and {MAX_LENGTH}.")
    if not selected:
        errors.append("Select at least one character type.")

    password = None if errors else generate_password(length, selected)
    response = app.make_response(
        render_template(
            "index.html",
            password=password,
            length=length,
            selected=selected,
            charsets=CHARSETS,
            errors=errors,
            min_length=MIN_LENGTH,
            max_length=MAX_LENGTH,
        )
    )
    # Keep generated passwords out of the browser cache.
    response.headers["Cache-Control"] = "no-store"
    return response


if __name__ == "__main__":
    app.run(debug=True, port=5003)
