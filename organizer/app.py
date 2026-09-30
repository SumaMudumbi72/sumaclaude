import hashlib
import json
import os
import secrets
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

app = Flask(__name__)
# A fresh random key each start is fine for a local tool; it only protects
# the session that holds the CSRF token.
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

# Details of the most recent run, so it can be undone.
LAST_RUN_FILE = Path(app.root_path) / "last_run.json"

CATEGORIES = {
    "Images": {"jpg", "jpeg", "png", "gif", "bmp", "tiff", "tif", "webp", "heic", "svg", "ico", "raw"},
    "Documents": {"pdf", "doc", "docx", "txt", "rtf", "odt", "md", "pages", "tex", "epub"},
    "Spreadsheets": {"xls", "xlsx", "csv", "ods", "numbers", "tsv"},
    "Presentations": {"ppt", "pptx", "odp", "key"},
    "Audio": {"mp3", "wav", "aac", "flac", "ogg", "m4a", "wma", "aiff"},
    "Video": {"mp4", "mov", "avi", "mkv", "wmv", "flv", "webm", "m4v"},
    "Archives": {"zip", "rar", "7z", "tar", "gz", "bz2", "xz", "tgz"},
    "Code": {"py", "js", "ts", "html", "css", "java", "c", "cpp", "h", "go", "rs", "rb", "php", "sh", "json", "xml", "yaml", "yml", "sql", "ipynb"},
    "Installers": {"dmg", "pkg", "exe", "msi", "deb", "rpm", "apk", "iso"},
    "Fonts": {"ttf", "otf", "woff", "woff2"},
}
EXT_TO_CATEGORY = {ext: cat for cat, exts in CATEGORIES.items() for ext in exts}

MODES = {"category": "By category (Images, Documents, …)", "extension": "By extension (PDF, JPG, …)"}

# Folders the app refuses to touch, including everything inside them.
PROTECTED = [
    Path(p)
    for p in (
        "/System", "/Library", "/Applications", "/usr", "/bin", "/sbin", "/etc",
        "/var", "/opt", "/dev", "/boot", "/proc", "/sys",
        # macOS: /etc and /var resolve to these. /private/tmp stays allowed.
        "/private/etc", "/private/var",
        "C:\\Windows", "C:\\Program Files", "C:\\Program Files (x86)",
    )
]


class OrganizerError(Exception):
    """An error with a message that is safe to show the user."""


# --- Safety checks -------------------------------------------------------


@app.before_request
def only_local_hosts():
    # Blocks DNS-rebinding attacks, where another website's hostname is
    # pointed at 127.0.0.1 to reach this app from a browser.
    if request.host.split(":")[0] not in {"127.0.0.1", "localhost"}:
        abort(403)


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


def check_csrf():
    # Stops other websites from submitting a form to this app in your browser.
    sent = request.form.get("csrf", "")
    if not sent or not secrets.compare_digest(sent, session.get("csrf", "")):
        flash("That form expired. Please try again.", "error")
        return False
    return True


def resolve_folder(raw):
    if not raw:
        raise OrganizerError("Enter a folder path.")
    folder = Path(raw).expanduser()
    if not folder.is_absolute():
        raise OrganizerError("Enter a full path, e.g. ~/Downloads or /Users/you/Desktop.")
    folder = folder.resolve()
    if not folder.exists():
        raise OrganizerError(f"{folder} doesn't exist.")
    if not folder.is_dir():
        raise OrganizerError(f"{folder} is a file, not a folder.")
    if folder == Path(folder.anchor):
        raise OrganizerError("Organizing the top of the drive isn't allowed.")
    for protected in PROTECTED:
        if folder == protected or protected in folder.parents:
            raise OrganizerError(f"{folder} is a system folder, so it can't be organized.")
    return folder


# --- Planning and moving -------------------------------------------------


def target_folder(path, mode):
    ext = path.suffix.lower().lstrip(".")
    if mode == "extension":
        return ext.upper() if ext else "No extension"
    return EXT_TO_CATEGORY.get(ext, "Other")


def plan_moves(folder, mode):
    """List the files directly in `folder` and where each one would go.

    Only plain files at the top level are moved. Subfolders, hidden files
    (names starting with "."), and shortcuts/symlinks are left alone.
    """
    plan = []
    for path in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
        if path.name.startswith(".") or path.is_symlink() or not path.is_file():
            continue
        plan.append({"name": path.name, "folder": target_folder(path, mode)})
    return plan


def fingerprint(plan):
    """A short hash of the plan, to detect changes between preview and run."""
    data = json.dumps(plan, sort_keys=True).encode()
    return hashlib.sha256(data).hexdigest()[:16]


