"""Contrast check of every dashboard page in the light and the dark theme (Playwright, 1366x768).

Why: the atlas has a light and a dark theme, and the viewer can switch between them at any moment in
the ⋮ menu (Light / Dark / System). Every heading, label, card and chart must stay readable in both,
also right after a switch and after moving to another page, without reloading.

What it does:
  1. starts the app headless on a free port (or uses --url);
  2. for each browser colour scheme (light, dark) and each ⋮ menu choice (Light, Dark, System) it picks
     the theme in the menu WITHOUT reloading, checks that the page follows at once (the attribute
     data-nirf-theme on <html>, set by the page's theme sync), then visits every page by its sidebar link
     and checks the page still shows the right theme;
  3. on every page it measures the contrast of every visible piece of text against what is really
     behind it:
       * page text: its computed colour against the background colours of its ancestors (blended where
         they are see-through; opacity included);
       * chart text: the SVG fill against the shapes under it (bar, heatmap cell, map state, the label's
         own box) on top of the chart card;
     using the WCAG 2 contrast ratio (L1 + 0.05) / (L2 + 0.05), L = relative luminance. Limits: 4.5:1 for
     normal text, 3:1 for large text (at least 24 px, or 18.66 px bold);
  4. saves a screenshot of each page per combination (with --out), prints every failure and exits with
     code 1 if there is any.

Usage:
  python scripts/check_contrast.py
  python scripts/check_contrast.py --schemes light --menu Light --pages home trends --out shots/
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from screenshot_pages import HEIGHT, PAGES, WIDTH, free_port, open_by_sidebar, start_app, wait_until_drawn  # noqa: E402

# Question Bank: one question from three different sections (a map, a correlogram, a transition matrix).
QB_QUESTIONS = [("2 · Geospatial", "Q2.1"), ("4 · Bivariate", "Q4.3"), ("7 · Mobility", "Q7.1")]

AUDIT_JS = r"""
async () => {
  const cv = document.createElement('canvas'); cv.width = cv.height = 1;
  const cx = cv.getContext('2d', {willReadFrequently: true});
  const RGB = /^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,\s\/]+([\d.]+%?))?\s*\)$/;
  const rgba = (c) => {                       // any CSS colour -> [r, g, b, alpha 0..1]
    if (!c || c === 'none' || c === 'transparent' || c.startsWith('url')) return [0, 0, 0, 0];
    const m = c.match(RGB);
    if (m) { let a = m[4] === undefined ? 1 : m[4].endsWith('%') ? parseFloat(m[4]) / 100 : +m[4];
             return [+m[1], +m[2], +m[3], a]; }
    cx.clearRect(0, 0, 1, 1); cx.fillStyle = '#000'; cx.fillStyle = c; cx.fillRect(0, 0, 1, 1);
    const d = cx.getImageData(0, 0, 1, 1).data;
    return [d[0], d[1], d[2], d[3] / 255];
  };
  const over = (t, b) => [0, 1, 2].map(i => t[i] * t[3] + b[i] * (1 - t[3])).concat([1]);
  const lin = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const lum = c => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const hex = c => '#' + c.slice(0, 3).map(v => Math.round(v).toString(16).padStart(2, '0')).join('');
  const opacityOf = (el) => { let o = 1; for (let e = el; e && e.nodeType === 1; e = e.parentElement)
                                o *= parseFloat(getComputedStyle(e).opacity); return o; };
  const bgOf = (el) => {                      // the colour behind an element: its ancestors' backgrounds
    const layers = [], box = el.getBoundingClientRect();
    const x = box.left + box.width / 2, y = box.top + box.height / 2;
    let clipped = false;
    for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
      // An ancestor only counts if the element is drawn over it (a slider's value label sits above its
      // thumb). Inside a scroll box the test stops: content scrolled out of view lies outside those boxes.
      const r = e.getBoundingClientRect(), cs = getComputedStyle(e);
      const clips = /auto|scroll|hidden|clip/.test(cs.overflowX + cs.overflowY);
      if (e !== el && !clipped && !clips && r.width > 0 && (x < r.left || x > r.right || y < r.top || y > r.bottom)) continue;
      if (clips) clipped = true;
      if (cs.backgroundImage.includes('gradient') && rgba(cs.backgroundColor)[3] === 0)
        return [255, 0, 255, 1];                 // a gradient with no solid colour under it: flagged, not guessed
      const c = rgba(cs.backgroundColor);
      if (c[3] > 0) { layers.push(c); if (c[3] >= 0.999) break; }
    }
    let out = [255, 255, 255, 1];
    for (let i = layers.length - 1; i >= 0; i--) out = over(layers[i], out);
    return out;
  };
  const needOf = (cs) => { const px = parseFloat(cs.fontSize), w = parseInt(cs.fontWeight) || 400;
                           return (px >= 24 || (px >= 18.66 && w >= 700)) ? 3 : 4.5; };
  const describe = (el, text) => {
    const tid = el.closest('[data-testid]')?.getAttribute('data-testid') || '';
    const cls = (typeof el.className === 'string' ? el.className : el.className?.baseVal || '')
                  .split(/\s+/).filter(c => c && !c.startsWith('st-emotion') && !c.startsWith('e')).slice(0, 2).join('.');
    return `${el.tagName.toLowerCase()}${cls ? '.' + cls : ''} [${tid}] "${text.slice(0, 48)}"`;
  };
  const fails = [], app = document.querySelector('[data-testid="stApp"]');
  let checked = 0;

  // ---- page text ----
  for (const el of app.querySelectorAll('*')) {
    if (['SCRIPT', 'STYLE', 'NOSCRIPT', 'svg'].includes(el.tagName) || el.closest('svg, .js-plotly-plot')) continue;
    const own = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join('').trim();
    if (!own) continue;
    const cs = getComputedStyle(el);
    if (cs.fontFamily.includes('Material') || cs.visibility === 'hidden') continue;
    if (el.closest('[disabled], [aria-disabled="true"], [data-testid="stIconMaterial"]')) continue;
    const r = el.getBoundingClientRect();
    if (r.width <= 1 || r.height <= 1) continue;
    const bg = bgOf(el), fg = rgba(cs.color);
    fg[3] *= opacityOf(el);
    const shown = over(fg, bg), need = needOf(cs), k = ratio(shown, bg);
    if (k < 1.01) continue;      // drawn in the background colour on purpose (a slider's min/max until hover)
    checked++;
    if (k + 1e-6 < need) fails.push({where: describe(el, own), fg: hex(shown), bg: hex(bg), ratio: +k.toFixed(2), need});
  }

  // ---- chart text ----
  const images = new Map();
  const pixel = async (img, x, y) => {
    const href = img.getAttribute('href') || img.getAttribute('xlink:href');
    if (!images.has(href)) {
      const im = new Image(); im.src = href;
      try { await im.decode(); } catch (e) { images.set(href, null); }
      if (!images.has(href)) {
        const c = document.createElement('canvas'); c.width = im.naturalWidth; c.height = im.naturalHeight;
        const g = c.getContext('2d', {willReadFrequently: true}); g.drawImage(im, 0, 0); images.set(href, g);
      }
    }
    const g = images.get(href); if (!g) return null;
    const r = img.getBoundingClientRect();
    const px = Math.floor((x - r.left) / r.width * g.canvas.width), py = Math.floor((y - r.top) / r.height * g.canvas.height);
    const d = g.getImageData(Math.max(0, Math.min(px, g.canvas.width - 1)), Math.max(0, Math.min(py, g.canvas.height - 1)), 1, 1).data;
    return [d[0], d[1], d[2], d[3] / 255];
  };
  let charts = 0;
  for (const plot of document.querySelectorAll('.js-plotly-plot')) {
    const svg = plot.querySelector('.main-svg'); if (!svg) continue;
    charts++;
    const card = bgOf(svg);
    const shapes = [...plot.querySelectorAll('path, rect, circle, polygon, ellipse, image')]
      .filter(s => !s.closest('text, .hoverlayer'))
      .map(s => ({s, r: s.getBoundingClientRect()})).filter(o => o.r.width > 0 && o.r.height > 0);
    for (const t of plot.querySelectorAll('text, tspan')) {   // a label's coloured part is a tspan of its own
      const text = [...t.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join('').trim();
      if (!text) continue;
      const r = t.getBoundingClientRect(); if (r.width <= 1 || r.height <= 1) continue;
      const cs = getComputedStyle(t);
      const fg = rgba(cs.fill); fg[3] *= parseFloat(cs.fillOpacity) * opacityOf(t);
      if (fg[3] < 0.05) continue;
      const x = r.left + r.width / 2, y = r.top + r.height / 2;
      let bg = card;
      for (const {s, r: sr} of shapes) {        // document order = drawing order (later is on top)
        if (x < sr.left || x > sr.right || y < sr.top || y > sr.bottom) continue;
        let c;
        if (s.tagName === 'image') { c = await pixel(s, x, y); if (!c) continue; }
        else {
          const ss = getComputedStyle(s); c = rgba(ss.fill);
          if (c[3] === 0) continue;
          const m = s.getScreenCTM(); if (!m || !s.isPointInFill) continue;
          if (!s.isPointInFill(new DOMPoint(x, y).matrixTransform(m.inverse()))) continue;
          c[3] *= parseFloat(ss.fillOpacity) * opacityOf(s);
        }
        if (c[3] > 0.02) bg = over(c, bg);
      }
      const shown = over(fg, bg), need = needOf(cs), k = ratio(shown, bg);
      checked++;
      if (k + 1e-6 < need) {
        const title = plot.querySelector('.gtitle')?.textContent.slice(0, 40) || '';
        fails.push({where: `chart "${title}" text "${text.slice(0, 40)}"`, fg: hex(shown), bg: hex(bg), ratio: +k.toFixed(2), need});
      }
    }
  }
  const appBg = rgba(getComputedStyle(app).backgroundColor);
  return {fails, checked, charts, appTheme: lum(appBg) < 0.5 ? 'dark' : 'light',
          attr: document.documentElement.getAttribute('data-nirf-theme')};
}
"""

THEME_JS = """() => {
  const c = getComputedStyle(document.querySelector('[data-testid="stApp"]')).backgroundColor.match(/[\\d.]+/g).map(Number);
  const l = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  return {app: (0.2126 * l(c[0]) + 0.7152 * l(c[1]) + 0.0722 * l(c[2])) < 0.5 ? 'dark' : 'light',
          attr: document.documentElement.getAttribute('data-nirf-theme')};
}"""


def pick_theme(page: Page, choice: str) -> None:
    """Choose Light, Dark or System in Streamlit's ⋮ menu (no reload)."""
    page.click("[data-testid='stMainMenu']")
    page.click(f"[data-testid='stMainMenuItem-theme-{choice}']")
    page.keyboard.press("Escape")


