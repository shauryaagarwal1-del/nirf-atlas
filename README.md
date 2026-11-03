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
