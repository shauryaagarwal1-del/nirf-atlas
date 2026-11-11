# NIRF Atlas

An interactive dashboard exploring India's NIRF institutional rankings (2017–2025) across every ranking category.

# Deployed On Streamlit (No need to run locally):

Cloud Link: https://nirf-atlas-yc4xpzhunqocryytq7buhd.streamlit.app/

## Setup: run the app on your own laptop

Steps 1 to 3 are done once per laptop (about 15 minutes, needs internet). After that, step 5 is all you need.

### 1. Get the code
The repository is private: send Shaurya your GitHub username, he adds you under **Settings → Collaborators**,
and you accept the invite from your e-mail. Then either:
- open the repository on GitHub → green **Code** button → **Download ZIP**, and unzip it; or
- clone it: `git clone https://github.com/shauryaagarwal1-del/nirf-atlas.git`

`main` is the version the live app runs; day-to-day work happens on the `shaurya` branch
(`git checkout shaurya` after cloning if you are working on the code).

### 2. Install Python 3.11
Download Python **3.11** from [python.org/downloads](https://www.python.org/downloads/). On Windows, tick
**"Add python.exe to PATH"** on the first screen of the installer.

### 3. Create the virtual environment and install the packages
Open a terminal **in the project folder** (the folder with `run_dashboard.bat` in it). On Windows: click the
File Explorer address bar, type `powershell`, press Enter. On macOS: right-click the folder → *New Terminal at
Folder*.

**Windows (PowerShell)**
```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt
```

**macOS / Linux**
```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

Only if you want to take the page screenshots (`scripts/screenshot_pages.py`), also install the browser it uses:
`python -m playwright install chromium`.

### 4. Add your own Gemini API key
The key is only needed for the **Ask NIRF** chat; every other page works without it, and offline.

1. Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey), sign in with Google and click
   **Create API key**. It is free. Use your own key: each key has its own free daily quota.
2. Create your `.env` file from the template and open it:

   **Windows (PowerShell)**
   ```powershell
   Copy-Item .env.example .env
   notepad .env
   ```
   **macOS**
   ```bash
   cp .env.example .env
   open -e .env
   ```
3. Fill it in like this (no quotes, no spaces around `=`), then save and close:
   ```
   GEMINI_API_KEY=AIza...your-key...
   GEMINI_API_KEY_2=
   GEMINI_MODEL=gemini-2.5-flash
   ```
   - `GEMINI_MODEL=gemini-2.5-flash` is the model we use: its free quota lasts the longest. If it runs out, the app
     moves on to the next Flash model by itself.
   - `GEMINI_API_KEY_2` is optional: a spare key, tried when the first one fails (for example, quota used up).

The file must be named exactly `.env` (not `.env.txt`) and sit in the project folder. **Never commit or share
`.env`**: it is in `.gitignore`, so git leaves it out, but do not paste the key in chats either.

### 5. Start the dashboard
- **Windows:** double-click `run_dashboard.bat` in the project folder.
- **macOS / Linux:** run `./run_dashboard.sh` in a terminal (the first time, `chmod +x run_dashboard.sh` if needed).

Both activate `.venv` and start Streamlit on `app/Home.py`. It opens at http://localhost:8501; keep the terminal
window open while you use the app (closing it stops the app). If Streamlit asks for an e-mail address the first
time, press Enter. To start it by hand instead: `.\.venv\Scripts\python -m streamlit run app/Home.py`.

**Internet:** only the **Ask NIRF** chat needs internet (it sends the typed question to the Gemini API). Every
other page (Home, Question Bank, Explore, Chart Builder, Data & Method) runs fully on the laptop, offline.

### 6. Check that the chat works
Open **Ask NIRF (AI)** in the sidebar. The Gemini box shows a green dot: *Key loaded and working ·
gemini-2.5-flash*. Ask *"Top 10 engineering colleges in 2025"* and a chart appears. If the dot is not green:

| The app says | Fix |
|---|---|
| No Gemini API key was found | The file is not named exactly `.env`, or it is not in the project folder. |
| Gemini rejected the API key | The key was copied wrongly: copy it again from aistudio, no spaces or quotes. |
| Used up its free quota / rate limit | Wait a minute, or add a second key as `GEMINI_API_KEY_2`. |
| Could not be reached | No internet connection. The other pages still work. |

After any change to `.env`, close the terminal window and start the app again. The pre-demo checklist is in
[docs/final_checklist.md](docs/final_checklist.md).

## Run (for development)

Run every command from the project folder (`nirf-atlas`). The commands call the virtual environment's Python
directly, so nothing needs to be activated. On macOS / Linux, write `.venv/bin/python` instead of
`.\.venv\Scripts\python`.

**1. Rebuild the cleaned data from the raw files** (optional: the cleaned table is already in the repository;
about 1 minute):
```powershell
.\.venv\Scripts\python -m pipeline.clean
```
It reads every raw CSV in `data/raw/csv/`, writes `data/processed/nirf_master.parquet` (+ `.csv`), the mapping
tables in `data/mappings/` and `docs/cleaning_report.md`. The raw CSVs come from the scraper
(`python -m scraper.scrape_nirf`, needs internet; not needed, the CSVs are in the repository).

**2. Check the answers:**
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

The `Screenshots/` folder holds reference shots of four Question Bank charts (Q2.3 map and ranked list, Q2.4, Q5.3, Q7.1) at 1366x768; remake them with `python scripts/screenshot_pages.py --questions Q2.3 Q2.3:ranked Q2.4 Q5.3 Q7.1 --out Screenshots --themes light`.

If you pulled the rename of `app/pages/` to `app/views/`, delete the old `app/pages/` folder (only `__pycache__` is
left in it): while it exists, Streamlit can open direct links without the app's styling and filters.
