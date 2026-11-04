"""Name resolution: what people type -> the names used in the master table.

The language model copies names and phrases from the question; this module turns them into data
values with fixed rules, and writes down every translation as a plain-English sentence that the
chat shows under the answer ("I read 'iitb' as Indian Institute of Technology Bombay."). Rules, in order:
  * institutions: known short forms first (iitb, iitkgp, iima, LPU, IIIT Bangalore ...), then
    core.data.match_institution: exact name, word match, close spelling last, with two guards (a typed
    family such as IIIT only matches that family; a typed place must be the institution's city or
    state), then institutions that took part but were never ranked, then the family swap
    ("There's no IIT Bangalore in the NIRF rankings, so I assumed you meant IIIT Bangalore ...");
  * states: two-letter codes and old names (TN, KA, UP, Orissa, Pondicherry), then core.data.check_states;
  * parameters: everyday words (research -> rpc, teaching -> tlr, placements -> go, reputation -> pr);
  * categories: everyday words (engg, B-schools, pharma, universities) -> the NIRF category;
  * years: numbers, ranges and phrases ("last 3 years", "since 2020", "latest") -> the years the
    category was actually published in.
"""

from __future__ import annotations

import re
from typing import NamedTuple

from core.data import (LATEST_YEAR, PARAMETERS, PLACE_SYNONYMS, RESEARCH_PARAMETERS, SHORT, YEARS,
                       NirfInputError, category_years, check_category, check_states, fmt_years,
                       institution_names, match_institution, short_label)

# ---------- institutions ----------

# Letters after IIT / IIM / NIT / IIIT in compact forms like "iitb" or "iimahmedabad".
CAMPUS_CODES = {
    "iit": {"b": "Bombay", "d": "Delhi", "m": "Madras", "k": "Kanpur", "kgp": "Kharagpur", "r": "Roorkee",
            "g": "Guwahati", "h": "Hyderabad", "bhu": "(BHU) Varanasi", "i": "Indore", "p": "Patna",
            "j": "Jodhpur", "bbs": "Bhubaneswar", "gn": "Gandhinagar", "rpr": "Ropar", "ism": "(ISM) Dhanbad",
            "dh": "(ISM) Dhanbad", "mandi": "Mandi", "pkd": "Palakkad", "tp": "Tirupati", "jammu": "Jammu"},
    "iim": {"a": "Ahmedabad", "b": "Bangalore", "c": "Calcutta", "l": "Lucknow", "k": "Kozhikode",
            "i": "Indore", "u": "Udaipur", "t": "Tiruchirappalli", "r": "Raipur", "s": "Shillong"},
    "nit": {"t": "Tiruchirappalli", "k": "Karnataka", "w": "Warangal", "r": "Rourkela", "c": "Calicut",
            "s": "Silchar", "d": "Durgapur", "j": "Jamshedpur"},
    "iiit": {"h": "Hyderabad", "d": "Delhi", "b": "Bangalore", "a": "Allahabad"},
}
# Place words used only after IIT / IIM / NIT / IIIT ('NIT Surathkal', 'IIT Banaras'). Spellings of the same
# place (Mumbai = Bombay, Bengaluru = Bangalore) are handled for every name by core.data.PLACE_SYNONYMS.
CITY_SYNONYMS = {"surathkal": "karnataka", "kgp": "kharagpur", "benaras": "varanasi", "banaras": "varanasi"}
FAMOUS = {"iisc": "Indian Institute of Science", "iisc bangalore": "Indian Institute of Science",
          "du": "University of Delhi", "delhi university": "University of Delhi",
          "jadavpur": "Jadavpur University", "manipal": "Manipal Academy of Higher Education",
          "bits pilani": "Birla Institute of Technology and Science Pilani", "bits": "Birla Institute of "
          "Technology and Science Pilani", "jnu": "Jawaharlal Nehru University", "bhu": "Banaras Hindu University",
          "amu": "Aligarh Muslim University", "aiims": "All India Institute of Medical Sciences Delhi",
          "aiims delhi": "All India Institute of Medical Sciences Delhi", "nlsiu": "National Law School of "
          "India University", "nls": "National Law School of India University",
          "kiit": "Kalinga Institute of Industrial Technology", "lpu": "Lovely Professional University",
          "iiit hyderabad": "International Institute of Information Technology Hyderabad",
          "iiith": "International Institute of Information Technology Hyderabad",
          "iiit bangalore": "International Institute of Information Technology Bangalore",
          "iiitb": "International Institute of Information Technology Bangalore",
          "nmims": "SVKM's Narsee Monjee Institute of Management Studies, Mumbai",
          "isi": "Indian Statistical Institute", "isi kolkata": "Indian Statistical Institute",
          "mdi": "Management Development Institute", "mdi gurgaon": "Management Development Institute",
          "fms": "Faculty of Management Studies", "fms delhi": "Faculty of Management Studies",
          "pgimer": "Post Graduate Institute of Medical Education and Research",
          "pgi chandigarh": "Post Graduate Institute of Medical Education and Research",
          "cmc vellore": "Christian Medical College Vellore", "cmc": "Christian Medical College Vellore",
          "iift": "Indian Institute of Foreign Trade", "uoh": "University of Hyderabad",
          "iiit delhi": "Indraprastha Institute of Information Technology",
          "iiitd": "Indraprastha Institute of Information Technology"}


