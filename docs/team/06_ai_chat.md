# 06 · Ask NIRF: from a typed question to a chart

**In one sentence:** a language model (Google Gemini) reads the question and writes a small **JSON plan**
("which analysis, with which settings"); **our code** checks the plan, translates the names and runs the same
engines as the rest of the dashboard. **The model never sees the data and never calculates a number.**

Deeper reference: `docs/methods.md`, section "Ask NIRF (Level 3)".

---

## 1. What it does and why

Level 3 (5 marks) asks for a chatbox that turns a typed question into a data query and a chart. The risk with
language models is that they *make things up* (hallucinate), including numbers. So we split the work:

| Job | Who does it | Why |
|---|---|---|
| Understand the question (typos, Hinglish, short forms, "same for Engineering") | Language model | That is what language models are good at |
| Choose the analysis and its settings | Language model, but only from **our list** | It can only pick something we built and explained |
| Check the plan, translate names, fit years | **Our code** (fixed rules) | Predictable and testable |
| Calculate every number, draw the chart | **Our engines** on the master table | Same numbers as the rest of the dashboard |

```
 "Karnataka vs TN engineering colleges"
            |
            v
 +---------------------+   catalog of our analyses, columns, categories, years, states, parameters
 |  1. Gemini reads    | <-------------------------------------------------------------------------
 |     the question    |   (generated from our code; the model gets NO data rows)
 +----------+----------+
            |  writes ONE JSON plan
            v
   {"type": "engine", "engine": "geography", "function": "compare_states",
    "params": {"states": ["Karnataka", "TN"], "category": "engineering"},
    "assumptions": ["All years 2017-2025"], "follow_ups": [...]}
            |
            v
 +---------------------+   2. CHECK: valid JSON? allowed shape? does geography.compare_states exist?
 |  our code           |      (if not: ask the model once more, with the error)
 |                     |   3. TRANSLATE: TN -> Tamil Nadu, engineering -> Engineering,
 |                     |      "last 3 years" -> 2023-2025, iitb -> IIT Bombay, research -> RPC
 |                     |   4. RUN: the same engine function as the Explore pages
 +----------+----------+
            v
   chart card + "How I understood your question" + 3 follow-up buttons
```

---

## 2. The four steps

1. **The catalog.** The model receives a text description that our code generates automatically: the columns and
   their meaning, the years, every category with the years it exists, the states, regions and parameter codes, and
   every engine function with its settings, its definition and method, and the Annexure questions that use it. A new
   analysis appears in the chat automatically.
