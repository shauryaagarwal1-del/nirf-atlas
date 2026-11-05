"""Global filters and institution pickers (Phase 15d).

Checked:
  * institution_options(category) lists only institutions listed in that category (exact rank or band):
    Medical has no Engineering-only college, Engineering has IIT Dharwad and IIIT Bangalore, a college NIRF
    placed only in Engineering bands is labelled "band only", and several categories give the union;
  * the global filters are drawn only on Home, the Explore pages and Data & Method; Question Bank, Chart
    Builder and Ask NIRF show a short note instead (Ask NIRF keeps its Gemini status box);
  * the filter values survive a visit to a page without them (Trends -> Ask NIRF -> Trends);
  * a sidebar change shows in the Explore page controls and in the Home chart;
  * a category change removes chosen institutions not listed in the new category, with a caption, in the
    Explore pages, the Question Bank and the Chart Builder.

    python -m pytest tests/test_filters.py -v
"""

import pytest

from core.data import MASTER_PATH, find_institution

if not MASTER_PATH.exists():
    pytest.skip("run `python -m pipeline.clean` first", allow_module_level=True)

from app.filters import institution_options, master  # noqa: E402
from app.nav import PAGES  # noqa: E402
from tests.app_helpers import chart_titles, html_text, open_page, set_widget, widget  # noqa: E402

NOTE = "This page uses its own controls. The sidebar filters apply to the Explore pages."


def categories_of() -> dict[str, set[str]]:
    df = master()
    return df.groupby("institution_key")["category_std"].agg(set).to_dict()


# ---------- institution_options(category) ----------

def test_medical_has_no_engineering_only_college():
    medical = institution_options("Medical")
    engineering_only = {k for k, cats in categories_of().items() if cats == {"Engineering"}}
    assert engineering_only and not engineering_only & set(medical)
    assert find_institution("IIT Dharwad") not in medical
    df = master()
    assert set(medical) == set(df.loc[df["category_std"].eq("Medical"), "institution_key"])


def test_engineering_lists_iit_dharwad_and_iiit_bangalore():
    engineering = institution_options("Engineering")
    for name in ("IIT Dharwad", "IIIT Bangalore"):
        key = find_institution(name)
        assert key in engineering
        assert "band only" not in engineering[key]                     # both had exact ranks


def test_band_only_engineering_college_is_labelled():
    df = master()
    eng = df[df["category_std"].eq("Engineering")]
    has_rank = eng.groupby("institution_key")["rank"].agg(lambda s: s.notna().any())
    band_only = has_rank[~has_rank].index
    assert len(band_only) > 0
    labels = institution_options("Engineering")
    assert all(labels[k].endswith(" · band only") for k in band_only)
    assert not any(labels[k].endswith("band only") for k in has_rank[has_rank].index)
    assert " · " in labels[band_only[0]].removesuffix(" · band only")   # still "Short name · City, State"


def test_several_categories_give_the_union():
    both = institution_options(["Engineering", "Medical"])
    assert set(both) == set(institution_options("Engineering")) | set(institution_options("Medical"))
    assert list(both.values()) == sorted(both.values(), key=str.lower)
    assert len(institution_options()) == master()["institution_key"].nunique()


# ---------- where the global filters are drawn ----------

@pytest.mark.parametrize("page", [p.path for p in PAGES])
def test_sidebar_filters_only_where_they_apply(page):
    at = open_page(page)
    assert not at.exception, [e.value for e in at.exception]
    info = next(p for p in PAGES if p.path == page)
    text = html_text(at)
    if info.global_filters:
        assert "Global filters" in text and NOTE not in text
    else:
        assert NOTE in text and "Global filters" not in text
    if page.endswith("ask_nirf.py"):
        assert "nirf-ai-status" in text                     # the Gemini status box stays


