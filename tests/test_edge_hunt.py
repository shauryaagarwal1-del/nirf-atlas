"""Edge-hunt tests (Phase 15e): every problem found by a systematic edge-case test stays fixed.

  A. bugs: no unusual score change beyond the threshold; top N larger than the list; categories ranked in
     one year only (SDG) and "1 years"; a state with no ranked institution (Ladakh);
  B. renamed institutions are one institution (Thapar University = Thapar Institute ...), different
     institutions with similar names stay apart, the rename finder and the review decisions;
  C. names people type: short forms (JIPMER, RVCE, NLU Delhi ...), vague families (IISER, IIM, NIPER),
     institutions NIRF does not rank (ISB, BITS Goa), no unrelated suggestions, clean display names;
  D. years ('2020 se', "'21", '2024-25', 2026 ...), category words (B.Tech, MBA colleges, nursing),
     parameter words (research score, patents), state typos, cities and regions;
  E. the institute-type filter: "Which IITs improved the most in Engineering since 2019?" shows only IITs.

No language model is used: chat plans are written by hand the way the model writes them.

    python -m pytest tests/test_edge_hunt.py -v
"""

from __future__ import annotations

import inspect
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from core.data import (MASTER_PATH, AmbiguousInstitutionError, NirfInputError, NotRankedError, check_types,
                       find_institution, institute_types, institution_names, load_master, match_institution)
from core.engines import geography, mobility, multivariate, outliers, trends
from core.runner import ENGINES, engine_function, run
from nlq.executor import execute
from nlq.planner import parse_plan
from nlq.resolve import (resolve_category, resolve_institution, resolve_parameter, resolve_region, resolve_state,
                         resolve_years)

if not MASTER_PATH.exists():
    pytest.skip("run `python -m pipeline.clean` first", allow_module_level=True)

ROOT = Path(__file__).resolve().parents[1]
ONE_YEAR = "SDG was ranked only in 2025, so there is no change over time to show."


def ask(params: dict, function: str, engine: str, question: str = ""):
    """Run a hand-written engine plan exactly like the chat runs the model's plan."""
    p = parse_plan(json.dumps({"type": "engine", "engine": engine, "function": function, "params": params}))
    return execute(p, question=question)


def key_of(name: str) -> str:
    return find_institution(name)


# =====================================================================================================
# A. bugs
# =====================================================================================================

@pytest.mark.parametrize("category", ["Dental", "Architecture & Planning", "Agriculture & Allied Sectors",
                                      "State Public University"])
def test_no_change_beyond_the_threshold_gives_a_clean_answer(category):
    r = outliers.unusual_score_jumps(category=category, z_threshold=3.0)
    assert r.insight.startswith("None of the ") and "is beyond |z| > 3" in r.insight
    assert "Try a lower threshold." in r.insight
    assert "nan" not in r.insight.lower() and "n/a" not in r.insight
    assert r.table[["score_from", "score_to", "z"]].notna().all().all()


def test_unusual_count_matches_the_threshold():
    r = outliers.unusual_score_jumps(category="Overall", z_threshold=2.0)
    n = int(r.insight.split(" are unusual")[0].split(", ")[-1])
    assert n == len(r.table) and (r.table["z"].abs() > 2.0).all()


def test_top_n_larger_than_the_list_is_capped():
    r = geography.state_counts(category="Overall", top_n=500)
    assert r.insight.startswith("Overall lists 200 institutions in 2025, so the top 200 is used.")
    assert "of the 200 places" in r.insight and "top 500" not in r.insight
    assert "top 200" in r.fig.layout.title.text
    r = geography.state_share_over_time(category="Overall", top_n=500)
    assert r.insight.startswith("Overall lists 200 institutions a year, so the top 200 is used.")
    r = geography.state_counts(category="Law", top_n=100)
    assert r.insight.startswith("Law lists 40 institutions in 2025, so the top 40 is used.")


def test_list_size_is_the_national_list_under_a_filter():
    r = run("geography", "state_counts", {"category": "Overall", "top_n": 500}, types=["IIT"])
    assert "Overall lists 200 institutions in 2025" in r.insight


