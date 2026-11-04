"""Screenshots of every dashboard page at projector size (1366x768), in the light and the dark theme.

Why: before a demo we look at every page the way the examiner will see it (a 1366x768 projector)
and in both themes, and check that each page loads quickly once the data is cached.

What it does:
  1. starts the Streamlit app headless on a free port (or uses --url if the app is already running);
  2. opens the app once, then visits every page by clicking its sidebar link, the way a presenter
     moves through the app: the first visit fills the caches, the second visit is timed as the
     "page load" (from the click until every chart is drawn);
  3. saves two PNGs per page and theme: the first screen (what fits in 1366x768) and the full page.

Usage:
  python scripts/screenshot_pages.py                       -> docs/previews/pages/
  python scripts/screenshot_pages.py --out some/folder --pages home trends
"""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT = 1366, 768
# URL path of each page (Streamlit derives it from the file name in app/pages/).
PAGES = ["home", "question_bank", "trends", "geography", "distributions", "relationships", "multi_parameter",
         "mobility", "outliers", "chart_builder", "ask_nirf", "data_method"]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_app(port: int) -> subprocess.Popen:
    cmd = [sys.executable, "-m", "streamlit", "run", str(ROOT / "app" / "Home.py"), "--server.headless=true",
           f"--server.port={port}", "--browser.gatherUsageStats=false"]
    return subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def wait_until_drawn(page: Page, timeout: float = 90) -> float:
    """Wait until the script run has finished and every chart is drawn; returns the seconds waited.

    Streamlit marks the app with data-test-script-state ("running" while the page script runs); a page
    counts as drawn when no script is running, no spinner shows and every Plotly chart has its SVG,
    and that has stayed true for half a second.
    """
    t0 = time.perf_counter()
    page.wait_for_selector("[data-testid='stMainBlockContainer']", timeout=timeout * 1000)
    quiet_since = None
    while time.perf_counter() - t0 < timeout:
        busy = page.evaluate("""() => {
            const app = document.querySelector("[data-testid='stApp']");
            const state = app ? app.getAttribute('data-test-script-state') : 'initial';
            const spinner = document.querySelector("[data-testid='stSpinner'], [data-testid='stSkeleton']");
            const plots = [...document.querySelectorAll('.js-plotly-plot')];
            const undrawn = plots.some(p => !p.querySelector('.main-svg'));
            return state === 'running' || state === 'initial' || !!spinner || undrawn;
        }""")
        now = time.perf_counter()
        if busy:
            quiet_since = None
        elif quiet_since is None:
            quiet_since = now
        elif now - quiet_since > 0.5:
            return quiet_since - t0
        time.sleep(0.05)
    return time.perf_counter() - t0


def open_by_sidebar(page: Page, name: str) -> float:
    """Click the page's sidebar link (as a presenter would) and time until the new page is drawn."""
    href = "" if name == "home" else name
    link = page.locator(f"[data-testid='stSidebarNav'] a[href$='/{href}']").first
    t0 = time.perf_counter()
    link.click()
    page.wait_for_function(r"p => location.pathname.replace(/\/$/, '').endsWith(p)", arg=href, timeout=30000)
    page.wait_for_timeout(150)      # let the new script run start
    return time.perf_counter() - t0 + wait_until_drawn(page)


def full_height(page: Page) -> int:
    # Chat pages (Ask NIRF) use a different scroll container than the other pages: take the tallest.
    return page.evaluate("""() => Math.max(document.body.scrollHeight, ...[
        "[data-testid='stMain']", "[data-testid='stAppScrollToBottomContainer']",
        "[data-testid='stMainBlockContainer']"].map(s => document.querySelector(s)?.scrollHeight || 0))""")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(ROOT / "docs" / "previews" / "pages"))
    ap.add_argument("--url", help="use an already running app instead of starting one")
    ap.add_argument("--pages", nargs="*", default=PAGES)
    ap.add_argument("--themes", nargs="*", default=["light", "dark"])
    ap.add_argument("--no-full", action="store_true", help="only the first screen, not the full page")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    proc = None
    url = args.url
    if not url:
        port = free_port()
        proc = start_app(port)
        url = f"http://127.0.0.1:{port}"
    timings = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for theme in args.themes:
                ctx = browser.new_context(viewport={"width": WIDTH, "height": HEIGHT}, color_scheme=theme,
                                          device_scale_factor=1)
                page = ctx.new_page()
                for attempt in range(60):          # wait for the server to come up
                    try:
                        page.goto(url, timeout=5000)
                        break
                    except Exception:
                        time.sleep(1)
                cold = wait_until_drawn(page)
                print(f"{theme:5}  first load (home, cold tab) {cold:5.2f}s", flush=True)
                for name in args.pages:
                    first = open_by_sidebar(page, name)       # first visit: fills the caches
                    if name != "home":
                        open_by_sidebar(page, "home")
                        again = open_by_sidebar(page, name)   # second visit: what a demo feels like
                    else:
                        again = first
                    page.wait_for_timeout(800)                # let chart transitions finish
                    if page.locator('.geolayer').count():     # maps paint their states a moment later
                        page.wait_for_timeout(2500)
                    page.screenshot(path=str(out / f"{name}_{theme}.png"))
                    if not args.no_full:
                        page.set_viewport_size({"width": WIDTH, "height": min(full_height(page) + 40, 16000)})
                        page.wait_for_timeout(3000 if page.locator('.geolayer').count() else 1200)
                        page.screenshot(path=str(out / f"{name}_{theme}_full.png"))
                        page.set_viewport_size({"width": WIDTH, "height": HEIGHT})
                        page.wait_for_timeout(300)
                    timings.append((theme, name, first, again))
                    print(f"{theme:5}  {name:16} first {first:5.2f}s   again {again:5.2f}s", flush=True)
                ctx.close()
            browser.close()
    finally:
        if proc:
            proc.terminate()
    slow = [t for t in timings if t[3] > 2.0]
    print(f"\n{len(timings)} page loads; {len(slow)} slower than 2 s after the first load"
          + (": " + ", ".join(f"{n} ({th}) {a:.1f}s" for th, n, _, a in slow) if slow else "."))


if __name__ == "__main__":
    main()
