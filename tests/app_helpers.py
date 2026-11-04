"""Small helpers for the headless app tests (Streamlit AppTest): open a page, find widgets, read the chart."""

from __future__ import annotations

import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from core.data import find_institution

HOME = Path(__file__).resolve().parents[1] / "app" / "Home.py"
# Pages whose "What do you want to see?" picker sits in a tab: the session state that opens that tab.
PICKER_TAB = {"views/geography.py": {"geography-tab": "More views"}}


def open_page(page: str, state: dict | None = None) -> AppTest:
    """Open a page headless; `state` presets session-state values first (e.g. which tab is open)."""
    at = AppTest.from_file(str(HOME), default_timeout=180)
    at.switch_page(page)
    for k, v in (state or {}).items():
        at.session_state[k] = v
    return at.run()


def widget(at: AppTest, kind: str, prefix: str):
    """The widget of this kind whose key is `prefix` or starts with `prefix-` (keys carry a scope suffix)."""
    for w in getattr(at, kind):
        if w.key and (w.key == prefix or w.key.startswith(prefix + "-")):
            return w
    keys = [w.key for w in getattr(at, kind)]
    raise KeyError(f"no {kind} with key {prefix!r}; have {keys}")


def set_widget(at: AppTest, kind: str, prefix: str, value) -> AppTest:
    """Set one widget (institution names are turned into keys) and rerun the app."""
    if kind == "button":
        return widget(at, "button", prefix).click().run()
    if prefix.endswith("institutions") or prefix.endswith("institution"):
        value = [find_institution(v) for v in value] if isinstance(value, list) else find_institution(value)
    return widget(at, kind, prefix).set_value(value).run()


def html_text(at: AppTest) -> str:
    """The page's HTML blocks, without the injected stylesheet (its CSS names every class, e.g. .nirf-empty)."""
    return " ".join(h.proto.body for h in at.get("html") if not h.proto.body.lstrip().startswith("<style>"))


def chart_titles(at: AppTest) -> list[str]:
    return [json.loads(c.proto.spec)["layout"]["title"]["text"] for c in at.get("plotly_chart")]


def chart_notes(at: AppTest) -> str:
    """All annotation text of the charts on the page (source line, notes)."""
    return " ".join(a.get("text", "") for c in at.get("plotly_chart")
                    for a in json.loads(c.proto.spec)["layout"].get("annotations", []))
