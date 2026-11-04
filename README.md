# NIRF Atlas

An interactive dashboard exploring India's NIRF institutional rankings (2017–2025) across every ranking category.

## Setup

Requires Python 3.11+.

**Windows (PowerShell)**
```powershell
git clone https://github.com/shauryaagarwal1-del/nirf-atlas.git
cd nirf-atlas
git checkout shaurya
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m playwright install chromium
```

**macOS / Linux**
```bash
git clone https://github.com/shauryaagarwal1-del/nirf-atlas.git
cd nirf-atlas
git checkout shaurya
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Then copy `.env.example` to `.env` and put your own Gemini API key in it. Never commit `.env`.
The key is only needed for the **Ask NIRF** chat page; every other page works without it (and offline).
Optional settings in `.env`: `GEMINI_API_KEY_2` (a spare key, tried once when the first fails) and `GEMINI_MODEL`.

Check the chat's understanding of 25 test questions with your key: `python -m scripts.nlq_accuracy`.

Before a demo, screenshot every page at projector size (1366x768) in the light and the dark theme and time each
page: `python scripts/screenshot_pages.py` (saves to `docs/previews/pages/` and prints the load time of every page).

If you pulled the rename of `app/pages/` to `app/views/`, delete the old `app/pages/` folder (only `__pycache__` is
left in it): while it exists, Streamlit can open direct links without the app's styling and filters.
