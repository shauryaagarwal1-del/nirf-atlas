"""Tests for institution name matching in the chat and the dashboard (no AI model needed).

Checks the rules of core.data.match_institution and nlq.resolve.resolve_institution:
  * order: known short forms first, then exact names, word matching, and close spelling last;
  * family guard: 'IIIT Bangalore' is a IIIT, never 'Bangalore Institute of Technology';
  * family swap: 'IIT Bangalore' does not exist -> IIIT Bangalore, with IISc and IIM Bangalore offered,
    and the assumption written as a plain sentence;
  * never-ranked: 'IIIT Dharwad' took part in NIRF but was never ranked -> a clear message, not an error,
    with two similar ranked institutions from the same state and category;
  * common short forms and real names with typos resolve to the right institution.

    python -m pytest tests/test_resolve_names.py -v
"""

from __future__ import annotations

import pytest

from core.data import (MASTER_PATH, NirfInputError, NotRankedError, find_institution, institution_names,
                       match_institution)
from nlq.executor import execute, with_institution
from nlq.planner import EnginePlan
from nlq.resolve import resolve_institution

if not MASTER_PATH.exists():
    pytest.skip("run `python -m pipeline.clean` first", allow_module_level=True)

IIIT_BANGALORE = "INST-00804"            # International Institute of Information Technology Bangalore
BANGALORE_IT = "INST-01124"              # Bangalore Institute of Technology (a different college)


def key_of(full_name: str) -> str:
    """The key of an institution typed with its full published name."""
    return match_institution(full_name).key


# ---------- the bugs found in testing ----------

@pytest.mark.parametrize("typed", ["IIIT Bangalore", "iiitb", "IIIT Bengaluru", "iiit bangalore", "IIIT-Bangalore"])
def test_iiit_bangalore_is_never_bangalore_institute_of_technology(typed):
    key, _, _ = resolve_institution(typed)
    assert key == IIIT_BANGALORE and key != BANGALORE_IT
    if typed != "iiitb":                                          # 'iiitb' is a chat short form only
        assert match_institution(typed).key == IIIT_BANGALORE    # the dashboard's own matcher agrees


def test_bangalore_institute_of_technology_is_still_found():
    assert resolve_institution("Bangalore Institute of Technology").key == BANGALORE_IT
    assert find_institution("Bangalore Institute of Technology") == BANGALORE_IT


def test_iit_bangalore_is_swapped_to_iiit_bangalore_and_says_so():
    key, note, alternatives = resolve_institution("IIT Bangalore")
    assert key == IIIT_BANGALORE
    assert note == ("There's no IIT Bangalore in the NIRF rankings, so I assumed you meant IIIT Bangalore "
                    "(International Institute of Information Technology Bangalore).")
    assert alternatives == [key_of("Indian Institute of Science"), key_of("Indian Institute of Management Bangalore")]


def test_the_dashboard_pages_never_swap_silently():
    with pytest.raises(NirfInputError, match="There's no IIT Bangalore in the NIRF rankings. Did you mean "
                                             "IIIT Bangalore, IISc or IIM Bangalore"):
        find_institution("IIT Bangalore")


def test_iiit_dharwad_took_part_but_was_never_ranked():
    with pytest.raises(NotRankedError) as e:
        resolve_institution("IIIT Dharwad")
    message = str(e.value)
    assert "took part in NIRF (Engineering and Overall, 2022-2025)" in message
    assert "was not in the published ranked list in any year" in message
    # Similar ranked institutions from the same state (Karnataka) and category (Engineering).
    assert e.value.similar == [IIIT_BANGALORE, key_of("Indian Institute of Technology Dharwad")]


@pytest.mark.parametrize("typed, full_name", [
    ("IIT Dharwad", "Indian Institute of Technology Dharwad"),
    ("IIT Mandi", "Indian Institute of Technology Mandi"),
    ("IIT Jodhpur", "Indian Institute of Technology Jodhpur"),
    ("NIT Surathkal", "National Institute of Technology Karnataka, Surathkal"),
    ("IIIT Hyderabad", "International Institute of Information Technology Hyderabad"),
    ("IIIT Delhi", "Indraprastha Institute of Information Technology"),
    ("IIT Mumbai", "Indian Institute of Technology Bombay"),
    ("IIM Bengaluru", "Indian Institute of Management Bangalore"),
    ("IIT Kerala", "Indian Institute of Technology Palakkad"),             # the only IIT in that state
])
def test_short_forms_find_the_right_institute(typed, full_name):
    assert resolve_institution(typed).key == key_of(full_name), typed


# ---------- typos in real names (the spelling step, which runs last) ----------