_FAMOUS = {" ".join(PLACE_SYNONYMS.get(w, w) for w in k.split()): v for k, v in FAMOUS.items()}


def _short_form(text: str) -> tuple[str, bool]:
    """(the name to look up, True if it is a known short form). Bengaluru = Bangalore, Mumbai = Bombay here too.

    'iitb' -> 'IIT Bombay'; 'IIM-A' -> 'IIM Ahmadabad'; 'iiitb', 'IIIT Bengaluru' -> International Institute
    of Information Technology Bangalore; 'NIT Surathkal' -> 'NIT karnataka'; anything else is returned as typed.
    """
    t = re.sub(r"[\s.\-]+", " ", text.strip().lower()).strip()
    places = " ".join(PLACE_SYNONYMS.get(w, w) for w in t.split())
    if places in _FAMOUS:
        return _FAMOUS[places], True
    m = re.fullmatch(r"(iiit|iit|iim|nit) ?([a-z()]+)", t)
    if m and m.group(2) in CAMPUS_CODES[m.group(1)]:
        short = f"{m.group(1).upper()} {CAMPUS_CODES[m.group(1)][m.group(2)]}"
        return FAMOUS.get(short.lower(), short), True      # 'iiith' -> IIIT Hyderabad -> International Institute ...
    words = t.split()
    if words and words[0] in CAMPUS_CODES:                 # 'NIT Surathkal', 'IIT Banaras', 'IIT KGP'
        return " ".join(CITY_SYNONYMS.get(w, w) for w in words), False
    return text, False


class ResolvedInstitution(NamedTuple):
    key: str
    note: str | None                    # the assumption, as a plain sentence (None = taken as typed)
    alternatives: list[str]             # other institutions the person may have meant (keys)


def resolve_institution(text: str) -> ResolvedInstitution:
    """(institution_key, assumption or None, alternative keys).

    Order: an institution key; the known short forms above (iitb, LPU, IIIT Bangalore ...); then
    core.data.match_institution: exact name, word match, close spelling last, with the family and place
    guards, then the never-ranked participants (NotRankedError) and the family swap ('IIT Bangalore' ->
    IIIT Bangalore, with IISc and IIM Bangalore as alternatives). Raises NirfInputError when nothing fits.
    """
    text = str(text).strip()
    target, short = _short_form(text)
    m = match_institution(target, typed=text)
    name = institution_names([m.key])[m.key]
    if m.how == "swap":
        label = short_label(m.key)
        meant = label if label == name else f"{label} ({name})"
        return ResolvedInstitution(m.key, f"There's no {text} in the NIRF rankings, so I assumed you meant {meant}.",
                                   m.alternatives)
    if m.how == "key" or name.lower() == text.lower():
        return ResolvedInstitution(m.key, None, [])
    if m.how == "spelling" and not short:
        return ResolvedInstitution(m.key, f"I read '{text}' as {name}, the closest spelling in the NIRF data.", [])
    return ResolvedInstitution(m.key, f"I read '{text}' as {name}.", [])


# ---------- states ----------