def test_filters_survive_a_page_without_them():
    at = open_page("views/trends.py")
    at = set_widget(at, "selectbox", "x-trends-category", "Engineering")
    at = set_widget(at, "multiselect", "x-trends-institutions", ["IIT Dharwad"])
    at.session_state["f_states"] = ["Karnataka"]
    at.session_state["f_top_n"] = 15
    at.run()
    before = {k: at.session_state[k] for k in ("f_category", "f_years", "f_states", "f_institutions", "f_top_n")}
    for page in ("views/ask_nirf.py", "views/question_bank.py", "views/chart_builder.py"):
        at.switch_page(page).run()
        assert not at.exception
        at.run()                                            # a second run on the same page
    at.switch_page("views/trends.py").run()
    after = {k: at.session_state[k] for k in before}
    assert after == before
    assert widget(at, "selectbox", "x-trends-category").value == "Engineering"
    assert widget(at, "multiselect", "x-trends-institutions").value == [find_institution("IIT Dharwad")]


def test_sidebar_change_shows_on_explore_controls_and_home_chart():
    at = open_page("views/home.py")
    assert "Overall" in chart_titles(at)[0]
    at.session_state["f_category"] = "Pharmacy"            # what the sidebar's category widget edits
    at.session_state["f_years"] = (2017, 2025)
    at.run()
    assert "Pharmacy" in chart_titles(at)[0]
    at.switch_page("views/trends.py").run()
    assert widget(at, "selectbox", "x-trends-category").value == "Pharmacy"
    assert "Pharmacy" in chart_titles(at)[0]


# ---------- category change drops institutions it does not list ----------

def test_explore_category_change_removes_unlisted_institutions():
    at = open_page("views/trends.py")
    at = set_widget(at, "selectbox", "x-trends-category", "Engineering")
    at = set_widget(at, "multiselect", "x-trends-institutions", ["IIT Dharwad", "IIT Madras"])
    at = set_widget(at, "selectbox", "x-trends-category", "Overall")
    assert at.session_state["f_institutions"] == [find_institution("IIT Madras")]
    assert "IIT Dharwad is not ranked in Overall, so it was removed." in [c.value for c in at.caption]
    assert widget(at, "multiselect", "x-trends-institutions").value == [find_institution("IIT Madras")]
    at = set_widget(at, "selectbox", "x-trends-category", "Medical")
    assert at.session_state["f_institutions"] == []
    assert "IIT Madras is not ranked in Medical, so it was removed." in [c.value for c in at.caption]
    assert not at.exception


def test_explore_institution_list_follows_the_category():
    at = open_page("views/trends.py")
    at = set_widget(at, "selectbox", "x-trends-category", "Medical")
    picker = widget(at, "multiselect", "x-trends-institutions")
    assert len(picker.options) == len(institution_options("Medical"))
    assert not any("Dharwad" in o for o in picker.options)


def test_question_bank_institutions_follow_the_question_category():
    at = open_page("views/question_bank.py", {"qb_q": "Q1.1"})
    picker = widget(at, "multiselect", "qb-Q1.1-institutions")
    assert len(picker.options) == len(institution_options("Overall"))
    at = set_widget(at, "selectbox", "qb-Q1.1-category", "Medical")
    assert widget(at, "multiselect", "qb-Q1.1-institutions").value == []
    assert "IIT Madras is not ranked in Medical, so it was removed." in [c.value for c in at.caption]
    assert len(widget(at, "multiselect", "qb-Q1.1-institutions").options) == len(institution_options("Medical"))
    assert not at.exception


def test_chart_builder_institutions_follow_the_chosen_categories():
    at = open_page("views/chart_builder.py")
    at = set_widget(at, "multiselect", "cb-categories", ["Engineering"])
    at = set_widget(at, "multiselect", "cb-institutions", ["IIT Dharwad"])
    at = set_widget(at, "multiselect", "cb-categories", ["Engineering", "Medical"])
    assert widget(at, "multiselect", "cb-institutions").value == [find_institution("IIT Dharwad")]
    at = set_widget(at, "multiselect", "cb-categories", ["Medical"])
    assert widget(at, "multiselect", "cb-institutions").value == []
    assert "IIT Dharwad is not ranked in Medical, so it was removed." in [c.value for c in at.caption]
    assert not at.exception