def _period_functions():
    """Every engine function that measures change over time (needs two years)."""
    return [("trends", "biggest_movers"), ("trends", "consistent_top_n"), ("geography", "state_share_over_time"),
            ("geography", "state_representation_change"), ("multivariate", "improved_despite_decline"),
            ("mobility", "band_transitions"), ("mobility", "biggest_rank_moves"), ("mobility", "band_retention"),
            ("mobility", "top10_entries_exits"), ("mobility", "up_down_same_counts"),
            ("outliers", "unusual_score_jumps"), ("outliers", "volatility_vs_peers")]


@pytest.mark.parametrize("engine,function", _period_functions())
def test_one_year_category_gets_one_clear_message(engine, function):
    with pytest.raises(NirfInputError) as e:
        run(engine, function, {"category": "SDG"})
    assert str(e.value) == ONE_YEAR


def test_one_year_category_in_the_chat():
    a = ask({"category": "SDG", "start_year": 2019, "end_year": 2024}, "biggest_movers", "trends",
            question="Which SDG institutions improved the most from 2019 to 2024?")
    assert a.kind == "error" and a.message == ONE_YEAR
    assert "must be before" not in a.message


def test_no_one_years_anywhere():
    """'1 years' never appears in an answer or a message (SDG and the two-year categories)."""
    texts = []
    for engine in ENGINES:
        module = __import__(f"core.engines.{engine}", fromlist=["x"])
        for name, fn in inspect.getmembers(module, inspect.isfunction):
            if name.startswith("_") or fn.__module__ != module.__name__:
                continue
            sig = inspect.signature(fn).parameters
            for category in ("SDG", "Open University"):
                kw = {"category": category} if "category" in sig else {"categories": category} if "categories" in sig \
                    else None
                if kw is None:
                    continue
                if "institutions" in sig:
                    kw["institutions"] = ["IIT Madras"]
                if "institution" in sig:
                    kw["institution"] = "IIT Madras"
                try:
                    r = fn(**kw)
                    texts += [r.insight, r.fig.layout.title.text or ""]
                except NirfInputError as e:
                    texts.append(str(e))
    assert texts and not [t for t in texts if " 1 years" in t or "(1 years" in t]


@pytest.mark.parametrize("place", ["Ladakh", "ladakh", "Lakshadweep"])
def test_a_state_with_no_ranked_institution(place):
    name = "Ladakh" if place.lower() == "ladakh" else "Lakshadweep"
    message = f"No institution from {name} appears in any NIRF ranking."
    with pytest.raises(NirfInputError, match=message):
        resolve_state(place)
    with pytest.raises(NirfInputError, match=message):
        run("trends", "biggest_movers", {"category": "Overall"}, states=[place])
    a = ask({"category": "Overall", "states": [place]}, "state_counts", "geography")
    assert a.kind == "error" and a.message == message and "Known states" not in a.message


# =====================================================================================================
# B. renamed institutions
# =====================================================================================================

RENAMES = [  # (2017 name, later name, city)
    ("Thapar University", "Thapar Institute of Engineering and Technology", "Patiala"),
    ("Siksha'O' Anusandhan University", "Siksha 'O' Anusandhan", "Bhubaneswar"),
    ("Symbiosis International University", "Symbiosis International", "Pune"),
    ("Sri Ramachandra University", "Sri Ramachandra Institute of Higher Education and Research", "Chennai"),
    ("NITTE University", "NITTE", "Mangalore"),
    ("Maharishi Markandeshwar University", "Maharishi Markandeshwar", "Ambala"),
    ("Lingaya's University", "Lingaya's Vidyapeeth", "Faridabad"),
    ("Rajalakshmi Engineering College Engineering & Technology", "Rajalakshmi Engineering College", "Chennai"),
    ("Poona College of Pharmacy, Erandwane, Pune", "Poona College of Pharmacy", "Pune"),
    ("Gokaraju Rangaraju Institute of Engineering & Technology",
     "Goka Raju Ranga Raju Institute of Engineering & Technology", "Hyderabad"),
    ("VNR Vignana Jyothi Institute of Engineering & Technology",
     "Vallurupalli Nageswara Rao Vignana Jyothi Institute of Engineering and Technology", "Hyderabad"),
]


