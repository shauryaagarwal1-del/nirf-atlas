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
   - `engine`: run one of our analyses (engine, function, settings, title, assumptions, follow-ups);
   - `custom`: a simple group-and-summarise chart through the Chart Builder (filters, group by, metric, aggregation,
     chart type) for questions no ready-made analysis covers;
   - `clarify`: ask the user back, with options as buttons (e.g. "Which category do you mean?");
   - `out_of_scope`: politely decline ("what's the weather", fees, salaries, years after 2025).
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

The sidebar shows a green or red dot: is a key loaded, and does Gemini accept it (checked without generating text).

**Accuracy test:** 25 varied questions (typos, Hinglish, abbreviations, informal phrasing, one custom chart, one
out-of-scope question), each with the analyses we accept as correct. Offline, each reference plan must produce a
chart from the expected analysis; live, the model's plan must name an expected analysis. Accuracy = correct plans
÷ 25 (`python -m scripts.nlq_accuracy`). The live part never runs inside a normal `pytest` (only with
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
For an ambiguous question the model returns a "clarify" plan: it asks back, with options as buttons. For something
outside the data (fees, salaries, the weather, 2026 rankings) it returns "out of scope" with a short explanation. If
a named institution is not in the chosen category, it is left out and the page says so.

**Q6. What if the internet or the API fails during the demo?**
The page explains the problem and the fix. If one model's free quota is used up, the next model is tried, and a spare
key if set. If no model can be reached, the page offers the closest of the 40 sample questions using simple word
overlap, which runs without any model. Every other page of the dashboard works offline.

**Q7. How accurate is it, and how did you test it?**
We wrote 25 varied test questions with typos, Hinglish, abbreviations, informal phrasing, a custom chart and an
out-of-scope question, each with the analyses we accept as correct. Offline tests check that each reference plan
produces the expected chart; a live script asks Gemini all 25 and reports accuracy as correct plans out of 25.

**Q8. Can it answer a question that none of your analyses covers?**
Partly: for simple group-and-summarise questions the model returns a "custom" plan, which runs through our Chart
Builder (filters, a grouping, a number, count/mean/median, an allowed chart type), for example "average TLR per
region in Engineering over the years". It cannot invent a new statistical method; that is deliberate, because every
method must be one we can explain.
