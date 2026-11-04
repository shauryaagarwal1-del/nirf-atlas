"""Checks for the Phase 13 polish rules, so they stay true when an engine changes.

Every one of the 40 question charts must have: an answer title, a title on every axis it draws, a legend
title whenever its legend lists two or more entries, an explicit chart surface (so Streamlit cannot paint
its own colour behind the plot) and the source note. Long institution names are shortened on the axis but
shown in full on hover. The Data & Method page reads its cleaning numbers from docs/cleaning_report.md.
"""

from __future__ import annotations

import pytest

from core.cleaning_report import find_count, read_cleaning_report
from core.data import CHART_LABEL_LEN, chart_labels, load_master
from core.questions import QUESTION_REGISTRY, run_question
from core.theme import FULL_NAMES, SOURCE_NOTE, SURFACE


@pytest.fixture(scope="module")
def results():
    return {qid: run_question(qid) for qid in QUESTION_REGISTRY}


def _used_axes(fig):
    """Cartesian axes that carry at least one trace (layout key, e.g. 'xaxis2')."""
    used = set()
    for t in fig.data:
        if t.type in ("choropleth", "scattergeo"):
            continue
        for a in ("xaxis", "yaxis"):
            ref = getattr(t, a, None) or a[0]
            used.add(a + ref[1:])
    return used


@pytest.mark.parametrize("qid", list(QUESTION_REGISTRY))
def test_chart_rules(results, qid):
    fig = results[qid].fig
    layout = fig.layout
    assert layout.title.text, "no title"
    assert SOURCE_NOTE in " ".join(a.text or "" for a in layout.annotations), "no source note"
    assert layout.paper_bgcolor == SURFACE and layout.plot_bgcolor == SURFACE, "chart surface not set"
    used = [k for k in _used_axes(fig) if layout[k].visible is not False and layout[k].showticklabels is not False]
    for letter in "xy":
        axes = [k for k in used if k[0] == letter]
        if not axes:
            continue
        if len(axes) == 1:
            assert layout[axes[0]].title.text, f"{axes[0]} has no title"
        else:   # small multiples: the outer row / column carries the title for the whole grid
            assert any(layout[k].title.text for k in axes), f"no {letter} axis of the panels has a title"
    named = [t for t in fig.data if t.name and t.showlegend is not False]
    if len(named) > 1 and layout.showlegend is not False:
        assert layout.legend.title.text, "legend without a title"


def test_long_names_shortened_with_full_name_on_hover():
    df = load_master()
    long_keys = (df.drop_duplicates("institution_key")
                 .loc[lambda d: d["canonical_name"].str.len() > 60, "institution_key"].head(3).tolist())
    labels = chart_labels(long_keys)
    for k, lab in labels.items():
        assert len(lab.split(" (")[0]) <= CHART_LABEL_LEN
        if "…" in lab:
            assert FULL_NAMES[lab] == df.loc[df["institution_key"].eq(k), "canonical_name"].iloc[0]


def test_cleaning_report_is_readable():
    rep = read_cleaning_report()
    assert rep.ok and len(rep.steps) >= 12
    assert rep.steps["rows_after"].iloc[-1] == len(load_master())
    assert (rep.steps["what_changed"].str.len() > 20).all()
    assert {"institution_key", "score", "rank"} <= set(rep.dictionary["column"])
    seven = rep.steps.set_index("step").at["7", "what_changed"]
    assert find_count(seven, r"into ([\d,]+) institutions") == load_master()["institution_key"].nunique()