def _keys_named(name: str, city: str | None = None) -> set[str]:
    df = load_master()
    rows = df[df["institute_name"].eq(name)]
    if city:
        rows = rows[rows["city"].eq(city)]
    return set(rows["institution_key"])


@pytest.mark.parametrize("old,new,city", RENAMES)
def test_renamed_institution_is_one_institution(old, new, city):
    a, b = _keys_named(old), _keys_named(new)
    assert len(a) == 1 and a == b, (old, a, new, b)
    years = load_master().loc[lambda d: d["institution_key"].isin(a), "year"]
    assert years.min() == 2017 and years.nunique() >= 2


def test_jntu_anantapur_is_one_institution_and_kakinada_stays_apart():
    df = load_master()
    jntu = df[df["canonical_name"].eq("Jawaharlal Nehru Technological University") & df["state"].eq("Andhra Pradesh")]
    by_city = jntu.groupby("city")["institution_key"].unique()
    assert set(by_city["Anantapur"]) == set(by_city["Ananthapuramu"])
    assert set(by_city["Kakinada"]).isdisjoint(set(by_city["Anantapur"]))


@pytest.mark.parametrize("a,b", [
    ("Thiagarajar College of Engineering", "Thiagarajar College"),
    ("Chandigarh Engineering College", "Chandigarh Engineering College Jhanjeri"),
    ("Jagannath International Management School", "Jagannath International Management School, VasantKunj"),
    ("Post Graduate Government College for Girls", "Govt Post-graduate College for Girls, Sector-11"),
    ("Gokaraju Rangaraju College of Pharmacy", "Goka Raju Ranga Raju Institute of Engineering & Technology"),
])
def test_different_institutions_with_similar_names_stay_apart(a, b):
    df = load_master()
    ka = set(df.loc[df["canonical_name"].eq(a), "institution_key"])
    kb = set(df.loc[df["canonical_name"].eq(b), "institution_key"])
    assert ka and kb and ka.isdisjoint(kb)


def test_renamed_institutions_count_in_2017_to_2025_movers():
    r = trends.biggest_movers(category="Overall", start_year=2017, end_year=2025, n=200, direction="both")
    assert "Thapar Institute of Engineering and Technology" in " ".join(r.table["full_name"])
    assert "65 institutions with an exact rank in both years" in r.insight


def test_a_renamed_institution_is_not_a_2018_new_entrant():
    df = load_master()
    thapar = df[df["institution_key"].eq(key_of("Thapar Institute of Engineering and Technology"))]
    row = thapar[thapar["year"].eq(2018) & thapar["category_std"].eq("Overall")].iloc[0]
    assert not row["is_new_entrant"] and row["first_year_seen"] == 2017
    assert row["years_present"] == thapar[thapar["category_std"].eq("Overall")]["year"].nunique()


def test_review_decisions_were_copied():
    review = pd.read_csv(ROOT / "data/mappings/institution_review.csv", dtype=str, keep_default_na=False)
    suggested = pd.read_csv(ROOT / "data/mappings/institution_review_suggested.csv", dtype=str, keep_default_na=False)
    want = {frozenset((a, b)): s for a, b, s in zip(suggested["node_a"], suggested["node_b"], suggested["suggestion"])}
    for a, b, approve in zip(review["node_a"], review["node_b"], review["approve"]):
        s = want.get(frozenset((a, b)))
        if s in ("yes", "no"):
            assert approve == s, (a, b)
        elif s == "check":
            assert approve == "", (a, b)


