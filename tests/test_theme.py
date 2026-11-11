"""Checks for the light and dark theme (Phase 17), so a later change cannot make the atlas unreadable again.

  * both stylesheets are always injected, and neither contains a "<" (Streamlit's HTML sanitiser drops a
    whole style block whose text has one, which silently removed every token once);
  * the dark tokens apply only under html[data-nirf-theme="dark"], the attribute the theme follower sets;
  * themed() draws every one of the 40 charts on a transparent background in both themes, and every label
    printed on a coloured mark (heatmap cell, inside a bar) reaches 4.5:1 against that mark;
  * the core chart text colours reach 4.5:1 on the card surface of their theme.
The full in-browser check of every page is scripts/check_contrast.py.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.questions import QUESTION_REGISTRY, run_question
from core.theme import (DARK_SURFACE, INK, INK_MUTED, INK_SECONDARY, MARIGOLD_INK, SURFACE, _scale_at, _values,
                        contrast, for_theme, ink_on, themed)

ASSETS = Path(__file__).resolve().parents[1] / "assets"


@pytest.fixture(scope="module")
def results():
    return {qid: run_question(qid) for qid in QUESTION_REGISTRY}


def test_stylesheets_survive_the_html_sanitiser():
    for name in ("style.css", "style-dark.css"):
        css = (ASSETS / name).read_text(encoding="utf-8")
        assert not re.search(r"<[/\w!]", css), f"{name} contains '<': Streamlit would drop the whole stylesheet"


def test_dark_tokens_are_scoped_to_the_theme_attribute():
    css = (ASSETS / "style-dark.css").read_text(encoding="utf-8")
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)                # comments out
    selectors = [s.strip() for s in re.findall(r"(?:^|\})\s*([^{}]+)\{", css)]
    assert selectors and all(s.strip().startswith('html[data-nirf-theme="dark"]') for s in selectors), selectors


@pytest.mark.parametrize("color", [INK, INK_SECONDARY, INK_MUTED, MARIGOLD_INK])
def test_chart_text_colours_read_on_both_card_surfaces(color):
    assert contrast(color, SURFACE) >= 4.5
    assert contrast(for_theme(color, True), DARK_SURFACE) >= 4.5


@pytest.mark.parametrize("fill", ["#0e9c8c", "#14a090", "#1f8782", "#e39a12", "#05332f", "#c2f3ea", "#cfd3e0",
                                  "#e0564f", "#2a3152", "#808080"])
def test_ink_on_any_mark_is_readable(fill):
    assert contrast(ink_on(fill), fill) >= 4.5


def _cell_labels(trace):
    """(ink, cell colour) for every heatmap label drawn by themed()."""
    zs = _values(trace["z"]).astype(float)
    lo = trace.get("zmin") if trace.get("zmin") is not None else float(zs[zs == zs].min())
    hi = trace.get("zmax") if trace.get("zmax") is not None else float(zs[zs == zs].max())
    if trace.get("zmid") is not None:
        half = max(hi - trace["zmid"], trace["zmid"] - lo)
        lo, hi = trace["zmid"] - half, trace["zmid"] + half
    for zrow, trow in zip(zs, trace["text"]):
        for v, label in zip(zrow, trow):
            m = re.match(r"<span style='color:(#[0-9a-f]{6})'>", label or "")
            if m:
                t = (v - lo) / (hi - lo or 1)
                yield m.group(1), "#" + "".join(f"{round(x):02x}" for x in _scale_at(trace["colorscale"], t))


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_every_chart_is_drawn_readably(results, dark):
    labelled = 0
    for qid, result in results.items():
        fig = themed(result.fig, dark)
        assert fig["layout"]["paper_bgcolor"] == fig["layout"]["plot_bgcolor"] == "rgba(0,0,0,0)", qid
        for trace in fig["data"]:
            if trace.get("type") == "heatmap" and isinstance(trace.get("colorscale"), list):
                for ink, cell in _cell_labels(trace):
                    labelled += 1
                    assert contrast(ink, cell) >= 4.5, (qid, ink, cell)
            if trace.get("type") == "bar" and trace.get("textposition") == "inside":
                fill, ink = trace["marker"]["color"], trace["textfont"]["color"]
                if isinstance(fill, str):
                    assert contrast(ink, fill) >= 4.5, (qid, ink, fill)
    assert labelled > 50          # the correlogram, transition matrices and top-10 grids were all checked


def test_themed_leaves_the_engine_figure_untouched(results):
    fig = results["Q4.3"].fig
    before = fig.to_json()
    themed(fig, True)
    themed(fig, False)
    assert fig.to_json() == before