def wait_theme(page: Page, expected: str, timeout: float = 5.0) -> tuple[float | None, dict]:
    """Seconds until both the app background and the page's theme attribute show `expected` (None = never)."""
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < timeout:
        state = page.evaluate(THEME_JS)
        if state["app"] == expected and state["attr"] == expected:
            return time.perf_counter() - t0, state
        page.wait_for_timeout(25)
    return None, page.evaluate(THEME_JS)


def audit(page: Page, label: str, expected: str, problems: list[str], out: Path | None, shot: str) -> None:
    result = page.evaluate(AUDIT_JS)
    if result["appTheme"] != expected or result["attr"] != expected:
        problems.append(f"{label}: theme should be {expected}, app shows {result['appTheme']}, "
                        f"data-nirf-theme={result['attr']}")
    for f in result["fails"]:
        problems.append(f"{label}: {f['where']}  {f['fg']} on {f['bg']} = {f['ratio']}:1 (needs {f['need']})")
    print(f"  {label:44} {result['checked']:5} texts, {result['charts']:2} charts, "
          f"{len(result['fails']):3} below the limit", flush=True)
    if out:
        page.screenshot(path=str(out / f"{shot}.png"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", help="use an already running app instead of starting one")
    ap.add_argument("--schemes", nargs="*", default=["light", "dark"], help="browser colour schemes")
    ap.add_argument("--menu", nargs="*", default=["Light", "Dark", "System"], help="⋮ menu theme choices")
    ap.add_argument("--pages", nargs="*", default=PAGES)
    ap.add_argument("--out", help="folder for screenshots (one per page and combination)")
    ap.add_argument("--ask", help="on Ask NIRF, type this question so the chat bubbles are checked too")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    out = Path(args.out) if args.out else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
    proc, url = None, args.url
    if not url:
        port = free_port()
        proc = start_app(port)
        url = f"http://127.0.0.1:{port}"
    problems: list[str] = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for scheme in args.schemes:
                ctx = browser.new_context(viewport={"width": WIDTH, "height": HEIGHT}, color_scheme=scheme)
                page = ctx.new_page()
                for _ in range(60):
                    try:
                        page.goto(url, timeout=5000)
                        break
                    except Exception:
                        time.sleep(1)
                wait_until_drawn(page)
                for choice in args.menu:
                    expected = scheme if choice == "System" else choice.lower()
                    combo = f"browser {scheme}, menu {choice}"
                    print(f"\n{combo}", flush=True)
                    pick_theme(page, choice)
                    took, state = wait_theme(page, expected)
                    if took is None:
                        problems.append(f"{combo}: after the menu switch the page did not follow "
                                        f"(app {state['app']}, data-nirf-theme={state['attr']})")
                    else:
                        print(f"  page followed the menu in {took * 1000:.0f} ms (no reload)", flush=True)
                    page.wait_for_timeout(1500)
                    wait_until_drawn(page)
                    # The page that was open during the switch, before any navigation or reload.
                    audit(page, f"{combo} | same page, right after the switch", expected, problems, out,
                          f"{scheme}-{choice.lower()}_00_after_switch")
                    for name in args.pages:
                        open_by_sidebar(page, name)
                        page.wait_for_timeout(600)
                        if page.locator(".geolayer").count():
                            page.wait_for_timeout(1500)
                        tag = f"{scheme}-{choice.lower()}"
                        if name == "question_bank":
                            for tab, qid in QB_QUESTIONS:
                                page.get_by_role("tab", name=tab).click()
                                page.locator("[data-testid='stRadio'] label", has_text=f"{qid} ·").first.click()
                                page.wait_for_timeout(300)
                                wait_until_drawn(page)
                                page.wait_for_timeout(1200 if page.locator(".geolayer").count() else 400)
                                audit(page, f"{combo} | {name} {qid}", expected, problems, out, f"{tag}_{name}_{qid}")
                            continue
                        if name == "ask_nirf" and args.ask:
                            page.locator("[data-testid='stChatInputTextArea']").fill(args.ask)
                            page.keyboard.press("Enter")
                            page.wait_for_timeout(1000)
                            wait_until_drawn(page, timeout=120)
                        audit(page, f"{combo} | {name}", expected, problems, out, f"{tag}_{name}")
                ctx.close()
            browser.close()
    finally:
        if proc:
            proc.terminate()
    print(f"\n{len(problems)} problem(s)")
    for p in problems:
        print("  " + p)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