def unique_destination(directory, name):
    """Return a path in `directory` that doesn't exist yet: "a.txt", "a (1).txt", …"""
    dest = directory / name
    stem, suffix = Path(name).stem, Path(name).suffix
    n = 1
    while dest.exists():
        dest = directory / f"{stem} ({n}){suffix}"
        n += 1
    return dest


def execute(folder, plan):
    moves, created, errors = [], [], []
    for item in plan:
        src = folder / item["name"]
        dest_dir = folder / item["folder"]
        try:
            # A symlink here could point anywhere, so never move files through one.
            if dest_dir.is_symlink() or (dest_dir.exists() and not dest_dir.is_dir()):
                raise OrganizerError(f'a file or shortcut named "{item["folder"]}" is in the way')
            if not dest_dir.exists():
                dest_dir.mkdir()
                created.append(str(dest_dir))
            dest = unique_destination(dest_dir, item["name"])
            src.rename(dest)
            moves.append([str(src), str(dest)])
        except (OSError, OrganizerError) as exc:
            errors.append(f'{item["name"]}: {getattr(exc, "strerror", None) or exc}')
    return moves, created, errors


def save_last_run(folder, moves, created):
    LAST_RUN_FILE.write_text(
        json.dumps({"folder": str(folder), "moves": moves, "created": created}, indent=2)
    )


def load_last_run():
    try:
        return json.loads(LAST_RUN_FILE.read_text())
    except (OSError, ValueError):
        return None


def undo_last_run(run):
    restored, errors = 0, []
    for src, dest in reversed(run["moves"]):
        src, dest = Path(src), Path(dest)
        if not dest.exists():
            errors.append(f"{dest.name}: no longer in {dest.parent.name}/")
        elif src.exists():
            errors.append(f"{src.name}: a file with that name is already back in place")
        else:
            try:
                dest.rename(src)
                restored += 1
            except OSError as exc:
                errors.append(f"{dest.name}: {exc.strerror}")
    # Remove folders the run created, but only if they're empty now.
    for directory in reversed(run["created"]):
        try:
            Path(directory).rmdir()
        except OSError:
            pass
    return restored, errors


# --- Routes --------------------------------------------------------------


@app.route("/")
def index():
    raw_path = request.args.get("path", "").strip()
    mode = request.args.get("mode", "category")
    if mode not in MODES:
        mode = "category"

    folder = plan = groups = None
    if raw_path:
        try:
            folder = resolve_folder(raw_path)
            plan = plan_moves(folder, mode)
        except OrganizerError as exc:
            flash(str(exc), "error")
        except PermissionError:
            flash(f"No permission to read {raw_path}.", "error")
        else:
            groups = {}
            for item in plan:
                groups.setdefault(item["folder"], []).append(item["name"])
            groups = dict(sorted(groups.items()))

    return render_template(
        "index.html",
        raw_path=raw_path,
        mode=mode,
        modes=MODES,
        folder=folder,
        plan=plan,
        groups=groups,
        plan_id=fingerprint(plan) if plan else None,
        last_run=load_last_run(),
    )


@app.route("/organize", methods=["POST"])
def organize():
    raw_path = request.form.get("path", "")
    mode = request.form.get("mode", "category")
    back = redirect(url_for("index", path=raw_path, mode=mode))
    if not check_csrf() or mode not in MODES:
        return back

    try:
        folder = resolve_folder(raw_path)
        plan = plan_moves(folder, mode)
    except OrganizerError as exc:
        flash(str(exc), "error")
        return back

    # Re-plan from the folder's current contents and make sure it matches
    # what was previewed, so nothing unexpected gets moved.
    if fingerprint(plan) != request.form.get("plan_id"):
        flash("The folder changed since the preview. Check the new preview and try again.", "error")
        return back

    moves, created, errors = execute(folder, plan)
    if moves:
        save_last_run(folder, moves, created)
        folders = len({Path(dest).parent for _, dest in moves})
        flash(
            f"Moved {len(moves)} file{'s' * (len(moves) != 1)} into "
            f"{folders} folder{'s' * (folders != 1)}.",
            "success",
        )
    for error in errors:
        flash(f"Skipped {error}", "error")
    return back


@app.route("/undo", methods=["POST"])
def undo():
    run = load_last_run()
    back = redirect(url_for("index", path=run["folder"] if run else ""))
    if not check_csrf():
        return back
    if not run:
        flash("There's nothing to undo.", "error")
        return back

    restored, errors = undo_last_run(run)
    LAST_RUN_FILE.unlink(missing_ok=True)
    flash(f"Undo: moved {restored} file{'s' * (restored != 1)} back.", "success")
    for error in errors:
        flash(f"Couldn't restore {error}", "error")
    return back


if __name__ == "__main__":
    # Listens on 127.0.0.1 only, so other computers on your network can't reach it.
    app.run(host="127.0.0.1", port=5005, debug=True)