2. **The plan.** The model must answer with exactly one JSON object of one of four shapes:
   - `engine`: run one of our analyses (engine, function, settings, title, assumptions, follow-ups, and an
     optional `notice` shown above the chart, e.g. for a prediction answered with past data);
   - `custom`: a simple group-and-summarise chart through the Chart Builder (filters, group by, metric, aggregation,
     chart type) for questions no ready-made analysis covers;
   - `clarify`: ask the user back, with options as buttons (e.g. "Which category do you mean?");
   - `out_of_scope`: politely decline ("what's the weather", fees, salaries). A prediction ("who will be #1 in
     2026?") is *not* declined: see "When the data does not fit the question" below.
   The shape and types are checked (with the pydantic library), then every name is checked against our code. If
   something is wrong, the model is asked once more with the error message.
3. **Name resolution (fixed rules, no model):**
   - institutions, in this order: known short forms (iitb, iitkgp, iima, nitt, LPU, IIIT Bangalore), the exact name,
     word matching ("IIT Madras", "Christian Medical College Vellore"), and close spelling **last**. Bengaluru =
     Bangalore, Mumbai = Bombay and so on everywhere. Two guards (see "How institution names are matched" below);
   - institutions that took part but were never ranked, and institutes that do not exist ("IIT Bangalore"), get a
     clear answer instead of a wrong match (also below);
   - states: codes and old names (TN, KA, UP, Orissa);
   - parameters: everyday words (research → RPC, teaching → TLR, placements → GO, reputation → PR);
   - categories: engg → Engineering, B-schools → Management;
   - years: numbers, ranges and phrases ("last 3 years" = the latest 3 years *that category* was published, "since
     2020", "latest", "pichhle 5 saal").
4. **Running.** Years are fitted to the function (a list, one year, or a first and last year). A state filter limits
   any analysis to those states. Settings a function does not have are dropped and listed. Only the eight engines'
   public functions or the Chart Builder can be called; **nothing the model writes is ever run as code** (a test
   checks that the chat code contains no `exec` or `eval`).

**What the page shows:** the chart card (chart, one-line answer, method, data + CSV), directly under it an
**"Assumed:"** box with every assumption as a plain sentence, buttons for the other institutions the person may have
meant ("Use IISc instead"), "How I understood your question" (the assumptions again and the exact plan we ran) and
three follow-up questions as buttons. Six example questions sit above the input box. Earlier turns are sent along,
so "same for Engineering" works.

### How institution names are matched (and the bugs this fixed)

We tested the chat and found that "IIIT Bangalore" was matched to *Bangalore Institute of Technology*, a different
college. The old finder expanded "IIIT" to "Indian Institute of Information Technology", and a spelling score
(which only counts shared letters) found "Bangalore ... Institute of Technology" close enough. The new rules:

1. **Order:** known short forms first, then the exact name, then word matching, and the spelling match **last**.
2. **Family guard:** if you type a family (IIT, IIIT, NIT, IIM, IISER, IISc, AIIMS, NLU, IIEST), the answer must be
   from that family. IIIT includes the Indian, International and Indraprastha Institutes of Information Technology.
   A name without a family, like "Bangalore Institute of Technology", can never match "IIIT Bangalore".
3. **Place guard:** for a spelling match, every city or state you type must be the institution's city or state.
4. **Took part, never ranked:** "IIIT Dharwad" is in NIRF's participant lists (Engineering and Overall, 2022-2025)
   but never in a ranked list. The chat says exactly that, with buttons for two similar ranked institutions in the
   same state and category (IIIT Bangalore, IIT Dharwad), instead of "no such institution".
5. **Family swap:** "IIT Bangalore" does not exist. The chat looks for other families in the same city (or state)
   in a fixed order (for IIT: IIIT, NIT, IIEST, IISc, IISER, IIM), picks the first and says so in the Assumed box:
   *"There's no IIT Bangalore in the NIRF rankings, so I assumed you meant IIIT Bangalore (International Institute
   of Information Technology Bangalore)."* The others are buttons: "Use IISc instead", "Use IIM Bangalore instead".
   A click re-runs the same plan with that institution, without asking the model again.
6. **Otherwise:** "No institution called X in the NIRF data", with at most 3 suggestions that pass both guards.

Every guess is shown as a sentence: "I read 'iitb' as Indian Institute of Technology Bombay.", "I read 'Jadavpur
Universty' as Jadavpur University, the closest spelling in the NIRF data." Tests: `tests/test_resolve_names.py`.

### When the data does not fit the question (`nlq/adapt.py`)

The model only reads the words; it does not know which lists an institution is in or in which years. So after the
names are resolved, fixed rules fit the plan to what the data really has, and every change is written in the
Assumed box. The chat never shows an empty chart for a year that does not exist and never invents a value.

| The question | What the data says | What the chat does |
|---|---|---|
| "Give me the line chart for rankings of IIIT Bangalore from 2017-2025" (no category) | IIIT Bangalore is not in the Overall ranking, only in Engineering (2018-2025) | Uses Engineering: *"IIIT Bangalore is not in the Overall ranking; it is ranked in Engineering (2018-2025), so I used Engineering."* Rule: Overall if every named institution is there in every year asked, else the category it is ranked in the most years (ties: the most recent). Several institutions: the category they share for the most years; none shared: one chart each |
| "IIT Dharwad Engineering rank 2017-2025" | Ranked only 2023-2025 | Shows 2023-2025: *"You asked for 2017-2025; IIT Dharwad is ranked in Engineering only in 2023-2025, so the chart shows those years."* |
| "SDG rankings in 2019" | SDG exists only in 2025 (Dental from 2020, Research 2021, Agriculture/Innovation 2023, Open/Skill/State Public University 2024) | Uses the nearest year that exists: *"SDG rankings exist only for 2025, so 2025 is shown (the nearest to 2019)."* |
| "Bangalore Institute of Technology rank" | Only bands: 201-250 (2020), 251-300 (2021), no exact rank, no score | Draws the **band chart** (point plot with error bars): each bar spans the band, no line, because a line through a band would invent a rank |
| "Bangalore Institute of Technology parameter scores" | NIRF published no scores for it | Says so, lists its bands, and offers a button "Show the rank bands chart" |
| "Will IIT Mandi overtake IIT Jodhpur?" / "Which is better, IIT Madras or IIT Bombay?" | We have no future data and no "better" | Not refused: the rank chart of the past, with a highlighted notice *"I can't predict future rankings; here is how they have done so far."* The answer states the plain fact: *"In 2025, IIT Mandi (rank 26) was ahead of IIT Jodhpur (rank 27) by 1 place; in 2017 ... by 37 places."* No forecast line |
| "NIT rank trend", "Christian Medical College" | 31 NITs; two CMC campuses (Vellore, Ludhiana) | "Which one did you mean?" with up to 4 buttons of real institutions, best known first |
| "Bangalore colleges", "colleges in Pune" | We filter by state, not city | *"'Bangalore' = Karnataka (we filter by state, not city)."* |
| Two questions in one message ("rank of IIT Bombay and which state has the most top 100 colleges") | | Answers the first, with a notice *"Your message asks two things; this chart answers the first. The second is the first suggestion below."* The second is the first follow-up button |
| "NIT ranking", "IIM ranks" (only a type of institute) | Most NITs are in the Engineering list (31, against 21 in Overall) | Today's top 10 NITs in Engineering, followed back in time; the answer starts "Among NITs only" and the Assumed box gives the counts |
| "Bangalore colleges in engineering 2025" | 7 Karnataka institutions have an exact Engineering rank in 2025 | Lists all 7 with their ranks; the title says "the 7 Engineering institutions with an exact rank", not "top 10" |

In a rank line (`rank_trajectory`) a year with only a band is a short vertical bar (no line through it) and the
answer lists it: *"In 2024 it was placed only in the 101-150 band."* Tests: `tests/test_edge_cases.py`.

---

## 3. When things go wrong (and why the demo is still safe)

| Problem | What the page does |
|---|---|
| No key, no internet, rejected key, used-up quota, unknown model, server problem | A plain message saying what happened and how to fix it |
| Daily free quota of one model used up | Tries the next Gemini model in the list (each has its own quota), and a spare key if one is set |
| Gemini cannot be reached at all | Offers the **closest sample questions without any model** (word overlap with the 40 questions); "Run Qx.y here" answers it in the chat |
| The question is ambiguous | The plan is `clarify`: a question back with buttons |
| The question is outside the data | The plan is `out_of_scope`: a polite explanation |
| A named institution is not in the chosen category | It is left out and the page says so, instead of failing |
| A named institution took part in NIRF but was never ranked ("IIIT Dharwad") | Says so, with the years and categories, and offers two similar ranked institutions |
| A named institute does not exist ("IIT Bangalore") | Uses the nearest other family in that city, says so in the Assumed box, and offers the others as buttons |
| No category named and the institution is not in Overall ("IIIT Bangalore") | Uses the category it is actually ranked in, and says so |
| Years asked that the institution or category does not have | Shows the years that exist (nearest year for a single year), and says so |
| A band-only college (no exact rank, no score) | Band chart for a rank question; "NIRF did not publish scores" + band-chart button for a score question |
| A prediction or opinion | The past as a chart, with a highlighted "I can't predict future rankings ..." notice |
| A vague name in a chart of named institutions ("rank trend of NIT") | "Which one did you mean?" with buttons of real institutions |
| A short request ("NIT ranking", "SDG ranking in 2019") | Drawn as a chart (the top of that list), not asked back or refused |

The sidebar shows a green or red dot: is a key loaded, and does Gemini accept it (checked without generating text).

**Accuracy test:** 33 varied questions (typos, Hinglish, abbreviations, informal phrasing, one custom chart, one
out-of-scope question, and 8 edge cases: not in Overall, missing years, a band-only college, two predictions, an
opinion, a vague name, a city), each with the analyses we accept as correct. Offline, each reference plan must
produce a chart from the expected analysis (or the "which one?" buttons); live, the model's plan must name an
expected analysis, and a prediction or opinion must carry its notice. Accuracy = correct plans ÷ 33
(`python -m scripts.nlq_accuracy`). The live part never runs inside a normal `pytest` (only with
`NIRF_LIVE_TESTS=1`), so testing on the demo day does not use up the free quota.

**Exam simulation:** 30 further examiner questions with tricky cases (`docs/exam_simulation.md`). The live model's
plans are recorded once in `tests/exam_chat_plans.json` and replayed offline by the tests. Two rules came out of it:
years given the wrong way round ("from 2024 to 2019") are put in order with a note, and "every year" means all the
years a category was published.

---

## 4. Key decisions (and why)

| Decision | Why |
|---|---|
| **The model plans, our code calculates** | No hallucinated numbers: every number comes from the cleaned table through an engine we can explain |
| **A fixed menu of analyses** (the catalog) instead of letting the model write code | Safe (no arbitrary code runs) and every answer uses a method already documented in `docs/methods.md` |
| **JSON with four allowed shapes, validated** | A machine-checkable answer; invalid plans are caught and retried once |
| **Temperature 0** | The same question gives the same plan (as deterministic as the model allows) |
| **Name resolution in our code, not the model** | Rules are predictable and testable; every translation is shown to the user |
| **Show "How I understood your question"** | Transparency: the examiner sees exactly what was run and can spot a misunderstanding |
| **Several fallbacks** (next model, spare key, sample-question matching) | The live demo cannot depend on one free quota or the internet |
| **Gemini** (Google) with the `google-genai` library | Free tier is enough for a student project; all model calls sit in one small module, so another model could be swapped in |

---

## 5. Concepts explained simply

- **Large language model (LLM):** a program trained on huge amounts of text that predicts likely next words. Good
  at understanding and producing language; not reliable at arithmetic or facts it was not given.
- **Hallucination:** when a language model states something false with confidence, e.g. a made-up rank.
- **Prompt:** the instructions and text sent to the model. Ours = the rules + the catalog + the question.
- **JSON:** a simple text format for structured data: `{"key": "value", "list": [1, 2]}`. Easy for code to check.
- **Schema validation:** checking that data has the expected shape and types (here with pydantic).
- **Temperature:** how random the model's answers are; 0 = always pick the most likely answer.
- **API and API key:** an API is how one program asks another for a service over the internet; the key is a secret
  password identifying our account. It lives in a `.env` file that is never uploaded to GitHub.
- **Quota / rate limit:** the free tier allows only a limited number of requests per day per model.
- **Natural-language query (NLQ):** asking a database a question in everyday language instead of a query language.
- **Entity resolution:** mapping "iitb" or "TN" to the exact institution or state in our table.

---

## 6. Likely viva questions with model answers

**Q1. How does the chat work, in simple steps?**
The user types a question. Gemini reads it, together with a catalog of our analyses generated from our code, and
writes a small JSON plan: which analysis to run and with which settings. Our code checks the plan, translates names
like "TN" or "iitb", and runs the same engine function as the dashboard pages. The page shows the chart, the
one-line answer, the method, the data, and how the question was understood.

**Q2. Does the language model calculate any numbers?**
No. It never sees the data and never calculates. It only chooses an analysis and its settings from our list. Every
number is calculated by our engines from the cleaned master table, so the chat gives exactly the same numbers as the
Question Bank and Explore pages.

**Q3. How do you stop the model from making things up or running something dangerous?**
The plan must be one of four JSON shapes, checked with a schema; every analysis name and setting is checked against
our code; invalid plans are retried once and otherwise rejected. The model's text is never executed as code. Only
our public engine functions or the Chart Builder can be called, and a test checks the chat code contains no
exec or eval.

**Q4. How does it understand typos, abbreviations or Hinglish?**
The model handles the language ("kaun se institutes hamesha top 10 mein rahe" means "which institutions stayed in
the top 10"). Our own rules then translate names: institution short forms and every NIRF spelling, close spellings,
state codes, everyday words for parameters, and phrases like "last 3 years" into real years for that category.
Every translation is written as a plain sentence in the "Assumed:" box under the answer.

**Q4b. Someone types "IIT Bangalore". What happens, and why not just pick the closest spelling?**
There is no IIT in Bangalore. A spelling score alone once matched "IIIT Bangalore" to Bangalore Institute of
Technology, because it only counts shared letters. Now the precise rules run first (short forms, exact name, word
match), a typed family (IIT, IIIT, NIT ...) can only match that family, and a typed city must be the institution's
city. When the institute does not exist, we take the next family in a fixed order in the same city (IIIT, then NIT,
IIEST, IISc, IISER, IIM), here IIIT Bangalore, write "There's no IIT Bangalore in the NIRF rankings, so I assumed you
meant IIIT Bangalore ...", and offer IISc and IIM Bangalore as one-click buttons.

**Q5. What if the question is ambiguous or outside the data?**
For an ambiguous question the model returns a "clarify" plan: it asks back, with options as buttons; a vague name
like "NIT" gets buttons of real NITs from our own code. For something outside the data (fees, salaries, the weather)
it returns "out of scope" with a short explanation. A prediction ("who will be #1 in 2026?") is answered with the
past and a notice instead of a refusal. If a named institution is not in the chosen category, it is left out and the
page says so.

**Q6. What if the internet or the API fails during the demo?**
The page explains the problem and the fix. If one model's free quota is used up, the next model is tried, and a spare
key if set. If no model can be reached, the page offers the closest of the 40 sample questions using simple word
overlap, which runs without any model. Every other page of the dashboard works offline.

**Q7. How accurate is it, and how did you test it?**
We wrote 33 varied test questions with typos, Hinglish, abbreviations, informal phrasing, a custom chart, an
out-of-scope question and 8 edge cases (an institution not in Overall, missing years, a band-only college,
predictions, an opinion, a vague name, a city), each with the analyses we accept as correct. Offline tests check
that each reference plan produces the expected chart; a live script asks Gemini all 33 and reports accuracy as
correct plans out of 33 (a prediction only counts if the notice is there).

**Q8. Can it answer a question that none of your analyses covers?**
Partly: for simple group-and-summarise questions the model returns a "custom" plan, which runs through our Chart
Builder (filters, a grouping, a number, count/mean/median, an allowed chart type), for example "average TLR per
region in Engineering over the years". It cannot invent a new statistical method; that is deliberate, because every
method must be one we can explain.

**Q9. Someone asks "Will IIT Mandi overtake IIT Jodhpur?". Why not refuse, and why not predict?**
We cannot predict: there is no 2026 data, and drawing a trend line into the future would be a guess dressed up as a
result. But refusing helps nobody. So the chat shows the closest facts, the two rank lines up to 2025, with a
highlighted notice "I can't predict future rankings; here is how they have done so far", and the answer states who
is ahead in the latest year and how the gap changed. The examiner gets facts, clearly labelled as the past.

**Q10. Why does "IIIT Bangalore from 2017-2025" show Engineering 2018-2025 and not Overall 2017-2025?**
IIIT Bangalore is not in the Overall ranking at all; it is ranked only in Engineering, from 2018. Defaulting to
Overall would give an error, and showing 2017 would show an empty year. Our rule: when no category is named, use
Overall only if every named institution is there in every year asked, otherwise the category it is ranked in for
the most years; then show only the years it is actually listed. Both choices are written in the Assumed box.

**Q11. Some colleges have no exact rank and no score. How do you show them?**
Below its exact-rank list NIRF publishes only a band, like 201-250, and no score; about 1,225 institution-category
pairs in our data only ever have a band. A line chart would need a number, and taking the middle of the band would
invent one. So we draw a point plot with error bars: each bar runs from the band's best to its worst rank, and an
exact rank, if any, is a dot. A score question about such a college says clearly that NIRF did not publish scores,
gives its bands and offers the band chart as a button.