STATE_CODES = {
    "ap": "Andhra Pradesh", "ar": "Arunachal Pradesh", "as": "Assam", "br": "Bihar", "cg": "Chhattisgarh",
    "ct": "Chhattisgarh", "ch": "Chandigarh", "dl": "Delhi", "ncr": "Delhi", "new delhi": "Delhi", "ga": "Goa",
    "gj": "Gujarat", "hr": "Haryana", "hp": "Himachal Pradesh", "jk": "Jammu and Kashmir", "j and k":
    "Jammu and Kashmir", "jh": "Jharkhand", "ka": "Karnataka", "kar": "Karnataka", "kl": "Kerala",
    "mp": "Madhya Pradesh", "mh": "Maharashtra", "mn": "Manipur", "ml": "Meghalaya", "mz": "Mizoram",
    "nl": "Nagaland", "or": "Odisha", "od": "Odisha", "orissa": "Odisha", "py": "Puducherry",
    "pondicherry": "Puducherry", "pb": "Punjab", "rj": "Rajasthan", "sk": "Sikkim", "tn": "Tamil Nadu",
    "tamilnadu": "Tamil Nadu", "ts": "Telangana", "tg": "Telangana", "tr": "Tripura", "up": "Uttar Pradesh",
    "uk": "Uttarakhand", "uttaranchal": "Uttarakhand", "wb": "West Bengal", "bengal": "West Bengal",
}


def resolve_state(text: str) -> tuple[str, str | None]:
    """(official state name, assumption or None). A city typed as a place becomes its state ('Bangalore' ->
    Karnataka), because the data is filtered by state, and the answer says so."""
    from nlq.adapt import city_state          # imported here: adapt needs the master table, resolve does not

    t = re.sub(r"[\s.&]+", " ", str(text).strip().lower()).strip()
    official = STATE_CODES.get(t) or STATE_CODES.get(t.replace(" ", ""))
    try:
        name = check_states([official or text])[0]
    except NirfInputError:
        state = city_state(text)
        if state is None:
            raise
        return state, f"'{str(text).strip()}' = {state} (we filter by state, not city)."
    return name, (None if name.lower() == str(text).strip().lower() else f"I read '{text}' as {name}.")


# ---------- parameters ----------

PARAMETER_WORDS = {
    "score": "score", "overall": "score", "overall score": "score", "total": "score", "total score": "score",
    "nirf score": "score", "rank": "rank", "ranking": "rank",
    "teaching": "tlr", "teaching learning and resources": "tlr", "resources": "tlr", "faculty": "tlr",
    "research": "rpc", "research and professional practice": "rpc", "publications": "rpc", "papers": "rpc",
    "graduation": "go", "graduation outcomes": "go", "outcomes": "go", "placements": "go", "placement": "go",
    "outreach": "oi", "inclusivity": "oi", "outreach and inclusivity": "oi", "diversity": "oi",
    "inclusion": "oi", "perception": "pr", "reputation": "pr", "peer perception": "pr", "brand": "pr",
    "quantitative research": "qnr", "qualitative research": "qlr",
    "student faculty and collaboration": "sfc",
}
ALL_PARAMETERS = ["score", "rank", *dict.fromkeys(PARAMETERS + RESEARCH_PARAMETERS)]


def resolve_parameter(text: str) -> tuple[str, str | None]:
    """(column code such as 'rpc', assumption or None). Raises NirfInputError for an unknown word."""
    t = re.sub(r"[^a-z ]+", " ", str(text).lower().replace("&", " and "))
    t = " ".join(t.split())
    code = t.replace(" ", "") if t.replace(" ", "") in ALL_PARAMETERS else PARAMETER_WORDS.get(t)
    if code is None:
        words = [PARAMETER_WORDS[w] for w in t.split() if w in PARAMETER_WORDS]
        code = words[0] if len(set(words)) == 1 else None
    if code is None:
        raise NirfInputError(f"'{text}' is not a NIRF number. Use the overall score or a parameter: "
                             f"TLR (teaching), RPC (research), GO (graduation outcomes), OI (outreach), "
                             f"PR (perception).")
    plain = t.replace(" ", "")
    return code, (None if plain == code else f"I read '{text}' as {SHORT[code]}.")


# ---------- categories ----------

