"""Phase 14 exam simulation tests: 30 new examiner questions, answered via the UI path and via the Ask NIRF chat.

Offline (no API key or internet needed):
  * the question set covers all 8 sections and every tricky case (missing years, a category that only
    exists from 2023, a one-institution state, start year after end year, tied ranks, band-only ranks);
  * UI path: the real app, with the listed controls set, draws the expected chart (or the message);
  * chat: the golden plan, and the live model's plan recorded in tests/exam_chat_plans.json, both run
    through our executor to the right analysis with the right settings.
Recording new live plans: python -m scripts.exam_simulation --live (writes docs/exam_simulation.md).

    python -m pytest tests/test_exam.py -v
"""

import json
from pathlib import Path

import pytest

from core.data import MASTER_PATH
from tests.exam_questions import EXAM

if not MASTER_PATH.exists():
    pytest.skip("run `python -m pipeline.clean` first", allow_module_level=True)

from core.data import NirfInputError, find_institution  # noqa: E402
from core.runner import run  # noqa: E402
from nlq.executor import engine_call  # noqa: E402
from nlq.planner import EnginePlan  # noqa: E402
from nlq.resolve import resolve_institution  # noqa: E402
from tests.exam_check import chat_answer, ui_answer  # noqa: E402

PLANS = Path(__file__).with_name("exam_chat_plans.json")
RECORDED = json.loads(PLANS.read_text(encoding="utf-8")) if PLANS.exists() else {}
IDS = [q.id for q in EXAM]


def test_thirty_questions_cover_every_section_and_tricky_case():
    assert len(EXAM) == 30 and len(set(IDS)) == 30
    assert {q.section for q in EXAM} == set(range(1, 9))
    tricky = " ".join(q.tricky for q in EXAM)
    for case in ("missing in some years", "category only from 2023", "one institution", "start year after end year",
                 "tied ranks", "band-only ranks"):
        assert case in tricky, case


@pytest.mark.parametrize("q", EXAM, ids=IDS)
def test_ui_path(q):
    o = ui_answer(q)
    assert o.ok, o.problem


@pytest.mark.parametrize("q", EXAM, ids=IDS)
def test_chat_golden_plan(q):
    o = chat_answer(q, q.golden)
    assert o.ok, o.problem


@pytest.mark.parametrize("q", EXAM, ids=IDS)
def test_chat_recorded_live_plan(q):
    rec = RECORDED.get(q.id)
    if not rec or not rec.get("plan"):
        pytest.skip("no live plan recorded yet (python -m scripts.exam_simulation --live)")
    o = chat_answer(q, rec["plan"])
    assert o.ok, o.problem


# ---------- problems found while preparing the questions (regression tests) ----------

def test_an_unknown_short_form_is_never_matched_by_spelling():
    with pytest.raises(NirfInputError):           # 'lpu' must not match 'Samba-lpu-r University'
        find_institution("LPU")
    assert resolve_institution("LPU")[0] == find_institution("Lovely Professional University")
    assert resolve_institution("KIIT")[0] == find_institution("Kalinga Institute of Industrial Technology")


def test_a_name_plus_its_city_picks_one_campus():
    vellore, ludhiana = find_institution("Christian Medical College Vellore"), find_institution("Christian Medical "
                                                                                                "College Ludhiana")
    assert vellore != ludhiana
    assert find_institution("National Law University Delhi") != find_institution("National Law University Cuttack")


def test_a_state_filter_never_claims_that_nirf_has_no_ranking():
    with pytest.raises(NirfInputError, match="No institution in Goa is in the Overall ranking of 2025"):
        run("univariate", "summary_stats", dict(year=2025), states=["Goa"])


def test_the_chat_puts_years_given_the_wrong_way_round_in_order():
    plan = EnginePlan(type="engine", engine="mobility", function="band_transitions",
                      params=dict(year_a=2025, year_b=2018))
    params, _, notes = engine_call(plan)
    assert (params["year_a"], params["year_b"]) == (2018, 2025)
    assert any("later year first" in n for n in notes)
