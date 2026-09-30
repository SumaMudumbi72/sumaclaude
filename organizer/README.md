# File Organizer

A standalone Flask app that tidies a folder by sorting its files into
subfolders based on their extensions.

## Features

- Organize files by extension, in one of two ways:
  - **By category**: `photo.jpg` → `Images/`, `report.pdf` → `Documents/`,
    unknown types → `Other/`
  - **By extension**: `photo.jpg` → `JPG/`, `report.pdf` → `PDF/`
- Creates the folders automatically when they don't exist yet
- Moves each file into the right folder

## How it works

1. Enter a folder path (e.g. `~/Downloads`) and pick a mode.
2. Click **Preview** to see exactly which files will go where. Nothing
   moves yet.
3. Click **Move** to do it.
4. Changed your mind? Click **Undo last run** to move everything back and
   remove any folders the run created (if they're empty).

## Safety

This app moves real files on your computer, so it's careful:

- **Preview first.** Nothing moves until you confirm. If the folder's
  contents change between the preview and the confirmation, the app stops
  and shows a fresh preview.
- **Never overwrites.** If a file with the same name is already in the
  target folder, the moved file is renamed to `name (1).ext`.
- **Top level only.** Only files directly inside the chosen folder are
  moved. Subfolders, hidden files (starting with `.`), and shortcuts or
  symlinks are left alone.
- **System folders are refused**, such as `/System`, `/usr`, `/Library`,
  `C:\Windows`, and the top of a drive.
- **Local only.** The server listens on `127.0.0.1`, so other computers on
  your network can't reach it. Forms carry a CSRF token and requests must
  use `127.0.0.1` or `localhost`, so other websites open in your browser
  can't trigger moves.
- **Undo** covers the most recent run. Its record is kept in
  `last_run.json` next to `app.py` (ignored by git).

Don't deploy this app to a server: anyone who can reach it can move files
on that machine.

## Getting started

Requires Python 3.9+. Run these from the `organizer/` folder:

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5005 in your browser. (It uses port 5005 so it can
run alongside the other apps in this repo on 5001–5004.)

On macOS, folders like Desktop, Documents, and Downloads may need you to
allow access for Terminal (System Settings → Privacy & Security → Files and
Folders) before the app can read them.