def test_rename_finder_lists_candidates(tmp_path):
    out = subprocess.run([sys.executable, "-m", "scripts.find_renames"], cwd=ROOT, capture_output=True, text=True,
                         encoding="utf-8")
    assert out.returncode == 0, out.stderr
    found = pd.read_csv(ROOT / "data/mappings/rename_review.csv", dtype=str, keep_default_na=False)
    assert {"approve", "similarity", "gap_years", "old_name", "new_name", "old_key", "new_key"} <= set(found.columns)
    assert (found["old_key"] != found["new_key"]).all()
    # the pairs fixed by hand are linked now, so the finder no longer lists them
    assert not found["old_name"].eq("Thapar University").any()


# =====================================================================================================
# C. names people type
# =====================================================================================================

SHORT_FORMS = {
    "IIT Chennai": "Indian Institute of Technology Madras",
    "MAHE": "Manipal Academy of Higher Education-Manipal",
    "IIT ISM": "Indian Institute of Technology (Indian School of Mines)",
    "ISM Dhanbad": "Indian Institute of Technology (Indian School of Mines)",
    "SRMIST": "S.R.M. Institute of Science and Technology",
    "JU": "Jadavpur University",
    "CMC Ludhiana": "Christian Medical College, Brown Road, Ludhiana",
    "JIPMER": "Jawaharlal Institute of Post Graduate Medical Education & Research",
    "PGI": "Post Graduate Institute of Medical Education and Research",
    "PGIMER": "Post Graduate Institute of Medical Education and Research",
    "NLU Jodhpur": "National Law University, Jodhpur",
    "RVCE": "R.V. College of Engineering",
    "MIT Manipal": "Manipal Institute of Technology",
    "LSR": "Lady Shri Ram College For Women",
    "IIEST": "Indian Institute of Engineering Science and Technology, Shibpur",
    "IIEST Shibpur": "Indian Institute of Engineering Science and Technology, Shibpur",
    "SOA": "Siksha 'O' Anusandhan",
    "TIFR": "Tata Institute of Fundamental Research",
    "ICT Mumbai": "Institute of Chemical Technology",
    "NIPER Mohali": "National Institute of Pharmaceutical Education and Research, Mohali",
    "NIPER Hyderabad": "National Institute of Pharmaceutical Education and Research Hyderabad",
    "Thapar": "Thapar Institute of Engineering and Technology (Deemed-to-be-university)",
    "St Stephens": "St. Stephen's College",
}


@pytest.mark.parametrize("typed,name", SHORT_FORMS.items())
def test_short_forms_resolve_with_an_assumption(typed, name):
    r = resolve_institution(typed)
    assert institution_names([r.key])[r.key] == name
    assert r.note and typed in r.note


@pytest.mark.parametrize("typed,city", [("NLU Delhi", "New Delhi"), ("NLU Odisha", "Cuttack"),
                                        ("NLU Cuttack", "Cuttack")])
def test_shared_names_are_shown_with_their_city(typed, city):
    r = resolve_institution(typed)
    assert institution_names([r.key])[r.key] == "National Law University"
    assert f"National Law University ({city})" in r.note


@pytest.mark.parametrize("typed,count,first", [("IISER", 5, "IISER Pune"), ("IIM", 21, "IIM Ahmedabad"),
                                               ("NIPER", 7, None), ("IIT", 23, "IIT Madras")])
def test_a_family_alone_asks_which_one(typed, count, first):
    with pytest.raises(AmbiguousInstitutionError) as e:
        resolve_institution(typed)
    assert e.value.total == count and len(e.value.options) == 4
    a = ask({"institutions": [typed]}, "rank_trajectory", "trends", question=f"How has {typed} ranked?")
    assert a.kind == "clarify" and len(a.options) == 4
    if first:
        assert a.options[0].startswith(first)
    if typed == "IIM":           # the main IIMs: the top of the Management ranking
        assert [o.split(" (")[0] for o in a.options] == ["IIM Ahmedabad", "IIM Bangalore", "IIM Kozhikode",
                                                         "IIM Lucknow"]
    if typed == "NIPER":
        assert all(o.startswith("NIPER ") for o in a.options)