CATEGORY_WORDS = {
    "overall": "Overall", "all": "Overall", "general": "Overall",
    "engg": "Engineering", "engineering colleges": "Engineering", "btech": "Engineering", "tech": "Engineering",
    "mba": "Management", "b school": "Management", "b schools": "Management", "business schools": "Management",
    "mgmt": "Management", "management institutes": "Management", "pharma": "Pharmacy",
    "medical colleges": "Medical", "medicine": "Medical", "mbbs": "Medical", "law schools": "Law",
    "law colleges": "Law", "llb": "Law", "univ": "University", "universities": "University",
    "colleges": "College", "degree colleges": "College", "research": "Research Institutions",
    "research institutes": "Research Institutions", "architecture": "Architecture & Planning",
    "agri": "Agriculture & Allied Sectors", "agriculture": "Agriculture & Allied Sectors",
    "dental colleges": "Dental", "bds": "Dental", "open universities": "Open University",
    "skill universities": "Skill University", "state universities": "State Public University",
    "state public universities": "State Public University", "sdg institutions": "SDG",
    "sustainable development goals": "SDG",
}


def resolve_category(text: str) -> tuple[str, str | None]:
    """(standard category name, assumption or None)."""
    t = " ".join(re.sub(r"[^a-z& ]+", " ", str(text).lower()).split())
    name = check_category(CATEGORY_WORDS.get(t, text))
    return name, (None if name.lower() == str(text).strip().lower() else f"I read '{text}' as the {name} ranking.")


# ---------- years ----------

_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                 "nine": 9, "ek": 1, "do": 2, "teen": 3, "char": 4, "paanch": 5}


def resolve_years(value, category: str | None = None) -> tuple[list[int], str | None]:
    """Years for a number, a list, a range or a phrase, within the years the category was published.

    "latest"/"this year" -> the latest year; "last 3 years" -> the latest 3 published years;
    "since 2020" -> 2020 to the latest; "2018-2022" or "between 2018 and 2022" -> that range;
    "all years" -> every year. Returns (years, assumption or None).
    """
    available = category_years(category) if category else YEARS
    where = f"{category} " if category else ""
    if isinstance(value, bool) or value is None:
        return available, None
    if isinstance(value, (int, float)):
        return [int(value)], None
    if isinstance(value, (list, tuple)):
        out: list[int] = []
        for v in value:
            out += resolve_years(v, category)[0]
        return sorted(set(out)), None

    text = str(value).strip().lower()
    numbers = [int(n) for n in re.findall(r"\b(20[12]\d)\b", text)]
    count = re.search(r"\b(\d+|" + "|".join(_NUMBER_WORDS) + r")\s*(?:years?|yrs?|saal|sal)\b", text)
    if re.fullmatch(r"20[12]\d", text):
        return [int(text)], None
    if re.search(r"\b(all|every|whole|entire)\b", text) and not numbers:
        return available, f"I read '{value}' as every {where}year ({fmt_years(available)})."
    if count and not numbers and any(w in text for w in ("last", "past", "recent", "pichhle", "pichle", "latest")):
        n = int(count.group(1)) if count.group(1).isdigit() else _NUMBER_WORDS[count.group(1)]
        years = available[-n:]
        return years, f"I read '{value}' as the latest {len(years)} {where}years in the data ({fmt_years(years)})."
    if numbers and any(w in text for w in ("since", "from", "after", "onwards", "se ")) and len(numbers) == 1:
        years = [y for y in available if y >= numbers[0]]
        return years, f"I read '{value}' as {fmt_years(years)}."
    if numbers and any(w in text for w in ("before", "until", "till", "up to", "upto")) and len(numbers) == 1:
        years = [y for y in available if y <= numbers[0]]
        return years, f"I read '{value}' as {fmt_years(years)}."
    if len(numbers) == 2:
        lo, hi = sorted(numbers)
        years = [y for y in available if lo <= y <= hi]
        return years, None
    if numbers:
        return sorted(set(numbers)), None
    if any(w in text for w in ("latest", "this year", "current", "recent", "now", "newest", "last year")):
        latest = available[-1] if available else LATEST_YEAR
        return [latest], f"I read '{value}' as {latest}, the latest {where}ranking in the data."
    if any(w in text for w in ("first", "earliest", "oldest")):
        return [available[0]], f"I read '{value}' as {available[0]}, the first {where}ranking in the data."
    raise NirfInputError(f"'{value}' is not a year or a time period I can read. "
                         f"{where or 'NIRF '}rankings exist for {fmt_years(available)}.")
