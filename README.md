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

## Run

Run every command from the project folder (`nirf-atlas`). The commands call the virtual environment's Python
directly, so nothing needs to be activated. On macOS / Linux, with the environment activated, write `python`
instead of `.\.venv\Scripts\python`.

**1. Rebuild the cleaned data from the raw files** (optional: the cleaned table is already in the repository;
about 1 minute):
```powershell
.\.venv\Scripts\python -m pipeline.clean
```
It reads every raw CSV in `data/raw/csv/`, writes `data/processed/nirf_master.parquet` (+ `.csv`), the mapping
tables in `data/mappings/` and `docs/cleaning_report.md`. The raw CSVs come from the scraper
(`python -m scraper.scrape_nirf`, needs internet; not needed, the CSVs are in the repository).

**2. Start the dashboard.** The quickest way, once Setup is done:
- **Windows:** double-click `run_dashboard.bat` in the project folder.
- **macOS / Linux:** run `./run_dashboard.sh` in a terminal (the first time, `chmod +x run_dashboard.sh` if needed).

Both activate `.venv` and start Streamlit on `app/Home.py`. Or start it by hand:
```powershell
.\.venv\Scripts\python -m streamlit run app/Home.py
```
It opens at http://localhost:8501. If Streamlit asks for an e-mail address the first time, press Enter.

**Internet:** only the **Ask NIRF** chat needs internet (it sends the typed question to the Gemini API). Every
other page (Home, Question Bank, Explore, Chart Builder, Data & Method) runs fully on the laptop, offline.
The pre-demo checklist is in [docs/final_checklist.md](docs/final_checklist.md).

**3. Check the answers:**
```powershell
.\.venv\Scripts\python -m scripts.run_all_questions     # the 40 Annexure A questions: 40/40 must pass
.\.venv\Scripts\python -m scripts.exam_simulation       # 30 new exam questions, UI path and Ask NIRF chat
.\.venv\Scripts\python -m pytest                        # all tests (about 5 minutes)
```
The tests never call the Gemini model, so they do not use up the free daily quota. To test the chat against the
live model as well: `python -m scripts.nlq_accuracy` (33 questions) or `python -m scripts.exam_simulation --live`
(records the model's plans for the 30 exam questions), or set `NIRF_LIVE_TESTS=1` before `pytest`.
Results of the exam simulation, and of 12 tricky chat questions asked live (institutes that do not exist, band-only
colleges, predictions, two questions in one message ...): [docs/exam_simulation.md](docs/exam_simulation.md).

Before a demo, screenshot every page at projector size (1366x768) in the light and the dark theme and time each
page: `python scripts/screenshot_pages.py` (saves to `docs/previews/pages/` and prints the load time of every page).

If you pulled the rename of `app/pages/` to `app/views/`, delete the old `app/pages/` folder (only `__pycache__` is
left in it): while it exists, Streamlit can open direct links without the app's styling and filters.