@pytest.mark.parametrize("typed, full_name", [
    ("Jadavpur Universty", "Jadavpur University"),
    ("Anna Univercity", "Anna University"),
    ("Jamia Milia Islamia", "Jamia Millia Islamia"),
    ("Amrita Vishwa Vidyapeetam", "Amrita Vishwa Vidyapeetham"),
    ("Savitribai Phule Pune Univeristy", "Savitribai Phule Pune University"),
    ("Kalinga Institute of Industial Technology", "Kalinga Institute of Industrial Technology"),
    ("Banaras Hindu Univrsity", "Banaras Hindu University"),
    ("Osmania Univrsity", "Osmania University"),
    ("Lady Hardinge Medical Colege", "Lady Hardinge Medical College"),
    ("Christian Medical Colege Vellore", "Christian Medical College Vellore"),
    ("IIT Kharagpr", "Indian Institute of Technology Kharagpur"),
    ("IIT Gauhati", "Indian Institute of Technology Guwahati"),
    ("NIT Warangle", "National Institute of Technology Warangal"),
    ("IIM Ahmadabad", "Indian Institute of Management Ahmedabad"),
    ("IIIT Banglore", "International Institute of Information Technology Bangalore"),
])
def test_typos_in_real_names(typed, full_name):
    key, note, _ = resolve_institution(typed)
    assert key == key_of(full_name), typed
    assert note and note.startswith(f"I read '{typed}' as "), note       # the guess is said in a plain sentence


# ---------- the guards ----------

def test_a_family_query_only_matches_that_family():
    # 'Indian Institute of Management and Commerce' (a never-ranked college) is not an IIM: there is no
    # IIM in Hyderabad, so the chat swaps to the IIT there and offers the IIIT.
    key, note, alternatives = resolve_institution("IIM Hyderabad")
    assert key == key_of("Indian Institute of Technology Hyderabad")
    assert note.startswith("There's no IIM Hyderabad in the NIRF rankings")
    assert alternatives == [key_of("International Institute of Information Technology Hyderabad")]


def test_the_place_guard_blocks_a_spelling_match_in_another_city():
    # Close in spelling to many 'X Institute of Technology' names, but no IIT is in Bangalore: never a
    # spelling match to an IIT elsewhere, always the swap within Bangalore.
    assert resolve_institution("IIT Banglore").key == IIIT_BANGALORE


def test_unknown_names_get_at_most_three_suggestions():
    with pytest.raises(NirfInputError, match="No institution called 'IIT Chandigarh' in the NIRF data") as e:
        resolve_institution("IIT Chandigarh")
    assert str(e.value).count(";") <= 2
    with pytest.raises(NirfInputError, match="No institution called"):
        find_institution("Hogwarts School of Witchcraft")


# ---------- the chat: assumptions and one-click alternatives ----------

def _plan(name: str) -> EnginePlan:
    """A plan as the model writes it, including its own notes and follow-ups that repeat the name."""
    return EnginePlan(type="engine", engine="trends", function="rank_trajectory",
                      params=dict(institutions=[name], category="Engineering"), title=f"{name}: rank over time",
                      assumptions=[f"Institution: {name}, as named", "Category: Engineering, as named"],
                      follow_ups=[f"How does {name} compare with IIT Madras?"])


def test_the_chat_answers_iit_bangalore_with_the_swap_and_buttons():
    answer = execute(_plan("IIT Bangalore"), question="How has IIT Bangalore's rank changed?")
    assert answer.kind == "chart", answer.message
    assert answer.plan["resolved_call"]["params"]["institutions"] == [IIIT_BANGALORE]
    assert any(a.startswith("There's no IIT Bangalore in the NIRF rankings") for a in answer.assumptions)
    assert [a["label"] for a in answer.alternatives] == ["IISc", "IIM Bangalore"]
    # The title, follow-ups and notes name the institution actually shown, not the one that does not exist.
    assert answer.title == "IIIT Bangalore: rank over time"
    assert "Institution: IIT Bangalore, as named" not in answer.assumptions
    assert "How does IIIT Bangalore compare with IIT Madras?" in answer.follow_ups

    # "Use IIM Bangalore instead" re-runs the same plan with that institution (no model call).
    choice = answer.alternatives[1]
    plan, question = with_institution(answer.plan, "How has IIT Bangalore's rank changed?", choice["typed"],
                                      choice["key"], choice["label"])
    assert question == "How has IIM Bangalore's rank changed?"
    assert plan["params"]["institutions"] == [choice["key"]] and "resolved_call" not in plan
    assert plan["assumptions"] == ["Category: Engineering, as named", "You chose IIM Bangalore instead of IIT Bangalore."]


def test_the_chat_explains_a_never_ranked_institution():
    answer = execute(_plan("IIIT Dharwad"), question="Show IIIT Dharwad's rank")
    assert answer.kind == "not_ranked"
    assert "2022-2025" in answer.message and "no rank or score to chart" in answer.message
    labels = [a["label"] for a in answer.alternatives]
    assert labels == ["IIIT Bangalore", "IIT Dharwad"]
    plan, question = with_institution(answer.plan, "Show IIIT Dharwad's rank", "IIIT Dharwad",
                                      answer.alternatives[0]["key"], labels[0])
    rerun = execute(EnginePlan(**plan), question=question)
    assert rerun.kind == "chart" and question == "Show IIIT Bangalore's rank"


def test_a_name_typed_exactly_needs_no_assumption():
    name = institution_names([IIIT_BANGALORE])[IIIT_BANGALORE]
    assert resolve_institution(name).note is None
    assert resolve_institution(IIIT_BANGALORE).note is None             # a key, as the buttons pass it
