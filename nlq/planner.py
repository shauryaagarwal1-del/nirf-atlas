"""The planner: question -> a checked JSON plan. The language model chooses WHAT to run; it never calculates.

Steps:
  1. build the instructions: the rules below + the catalog (nlq/catalog.py) + the last few turns of the
     chat (so "same for Engineering" can be understood);
  2. ask the model (nlq/llm.py) for ONLY a JSON object of one of four shapes:
       engine        {"type": "engine", "engine", "function", "params", "title", "assumptions", "notice"}
       custom        {"type": "custom", "filters", "group_by", "metric", "agg", "chart", ...}
       clarify       {"type": "clarify", "question", "options"}   when the question is truly ambiguous
       out_of_scope  {"type": "out_of_scope", "message"}          when the data cannot answer it
  3. check it: pydantic checks the shape and types, then executor.check_plan() checks that the engine,
     function, parameter names, groups and chart types really exist;
  4. if the JSON is invalid or the check fails, ask once more, sending the error message back.
Names, places and years are copied as the person typed them; nlq/resolve.py translates them later.
A prediction or an opinion ("Will IIT Mandi overtake IIT Jodhpur?", "Which is better?") is not refused:
the plan is the closest factual analysis, with an optional "notice" that the page shows in a highlighted
box above the chart ("I can't predict future rankings; here is how they have done so far.").
"""

from __future__ import annotations

import json
import re
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from nlq import llm
from nlq.catalog import NOT_IN_DATA, catalog_text


class _Plan(BaseModel):
    model_config = ConfigDict(extra="ignore")


class EnginePlan(_Plan):
    type: Literal["engine"]
    engine: str
    function: str
    params: dict[str, Any] = Field(default_factory=dict)
    title: str = ""
    assumptions: list[str] = Field(default_factory=list)
    follow_ups: list[str] = Field(default_factory=list)
    notice: str = ""            # shown above the chart, e.g. for a prediction answered with past data


class CustomFilters(_Plan):
    categories: list[str] = Field(default_factory=list)
    years: Any = None
    states: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    institutions: list[str] = Field(default_factory=list)
    rank_max: int | None = None


class CustomPlan(_Plan):
    type: Literal["custom"]
    filters: CustomFilters = Field(default_factory=CustomFilters)
    group_by: list[str] = Field(default_factory=list, max_length=3)
    metric: str = "score"
    agg: str = "mean"
    chart: str = "bar"
    x: str | None = None
    limit: int | None = None
    title: str = ""
    assumptions: list[str] = Field(default_factory=list)
    follow_ups: list[str] = Field(default_factory=list)
    notice: str = ""


class ClarifyPlan(_Plan):
    type: Literal["clarify"]
    question: str
    options: list[str] = Field(default_factory=list)


class OutOfScopePlan(_Plan):
    type: Literal["out_of_scope"]
    message: str


Plan = Annotated[Union[EnginePlan, CustomPlan, ClarifyPlan, OutOfScopePlan], Field(discriminator="type")]
PLAN = TypeAdapter(Plan)