@pytest.mark.parametrize("typed,offer", [("ISB", None), ("Indian School of Business", None),
                                         ("BITS Goa", "Birla Institute of Technology & Science - Pilani"),
                                         ("BITS Hyderabad", "Birla Institute of Technology & Science - Pilani")])
def test_institutions_nirf_does_not_rank_say_so(typed, offer):
    with pytest.raises(NotRankedError) as e:
        resolve_institution(typed)
    assert "Isb&m" not in str(e.value)
    assert ("does not appear in any NIRF ranking" in str(e.value)) or ("not ranked on its own" in str(e.value))
    a = ask({"institutions": [typed]}, "rank_trajectory", "trends")
    assert a.kind == "not_ranked"
    assert [x["label"] for x in a.alternatives] == ([offer] if offer else [])


@pytest.mark.parametrize("typed", ["XQZW", "PGX", "JPMR", "Qwerty Uiop Institute", "Zebra Goa"])
def test_no_unrelated_suggestions(typed):
    """An unknown short form or name gets no 'Did you mean' list of unrelated colleges."""
    with pytest.raises(NirfInputError) as e:
        match_institution(typed)
    assert "Did you mean" not in str(e.value)


def test_a_misspelt_name_still_gets_a_real_suggestion_or_match():
    r = resolve_institution("Christian Medical Colege Vellore")
    assert institution_names([r.key])[r.key] == "Christian Medical College"


def test_display_names_are_clean_and_raw_names_kept():
    df = load_master()
    assert not df["canonical_name"].str.contains("`").any()
    assert not df["canonical_name"].str.contains("Stephens's").any()
    stephen = df[df["institution_key"].eq(key_of("St. Stephen's College"))]
    assert set(stephen["canonical_name"]) == {"St. Stephen's College"}
    assert {"St. Stephens's College", "St. Stephen`s College"} <= set(stephen["institute_name_raw"])
    soa = resolve_institution("SOA").key
    assert institution_names([soa])[soa] == "Siksha 'O' Anusandhan"


# =====================================================================================================
# D. years, categories, parameters, places
# =====================================================================================================

@pytest.mark.parametrize("value,category,years", [
    ("2020 se", "Overall", list(range(2020, 2026))),
    ("since 2020", "Overall", list(range(2020, 2026))),
    ("over the years", "Overall", list(range(2017, 2026))),
    ("in the last decade", "Overall", list(range(2017, 2026))),
    ("2020s", "Overall", list(range(2020, 2026))),
    ("'21", "Overall", [2021]),
    ("2k21", "Overall", [2021]),
    ("FY2024", "Overall", [2024]),
    ("2024-25", "Overall", [2025]),
    ("recent years", "Overall", [2023, 2024, 2025]),
    ("in recent years", "Dental", [2023, 2024, 2025]),
    ("2018-22", "Overall", [2018, 2019, 2020, 2021, 2022]),
    ("latest", "Overall", [2025]),
])
def test_year_phrases(value, category, years):
    assert resolve_years(value, category)[0] == years


def test_academic_year_says_which_ranking_is_used():
    years, note = resolve_years("2024-25", "Overall")
    assert years == [2025] and "NIRF 2025" in note and "published" in note


def test_years_ago_counts_back_from_this_year():
    from datetime import date
    years, note = resolve_years("three years ago", "Overall")
    assert years == [date.today().year - 3] and "3 years before" in note


@pytest.mark.parametrize("value,category,words", [
    ("2016", None, "There is no NIRF ranking for 2016"),
    (2026, None, "the latest NIRF ranking is 2025"),
    ("2026", "Overall", "the latest Overall ranking is 2025"),
    ("2018", "Dental", "Dental starts in 2020"),
    (2018, "Dental", "Dental starts in 2020"),
])
def test_a_year_with_no_ranking_says_so(value, category, words):
    with pytest.raises(NirfInputError, match=words):
        resolve_years(value, category)


def test_typed_years_partly_outside_a_category_are_left_out_with_a_note():
    years, note = resolve_years([2018, 2021], "Dental")
    assert years == [2021] and "2018 is left out" in note


