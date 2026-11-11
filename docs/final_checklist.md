# Final checklist: the 30 minutes before the evaluation

What to open and test before the live demo on **Saturday 7 November 2026**. Tick every box. If a check fails, the
"If it fails" column says what to do; do not start fixing code on the day. The longer evening-before list and the
7-minute script are in [team/demo_script.md](team/demo_script.md).

We have two ways to run the dashboard: the **demo laptop** (local, works offline except Ask NIRF) and the
**live app** on Streamlit Community Cloud (runs from the `main` branch, needs internet). Use the laptop for the
demo; the live app is the backup and the link we can share.

## 30 minutes before

| ✓ | Check | How | If it fails |
|---|---|---|---|
| [ ] | **Internet** | Connect to college Wi-Fi and open any website. Keep a **phone hotspot** switched on and tested, ready to join if the Wi-Fi is slow. | Switch to the hotspot. Only Ask NIRF and the live app need internet. |
| [ ] | **App starts** | Windows: double-click `run_dashboard.bat`. macOS/Linux: `./run_dashboard.sh`. It opens at http://localhost:8501. | Run `.\.venv\Scripts\python -m streamlit run app/Home.py` by hand and read the error. If `.venv` is missing, redo the Setup in README.md. |
| [ ] | **40 questions pass** | In a second terminal: `.\.venv\Scripts\python -m scripts.run_all_questions`. The last line must say **40/40**. | Use the backup laptop or the live app. The saved charts in `docs/previews/Q*.html` open in any browser. |
| [ ] | **API key works** | Ask NIRF page: the Gemini status box in the sidebar is **green**. | Check `.env` has `GEMINI_API_KEY=` with no spaces or quotes; add `GEMINI_API_KEY_2` and restart the app. |
| [ ] | **Chat answers** | Ask NIRF: type *"Top 10 engineering colleges in 2025"*. A chart with a one-line answer appears. Ask only one or two warm-up questions (free quota). | Wait a minute (rate limit) or switch to the spare key. Fall back to Question Bank / Chart Builder, which do not need the chat. |
| [ ] | **Every page loads once** | Click Home, Question Bank, every Explore page, Chart Builder, Ask NIRF, Data & Method. This warms the cache so the demo is fast. | A slow first load is normal; a red error is not: note the page and use the live app for it. |
| [ ] | **Both themes read well** | ⋮ menu (top right) → **Light**, then **Dark**: cards, headings and charts switch at once, no reload. Optional full check: `.\.venv\Scripts\python scripts/check_contrast.py` ends with **0 problem(s)**. | Pick the theme that looks right on the projector and leave it. |
| [ ] | **Map draws** | Geography page: the India map is coloured. | Use Q2.1 in the Question Bank (bar chart of the same counts). |
| [ ] | **Live app awake** | Open the live app link (share.streamlit.io → *My apps* → nirf-atlas). If it shows "This app has gone to sleep", click the wake-up button and wait about a minute. Check Home and one Ask NIRF question. | The laptop is the main demo; the live app is only the backup. |
| [ ] | **Reset the view** | Sidebar back to defaults: Category **Overall**, years **2017–2025**, no states, top N **10**. Browser full screen (F11), zoom 100%. | Reload the page (F5) to reset everything. |
| [ ] | **Backup ready** | Second laptop with the app running, or a browser tab with `docs/previews/pages/` screenshots. Charger and HDMI adapter packed. | — |

## Do not do on the day

- Do not run `python -m scripts.nlq_accuracy` or `pytest` with `NIRF_LIVE_TESTS=1`: they use up the free Gemini quota.
- Do not `git pull` or change branches on the demo laptop after the checks above pass.
- Do not merge anything into `main`: that would redeploy the live app during the demo.

## Branches: how the live app is updated

Both branches matter from now on:

- **`shaurya`** is where all day-to-day work goes (commit and push to `origin shaurya`, as before).
- **`main`** is what the live app on Streamlit Community Cloud runs. The live app only changes when Shaurya merges
  `shaurya` into `main` (fast-forward) and pushes `main`. Nobody else pushes to `main`.

So a fix pushed to `shaurya` shows up on the laptop after `git pull`, but **not** on the live app until it is
merged into `main`.