RULES = f"""You are the question reader of NIRF Atlas, a dashboard of India's NIRF rankings 2017-2025.
Turn the user's question into ONE JSON object (no prose, no code fences). You never calculate or state
numbers: our own code runs the analysis you choose. Shapes:

1. {{"type": "engine", "engine": "<engine>", "function": "<function>", "params": {{...}},
    "title": "<the question restated in a few words>", "assumptions": ["<each choice you made>", ...],
    "follow_ups": ["<3 short questions the user could ask next>"], "notice": "<optional, see the rules>"}}
2. {{"type": "custom", "filters": {{"categories": [], "years": ..., "states": [], "regions": [],
    "institutions": [], "rank_max": null}}, "group_by": ["<x>", "<colour, optional>"], "metric": "<number or count>",
    "agg": "<mean|median|min|max|count>", "chart": "<chart>", "limit": null, "title": "...",
    "assumptions": [...], "follow_ups": [...]}}
3. {{"type": "clarify", "question": "<one short question back>", "options": ["<2-4 possible meanings>"]}}
4. {{"type": "out_of_scope", "message": "<friendly reason and what the data CAN answer>"}}

Rules:
- Prefer an analysis (shape 1). Use engine and function names and parameter names exactly as in the catalog.
  Only put parameters you need in params; leave out defaults.
- Use shape 2 only when no analysis fits (e.g. an average per region or per category as a bar chart).
- Use shape 3 only when you cannot pick a sensible reading. Otherwise choose sensible defaults and list each
  one in "assumptions" in plain English (e.g. "Category: Overall, because none was named").
- Use shape 4 for anything not about NIRF rankings or not in the data ({NOT_IN_DATA}).
- Predictions and opinions ("Will IIT Mandi overtake IIT Jodhpur?", "Who will be #1 in 2026?", "Which is
  better, IIT Madras or IIT Bombay?") are NOT shape 4: answer with the closest factual analysis (usually
  trends.rank_trajectory of the named institutions, or trends.top_n_race / the top of the latest ranking) and
  set "notice": "I can't predict future rankings; here is how they have done so far." (for an opinion: "I can't
  judge which is better; here is how they compare in the NIRF rankings."). Never add a forecast.
- Category: Overall unless the question names or clearly implies one ("engineering colleges" -> Engineering,
  "B-schools" -> Management, "universities" -> University). "colleges"/"institutes" in general mean Overall.
  EXCEPTION: when the question names institutions but no category, leave "category" out of params; our code
  picks the ranking those institutions are actually in (e.g. IIIT Bangalore is ranked only in Engineering).
- Institutions: write names as the user typed them or their common short name (e.g. "IIT Bombay", "iitb").
  A vague name ("NIT", "IIT", "Christian Medical College", which has two campuses) is still written as typed
  in an engine plan: our code offers the real institutions to choose from.
- A rank question about one institution (any institution, even one ranked only in bands such as 101-150) is
  trends.rank_trajectory; our code draws its rank bands when NIRF published no exact rank. Its score or
  parameters is trends.parameter_trends.
- States: write them as typed (e.g. "TN", "Karnataka"). Any analysis can be limited to institutions of some
  states by adding "states": [...] to params, even if the function has no states parameter. A city used as
  a place ("Bangalore colleges", "colleges in Pune") goes in "states" as typed; our code turns it into its
  state. A region ("South India", "the north-east") also goes in "states" as typed.
- Institute types: any analysis can be limited to one kind of institute by adding "institute_types": [...]
  to params, with codes IIT, NIT, IIIT, IIM, IISER, AIIMS, NLU, NIPER. "Which IITs improved the most?" =
  trends.biggest_movers with "institute_types": ["IIT"]; "all IIMs", "the NITs" likewise. Not for one named
  institute ("IIT Bombay" stays an institution).
- Two questions in one message: plan the first and put the second, written out in full, FIRST in follow_ups.
- Parameters: use codes score, tlr (teaching), rpc (research), go (graduation outcomes, placements),
  oi (outreach, inclusivity), pr (perception, reputation).
- Years: integers when given, even a year the category does not have (e.g. SDG 2019, or 2026): our code moves
  it to the nearest year that exists and says so. For a time phrase, copy the phrase as a string into the year
  parameter, e.g. "years": "last 3 years", "start_year": "since 2020", "year": "latest".
- "top N" in the sense "the N best" sets the function's n / top_n / top parameter.
- "Every year", "always", "each year it was ranked" mean ALL the years the category was published (see the
  catalog), e.g. min_years = 3 for a category ranked 2023-2025; never 1, which means "at least once".
- "From 2024 to 2019" (later year first): copy the years as given; our code puts them in order.
- Understand typos, abbreviations and Hinglish (e.g. "kaun sa", "sabse zyada" = most, "pichhle 5 saal" =
  last 5 years, "badha" = increased, "gira" = fell).
- Follow-up questions must be answerable with this data and be different from the question asked.
"""


class PlanError(Exception):
    """The model's reply was not a valid plan, even after one retry. `reply` is its last answer."""

    def __init__(self, message: str, reply: str = ""):
        super().__init__(message)
        self.reply = reply


def system_prompt() -> str:
    return RULES + "\n\nCATALOG\n\n" + catalog_text()


def _user_prompt(question: str, history: list[tuple[str, dict]] | None) -> str:
    parts = []
    for q, plan in (history or [])[-3:]:
        parts.append(f"Earlier question: {q}\nEarlier plan: {json.dumps(plan, ensure_ascii=False)}")
    parts.append(f"Question: {question}")
    return "\n\n".join(parts)


def _extract_json(reply: str) -> Any:
    """The JSON object in the reply (tolerates ```json fences or a sentence around it)."""
    text = reply.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise


def parse_plan(reply: str) -> _Plan:
    """Reply text -> a validated plan object. Raises ValueError with a readable reason."""
    try:
        data = _extract_json(reply)
    except json.JSONDecodeError as e:
        raise ValueError(f"The reply is not valid JSON ({e.msg} at character {e.pos}).") from None
    if isinstance(data, list) and len(data) == 1:
        data = data[0]
    try:
        plan = PLAN.validate_python(data)
    except ValidationError as e:
        problems = "; ".join(f"{'.'.join(map(str, err['loc'])) or 'plan'}: {err['msg']}" for err in e.errors()[:6])
        raise ValueError(f"The JSON does not match an allowed shape: {problems}.") from None
    from nlq.executor import check_plan          # imported here: executor imports this module's classes
    problems = check_plan(plan)
    if problems:
        raise ValueError("The plan names things that do not exist: " + "; ".join(problems) + ".")
    return plan


def plan_question(question: str, history: list[tuple[str, dict]] | None = None, complete=None) -> _Plan:
    """Ask the model for a plan for `question` and return it checked.

    history: earlier (question, plan dict) pairs of this chat, newest last. complete: the model call
    (default nlq.llm.complete; tests pass a stand-in). Raises llm.LLMError when the model cannot be
    reached, PlanError when it answers twice without a valid plan.
    """
    complete = complete or llm.complete
    system, user = system_prompt(), _user_prompt(question, history)
    reply = complete(system, user)
    try:
        return parse_plan(reply)
    except ValueError as first:
        retry = (f"{user}\n\nYour previous answer was:\n{reply}\n\nIt was rejected: {first}\n"
                 f"Answer again with ONE corrected JSON object only.")
        reply = complete(system, retry)
        try:
            return parse_plan(reply)
        except ValueError as second:
            raise PlanError(f"The question could not be turned into a valid plan: {second}", reply) from None