def test_the_chat_still_moves_a_missing_year_to_the_nearest():
    a = ask({"category": "Dental", "year": 2018}, "rank_distribution", "univariate")
    assert a.kind == "chart" and a.plan["resolved_call"]["params"]["year"] == 2020
    assert any("nearest to 2018" in s for s in a.assumptions)


@pytest.mark.parametrize("typed,category", [
    ("B.Tech", "Engineering"), ("btech colleges", "Engineering"), ("MBA colleges", "Management"),
    ("pharmacy colleges", "Pharmacy"), ("MBBS colleges", "Medical"), ("architecture colleges", "Architecture & Planning"),
    ("planning", "Architecture & Planning"), ("law universities", "Law"), ("agri colleges", "Agriculture & Allied Sectors"),
    ("arts colleges", "College"), ("arts and science colleges", "College"), ("sustainability", "SDG"),
    ("engineering", "Engineering"), ("dental colleges", "Dental"),
])
def test_category_words(typed, category):
    assert resolve_category(typed)[0] == category


@pytest.mark.parametrize("typed,what", [("nursing", "Nursing"), ("polytechnic", "Polytechnics"),
                                        ("nursing colleges", "Nursing")])
def test_not_nirf_categories_are_said_plainly(typed, what):
    with pytest.raises(NirfInputError, match=f"NIRF has no {what} ranking"):
        resolve_category(typed)


@pytest.mark.parametrize("typed,code,sub", [
    ("research score", "rpc", False), ("teaching score", "tlr", False), ("placement score", "go", False),
    ("patents", "rpc", True), ("student strength", "tlr", True), ("faculty ratio", "tlr", True),
    ("median salary", "go", True),
])
def test_parameter_words(typed, code, sub):
    got, note = resolve_parameter(typed)
    assert got == code
    if sub:
        assert "NIRF publishes only the 5 parameter scores, not the sub-parameters" in note


def test_research_in_research_institutions_is_qnr():
    code, note = resolve_parameter("research", "Research Institutions")
    assert code == "qnr" and "no RPC" in note
    a = ask({"category": "Research Institutions", "x": "research", "y": "score"}, "scatter_relation", "bivariate")
    assert a.kind == "chart" and a.plan["resolved_call"]["params"]["x"] == "qnr"
    assert any("no RPC" in s for s in a.assumptions)


@pytest.mark.parametrize("typed,state", [("Telengana", "Telangana"), ("Tamilnadu", "Tamil Nadu"),
                                         ("Mumbai", "Maharashtra"), ("Bombay", "Maharashtra"),
                                         ("Bangalore", "Karnataka"), ("Chennai", "Tamil Nadu"),
                                         ("Kolkata", "West Bengal"), ("Hyderabad", "Telangana"), ("Pune", "Maharashtra")])
def test_state_typos_and_cities(typed, state):
    assert resolve_state(typed)[0] == state


def test_andhra_and_madhya_pradesh_never_mix():
    assert resolve_state("Andhra Pradesh")[0] == "Andhra Pradesh"
    assert resolve_state("Madhya Pradesh")[0] == "Madhya Pradesh"
    assert resolve_state("Andra Pradesh")[0] == "Andhra Pradesh"


@pytest.mark.parametrize("typed,region,must", [("north east", "North-East", "Assam"), ("North-East India", "North-East", "Assam"),
                                               ("south india", "South", "Kerala"), ("north india", "North", "Punjab"),
                                               ("Southern states", "South", "Tamil Nadu")])
def test_regions(typed, region, must):
    got, states, note = resolve_region(typed)
    assert got == region and must in states and region in note
    with pytest.raises(NirfInputError, match="is a region, not a state"):
        resolve_state(typed)
    a = ask({"category": "Overall", "states": [typed]}, "state_counts", "geography")
    assert a.kind == "chart"
    assert sorted(a.plan["resolved_call"]["states"]) == states
    assert "Delhi" not in a.plan["resolved_call"]["states"] or region == "North"


# =====================================================================================================
# E. institute-type filter
# =====================================================================================================

