"""Tests for the Ask NIRF chat (Level 3): name resolution, plan checks, the executor, the model wrapper and the page.

Offline (always run, no API key needed):
  * the 25 questions of tests/nlq_questions.py: each golden plan is checked and run, and gives a chart
    from the expected analysis (or the out-of-scope message);
  * name resolution: 'IIT Bombay' / 'iitb' / 'Bombay IIT' -> one institution, 'TN' -> Tamil Nadu,
    'research' -> rpc, 'teaching' -> tlr, 'last 3 years' -> the latest 3 years;
  * the planner retries once with the error message, and the model wrapper falls back to GEMINI_API_KEY_2;
  * friendly messages for no key, no internet, an invalid key and a used-up quota;
  * the page draws a chart, the assumptions and 3 follow-ups, and survives a failed model call.
Live (only when a Gemini key is set): every one of the 25 questions is sent to the model and the plan
must name an expected analysis. Accuracy report: python scripts/nlq_accuracy.py

    python -m pytest tests/test_nlq.py -v
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from core.data import LATEST_YEAR, MASTER_PATH, YEARS, find_institution
from core.questions import QUESTION_REGISTRY, allowed_chart_types
from nlq import llm
from nlq.catalog import catalog_text, closest_questions, functions
from nlq.executor import execute, registry_plan
from nlq.planner import PlanError, parse_plan, plan_question
from nlq.resolve import resolve_institution, resolve_parameter, resolve_state, resolve_years
from tests.nlq_questions import NLQ_QUESTIONS, plan_label

if not MASTER_PATH.exists():
    pytest.skip("run `python -m pipeline.clean` first", allow_module_level=True)

NLQ_DIR = Path(__file__).resolve().parents[1] / "nlq"
HAS_KEY = bool(llm.settings().keys)


# ---------- the 25 questions ----------

def test_twenty_five_varied_questions():
    assert len(NLQ_QUESTIONS) == 25 and len({q.id for q in NLQ_QUESTIONS}) == 25
    styles = {q.style for q in NLQ_QUESTIONS}
    assert {"typo", "hinglish", "abbreviation", "informal", "out of scope", "custom"} <= styles


@pytest.mark.parametrize("q", NLQ_QUESTIONS, ids=[q.id for q in NLQ_QUESTIONS])
def test_golden_plan_is_answered(q):
    plan = parse_plan(json.dumps(q.golden))
    assert plan_label(plan) in q.expected
    answer = execute(plan, question=q.question)
    if plan.type == "out_of_scope":
        assert answer.kind == "out_of_scope" and answer.message and len(answer.follow_ups) == 3
        return
    assert answer.kind == "chart", answer.message
    assert answer.result.chart_type in allowed_chart_types()
    assert not answer.result.table.empty and answer.result.insight
    assert len(answer.follow_ups) == 3


# ---------- name resolution ----------

def test_institution_spellings_resolve_to_one_key():
    key = find_institution("Indian Institute of Technology Bombay")
    for text in ("IIT Bombay", "iitb", "Bombay IIT", "IIT-B", "iit bombay", "IIT Mumbai"):
        assert resolve_institution(text)[0] == key, text
    assert resolve_institution("iitkgp")[0] == find_institution("IIT Kharagpur")
    assert resolve_institution("iisc")[0] == find_institution("Indian Institute of Science")
    assert "Bombay" in resolve_institution("iitb")[1]          # the translation is written as an assumption


def test_states_parameters_and_years():
    assert resolve_state("TN")[0] == "Tamil Nadu"
    assert resolve_state("Orissa")[0] == "Odisha"
    assert resolve_parameter("research")[0] == "rpc"
    assert resolve_parameter("teaching")[0] == "tlr"
    assert resolve_parameter("placements")[0] == "go"
    years, note = resolve_years("last 3 years", "Overall")
    assert years == YEARS[-3:] and "latest 3" in note
    assert resolve_years("last 3 years", "Research Institutions")[0] == [2023, 2024, 2025]
    assert resolve_years("since 2020")[0] == list(range(2020, LATEST_YEAR + 1))
    assert resolve_years("pichhle 5 saal")[0] == YEARS[-5:]
    assert resolve_years("between 2018 and 2021")[0] == [2018, 2019, 2020, 2021]
    assert resolve_years("latest")[0] == [LATEST_YEAR]


def test_years_are_fitted_to_the_function():
    a = execute(parse_plan(json.dumps({"type": "engine", "engine": "trends", "function": "biggest_movers",
                                       "params": {"years": "last 3 years", "category": "engg"}})))
    call = a.plan["resolved_call"]["params"]
    assert (call["start_year"], call["end_year"], call["category"]) == (LATEST_YEAR - 2, LATEST_YEAR, "Engineering")
    a = execute(parse_plan(json.dumps({"type": "engine", "engine": "univariate", "function": "score_distribution",
                                       "params": {"years": "2019-2021"}})))
    assert a.plan["resolved_call"]["params"]["year"] == 2021
    assert any("one year" in s for s in a.assumptions)


def test_states_limit_any_analysis():
    a = execute(parse_plan(json.dumps({"type": "engine", "engine": "univariate", "function": "summary_stats",
                                       "params": {"states": ["KL"]}})))
    assert a.kind == "chart" and a.plan["resolved_call"]["states"] == ["Kerala"]
    assert "Kerala" in a.result.insight


# ---------- plan checks and safety ----------

@pytest.mark.parametrize("reply", [
    "not json at all",
    '{"type": "engine", "engine": "trends", "function": "delete_everything"}',
    '{"type": "engine", "engine": "os", "function": "system"}',
    '{"type": "custom", "group_by": ["colour"], "chart": "radar"}',
    '{"type": "sql", "query": "DROP TABLE"}',
])
def test_invalid_plans_are_rejected(reply):
    with pytest.raises(ValueError):
        parse_plan(reply)


def test_json_in_fences_is_accepted():
    plan = parse_plan('Here you go:\n```json\n{"type": "clarify", "question": "Which year?"}\n```')
    assert plan.type == "clarify"


def test_no_model_code_is_ever_executed():
    """No call to exec / eval / compile / __import__ anywhere in nlq/ (read from the code's syntax tree)."""
    for path in NLQ_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        assert not called & {"exec", "eval", "compile", "__import__"}, path.name


def test_bad_values_give_messages_not_crashes():
    for params in ({"institutions": ["Hogwarts School"]}, {"category": "Astrology"}, {"years": "the 1990s"},
                   {"institutions": ["IIT Madras"], "category": "Law"}):
        a = execute(parse_plan(json.dumps({"type": "engine", "engine": "trends", "function": "rank_trajectory",
                                           "params": params})))
        assert a.kind == "error" and len(a.message) > 20, params


def test_unknown_options_are_dropped_and_listed():
    a = execute(parse_plan(json.dumps({"type": "engine", "engine": "geography", "function": "state_counts",
                                       "params": {"colour": "red", "n": 50}})))
    assert a.kind == "chart"
    assert a.plan["resolved_call"]["params"]["top_n"] == 50              # n -> top_n
    assert any("colour" in s for s in a.assumptions)


def test_catalog_lists_every_function_and_question():
    text = catalog_text()
    for engine, name in functions():
        assert f"## {engine}.{name}(" in text
    for qid in QUESTION_REGISTRY:
        assert f"Sample {qid}:" in text
    assert "Kerala" in text and "Research Institutions: 2021-2025" in text


def test_registry_plan_runs_without_the_model():
    a = execute(registry_plan("Q2.1"))
    assert a.kind == "chart" and a.result.chart_type == QUESTION_REGISTRY["Q2.1"].chart_type
    assert closest_questions("which states have the most institutions in the top 100")[0].id == "Q2.1"


# ---------- planner retry and model wrapper ----------

GOOD = '{"type": "engine", "engine": "trends", "function": "rank_trajectory", "params": {"institutions": ["iitb"]}}'


def test_planner_retries_once_with_the_error():
    replies, prompts = ["{broken json", GOOD], []

    def fake(system, user):
        prompts.append(user)
        return replies.pop(0)

    plan = plan_question("iitb rank", complete=fake)
    assert plan.function == "rank_trajectory" and len(prompts) == 2
    assert "rejected" in prompts[1] and "not valid JSON" in prompts[1]


def test_planner_gives_up_after_one_retry():
    calls = []

    def fake(system, user):
        calls.append(user)
        return '{"type": "engine", "engine": "trends", "function": "nope"}'

    with pytest.raises(PlanError):
        plan_question("anything", complete=fake)
    assert len(calls) == 2


def test_history_is_sent_for_follow_up_questions():
    seen = []
    plan_question("same for engineering", history=[("iitb rank", json.loads(GOOD))],
                  complete=lambda s, u: seen.append(u) or GOOD)
    assert "Earlier question: iitb rank" in seen[0] and "Question: same for engineering" in seen[0]


class _FakeAPIError(Exception):
    def __init__(self, code, status, message):
        super().__init__(message)
        self.code, self.status, self.message = code, status, message


class ConnectError(Exception):        # same class name as httpx's, which is how network errors are recognised
    pass


@pytest.mark.parametrize("exc, kind", [
    (_FakeAPIError(429, "RESOURCE_EXHAUSTED", "Quota exceeded"), "quota"),
    (_FakeAPIError(400, "INVALID_ARGUMENT", "API key not valid. Please pass a valid API key."), "invalid_key"),
    (_FakeAPIError(404, "NOT_FOUND", "models/gemini-x is not found"), "model"),
    (_FakeAPIError(503, "UNAVAILABLE", "overloaded"), "server"),
    (ConnectError("getaddrinfo failed"), "offline"),
])
def test_errors_are_explained(exc, kind):
    error = llm._classify(exc)
    assert error.kind == kind and error.message and error.fix


def test_spare_key_is_tried(monkeypatch):
    monkeypatch.setattr(llm, "settings", lambda: llm.Settings(("key-1", "key-2"), ("model-a",)))
    used = []

    def fake(key, model, system, user, json_mode):
        used.append(key)
        if key == "key-1":
            raise _FakeAPIError(429, "RESOURCE_EXHAUSTED", "Quota exceeded")
        return GOOD

    monkeypatch.setattr(llm, "_gemini", fake)
    assert llm.complete("s", "u") == GOOD and used == ["key-1", "key-2"]


def test_used_up_model_moves_to_the_next_model(monkeypatch):
    """The free tier counts requests per model, so a used-up quota on every key tries the next model."""
    monkeypatch.setattr(llm, "settings", lambda: llm.Settings(("key-1", "key-2"), ("model-a", "model-b")))
    tried = []

    def fake(key, model, system, user, json_mode):
        tried.append((key, model))
        if model == "model-a":
            raise _FakeAPIError(429, "RESOURCE_EXHAUSTED", "Generate content requests per day limit exceeded")
        return GOOD

    monkeypatch.setattr(llm, "_gemini", fake)
    assert llm.complete("s", "u") == GOOD and llm.LAST_MODEL == "model-b"
    assert tried == [("key-1", "model-a"), ("key-2", "model-a"), ("key-1", "model-b")]


def test_no_internet_stops_at_once(monkeypatch):
    monkeypatch.setattr(llm, "settings", lambda: llm.Settings(("key-1", "key-2"), ("model-a", "model-b")))
    tried = []

    def fake(key, model, system, user, json_mode):
        tried.append(model)
        raise ConnectError("getaddrinfo failed")

    monkeypatch.setattr(llm, "_gemini", fake)
    with pytest.raises(llm.LLMError) as e:
        llm.complete("s", "u")
    assert e.value.kind == "offline" and tried == ["model-a"]


def test_no_key_is_a_friendly_error(monkeypatch):
    monkeypatch.setattr(llm, "settings", lambda: llm.Settings((), ("model-a",)))
    with pytest.raises(llm.LLMError) as e:
        llm.complete("s", "u")
    assert e.value.kind == "no_key" and ".env" in e.value.fix
    assert llm.check_connection()[0] is False


# ---------- the page ----------

def _ask_page(monkeypatch, planner):
    from streamlit.testing.v1 import AppTest

    import nlq.planner
    from tests.app_helpers import HOME

    monkeypatch.setattr(nlq.planner, "plan_question", planner)
    monkeypatch.setattr(llm, "check_connection", lambda: (True, "Key loaded and working · test"))
    at = AppTest.from_file(str(HOME), default_timeout=180)
    at.switch_page("pages/ask_nirf.py")
    at.run()
    return at


def test_page_answers_a_question(monkeypatch):
    import streamlit as st
    st.cache_data.clear()
    plan = parse_plan('{"type": "engine", "engine": "geography", "function": "state_counts", "params": '
                      '{"year": "latest", "top_n": 100}, "title": "States with most top-100 institutions", '
                      '"assumptions": ["Category: Overall, because none was named."], '
                      '"follow_ups": ["Same for Engineering?", "How has this changed since 2017?", '
                      '"Which states gained the most?"]}')
    at = _ask_page(monkeypatch, lambda q, history=None: plan)
    assert not at.exception
    at.chat_input[0].set_value("which state has most top 100 colleges").run()
    assert not at.exception
    assert len(at.get("plotly_chart")) == 1
    assert any(e.label == "How I understood your question" for e in at.expander)
    labels = [b.label for b in at.button]
    assert {"Same for Engineering?", "How has this changed since 2017?", "Which states gained the most?"} <= set(labels)
    assert "Gemini" in " ".join(h.proto.body for h in at.get("html"))


def test_page_survives_a_failed_model_call(monkeypatch):
    import streamlit as st
    st.cache_data.clear()

    def offline(q, history=None):
        raise llm.LLMError("offline", "The Gemini service could not be reached.", "Check the Wi-Fi.")

    at = _ask_page(monkeypatch, offline)
    at.chat_input[0].set_value("which states have the most institutions in the top 100").run()
    assert not at.exception
    page_html = " ".join(h.proto.body for h in at.get("html"))
    assert "No internet connection" in page_html and "Check the Wi-Fi." in page_html
    run_here = [b for b in at.button if b.label.startswith("Run Q2.1 here")]
    assert run_here, [b.label for b in at.button]
    run_here[0].click().run()
    assert not at.exception and len(at.get("plotly_chart")) == 1


# ---------- live model (needs a Gemini key) ----------

@pytest.mark.skipif(not HAS_KEY, reason="no GEMINI_API_KEY in .env: live planning not tested")
@pytest.mark.parametrize("q", NLQ_QUESTIONS, ids=[q.id for q in NLQ_QUESTIONS])
def test_live_model_plans_the_expected_analysis(q):
    plan = plan_question(q.question)
    assert plan_label(plan) in q.expected, f"{q.question!r} -> {plan_label(plan)}"
    answer = execute(plan, question=q.question)
    assert answer.kind in ("chart", "out_of_scope", "clarify"), answer.message
