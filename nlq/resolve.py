"""Name resolution: what people type -> the names used in the master table.

The language model copies names and phrases from the question; this module turns them into data
values with fixed rules, and writes down every translation as a plain-English assumption that the
chat shows ("'iitb' = Indian Institute of Technology Bombay, Mumbai"). Rules, in order:
  * institutions: compact short forms (iitb, iitkgp, iima, nitt) -> 'IIT Bombay' ...; city synonyms
    (Bombay = Mumbai); then core.data.find_institution (short forms, every published spelling, word
    match in any order, close spelling with rapidfuzz);
  * states: two-letter codes and old names (TN, KA, UP, Orissa, Pondicherry), then core.data.check_states;
  * parameters: everyday words (research -> rpc, teaching -> tlr, placements -> go, reputation -> pr);
  * categories: everyday words (engg, B-schools, pharma, universities) -> the NIRF category;
  * years: numbers, ranges and phrases ("last 3 years", "since 2020", "latest") -> the years the
    category was actually published in.
"""

from __future__ import annotations

import re

from core.data import (LATEST_YEAR, PARAMETERS, RESEARCH_PARAMETERS, SHORT, YEARS, NirfInputError,
                       category_years, check_category, check_states, find_institution, fmt_years,
                       institution_names)

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
CITY_SYNONYMS = {"mumbai": "bombay", "chennai": "madras", "kolkata": "calcutta", "trichy": "tiruchirappalli",
                 "surathkal": "karnataka", "kgp": "kharagpur", "benaras": "varanasi", "banaras": "varanasi"}
FAMOUS = {"iisc": "Indian Institute of Science", "iisc bangalore": "Indian Institute of Science",
          "du": "University of Delhi", "delhi university": "University of Delhi",
          "jadavpur": "Jadavpur University", "manipal": "Manipal Academy of Higher Education",
          "bits pilani": "Birla Institute of Technology and Science Pilani", "bits": "Birla Institute of "
          "Technology and Science Pilani", "jnu": "Jawaharlal Nehru University", "bhu": "Banaras Hindu University",
          "amu": "Aligarh Muslim University", "aiims": "All India Institute of Medical Sciences Delhi",
          "aiims delhi": "All India Institute of Medical Sciences Delhi", "nlsiu": "National Law School of "
          "India University", "nls": "National Law School of India University"}


def _expand_compact(text: str) -> str:
    """'iitb' -> 'IIT Bombay', 'IIM-A' -> 'IIM Ahmedabad', 'Bombay IIT' stays (word order is handled later)."""
    t = re.sub(r"[\s.\-]+", " ", text.strip().lower())
    if t in FAMOUS:
        return FAMOUS[t]
    m = re.fullmatch(r"(iiit|iit|iim|nit) ?([a-z()]+)", t)
    if m and m.group(2) in CAMPUS_CODES[m.group(1)]:
        return f"{m.group(1).upper()} {CAMPUS_CODES[m.group(1)][m.group(2)]}"
    words = [CITY_SYNONYMS.get(w, w) for w in t.split()]
    return " ".join(words)


def resolve_institution(text: str) -> tuple[str, str | None]:
    """(institution_key, assumption or None). Raises NirfInputError with suggestions when nothing fits."""
    text = str(text).strip()
    attempts = list(dict.fromkeys([text, _expand_compact(text)]))
    error: NirfInputError | None = None
    for attempt in attempts:
        try:
            key = find_institution(attempt)
        except NirfInputError as e:
            error = error or e
            continue
        name = institution_names([key])[key]
        note = None if name.lower() == text.lower() else f"'{text}' = {name}."
        return key, note
    raise error


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
    """(official state name, assumption or None)."""
    t = re.sub(r"[\s.&]+", " ", str(text).strip().lower()).strip()
    official = STATE_CODES.get(t) or STATE_CODES.get(t.replace(" ", ""))
    name = check_states([official or text])[0]
    return name, (None if name.lower() == str(text).strip().lower() else f"'{text}' = {name}.")


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
    return code, (None if plain == code else f"'{text}' = {SHORT[code]}.")


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
    return name, (None if name.lower() == str(text).strip().lower() else f"'{text}' = the {name} ranking.")


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
        return available, f"'{value}' = every {where}year ({fmt_years(available)})."
    if count and not numbers and any(w in text for w in ("last", "past", "recent", "pichhle", "pichle", "latest")):
        n = int(count.group(1)) if count.group(1).isdigit() else _NUMBER_WORDS[count.group(1)]
        years = available[-n:]
        return years, f"'{value}' = the latest {len(years)} {where}years in the data ({fmt_years(years)})."
    if numbers and any(w in text for w in ("since", "from", "after", "onwards", "se ")) and len(numbers) == 1:
        years = [y for y in available if y >= numbers[0]]
        return years, f"'{value}' = {fmt_years(years)}."
    if numbers and any(w in text for w in ("before", "until", "till", "up to", "upto")) and len(numbers) == 1:
        years = [y for y in available if y <= numbers[0]]
        return years, f"'{value}' = {fmt_years(years)}."
    if len(numbers) == 2:
        lo, hi = sorted(numbers)
        years = [y for y in available if lo <= y <= hi]
        return years, None
    if numbers:
        return sorted(set(numbers)), None
    if any(w in text for w in ("latest", "this year", "current", "recent", "now", "newest", "last year")):
        latest = available[-1] if available else LATEST_YEAR
        return [latest], f"'{value}' = {latest}, the latest {where}ranking in the data."
    if any(w in text for w in ("first", "earliest", "oldest")):
        return [available[0]], f"'{value}' = {available[0]}, the first {where}ranking in the data."
    raise NirfInputError(f"'{value}' is not a year or a time period I can read. "
                         f"{where or 'NIRF '}rankings exist for {fmt_years(available)}.")