def test_institute_types_from_names():
    t = institute_types()
    names = institution_names(t.dropna().index)
    counts = t.value_counts()
    assert counts["IIT"] == 23 and counts["IISER"] == 5 and counts["NIT"] >= 30
    iits = {names[k] for k in t[t.eq("IIT")].index}
    assert "Indian Institute of Technology (Indian School of Mines)" in iits
    assert all(n.startswith("Indian Institute of Technology") for n in iits)
    nits = {names[k] for k in t[t.eq("NIT")].index}
    assert "Visvesvaraya National Institute of Technology, Nagpur" in nits
    assert pd.isna(t.get(key_of("Birla Institute of Technology & Science - Pilani")))


@pytest.mark.parametrize("typed,code", [("IITs", "IIT"), ("all IIMs", "IIM"), ("the NITs", "NIT"), ("AIIMS", "AIIMS"),
                                        ("Indian Institutes of Technology", "IIT"), ("iiser", "IISER")])
def test_type_words(typed, code):
    assert check_types([typed]) == [code]


def test_unknown_type_lists_the_types():
    with pytest.raises(NirfInputError, match="Choose from: IIT, NIT"):
        check_types(["Central universities"])


def _only_iits(table: pd.DataFrame) -> bool:
    t = institute_types()
    keys = [key_of(n) for n in table["full_name"]]
    return bool(keys) and all(t.get(k) == "IIT" for k in keys)


def test_runner_type_filter_shows_only_iits():
    r = run("trends", "biggest_movers", {"category": "Engineering", "start_year": 2019}, types=["IIT"])
    assert _only_iits(r.table)
    assert r.fig.layout.title.text.startswith("Among IITs only")
    assert r.insight.startswith("Among IITs only:")
    assert "Institute type filter: only IITs" in r.method


def test_type_filter_with_states_and_a_category_without_them():
    r = run("geography", "state_counts", {"category": "Engineering"}, states=["Tamil Nadu"], types=["NIT"])
    assert r.insight.startswith("Among NITs in Tamil Nadu only:")
    with pytest.raises(NirfInputError, match="No IIM is ranked in Medical"):
        run("univariate", "rank_distribution", {"category": "Medical"}, types=["IIM"])


QUESTION = "Which IITs improved the most in Engineering since 2019?"


@pytest.mark.parametrize("params", [
    {"category": "Engineering", "start_year": 2019, "institute_types": ["IIT"]},     # the model uses the option
    {"category": "Engineering", "start_year": "since 2019", "institutions": ["IITs"]},  # ... or writes "IITs"
    {"category": "Engineering", "start_year": 2019},                                   # ... or forgets it
])
def test_which_iits_improved_the_most_in_the_chat(params):
    a = ask(params, "biggest_movers", "trends", question=QUESTION)
    assert a.kind == "chart", a.message
    assert a.plan["resolved_call"]["institute_types"] == ["IIT"]
    assert a.plan["resolved_call"]["params"]["start_year"] == 2019
    assert _only_iits(a.result.table)
    assert a.result.fig.layout.title.text.startswith("Among IITs only")
    assert a.result.insight.startswith("Among IITs only:")
    assert any(s.startswith("Only IITs are included") for s in a.assumptions)


def test_all_iims_in_the_chat_and_a_named_iit_stays_an_institution():
    a = ask({"category": "Management", "institutions": ["all IIMs"]}, "rank_distribution", "univariate",
            question="How are all IIMs spread over the rank bands?")
    assert a.plan["resolved_call"]["institute_types"] == ["IIM"]
    a = ask({"institutions": ["IIT Bombay"], "category": "Engineering"}, "rank_trajectory", "trends",
            question="How has IIT Bombay ranked?")
    assert "institute_types" not in a.plan["resolved_call"]


def test_explore_page_type_filter():
    from tests.app_helpers import html_text, open_page, set_widget
    at = open_page("views/mobility.py")
    at = set_widget(at, "multiselect", "x-mobility-types", ["IIT"])
    assert not at.exception
    assert "Among IITs only" in html_text(at)
