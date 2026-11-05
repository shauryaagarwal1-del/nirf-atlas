"""Name resolution: what people type -> the names used in the master table.

The language model copies names and phrases from the question; this module turns them into data
values with fixed rules, and writes down every translation as a plain-English sentence that the
chat shows under the answer ("I read 'iitb' as Indian Institute of Technology Bombay."). Rules, in order:
  * institutions: known short forms first (iitb, iitkgp, iima, LPU, IIIT Bangalore ...), then
    core.data.match_institution: exact name, word match, close spelling last, with two guards (a typed
    family such as IIIT only matches that family; a typed place must be the institution's city or
    state), then institutions that took part but were never ranked, then the family swap
    ("There's no IIT Bangalore in the NIRF rankings, so I assumed you meant IIIT Bangalore ...");
  * states: two-letter codes and old names (TN, KA, UP, Orissa, Pondicherry), then core.data.check_states
    (which also reads a one-letter slip such as 'Telengana'); regions ('South India', 'north east') -> the
    states of that region in the data's region column;
  * parameters: everyday words (research -> rpc, teaching -> tlr, placements -> go, reputation -> pr),
    also with 'score' ('research score'); NIRF sub-parameters (patents, median salary, faculty ratio) ->
    the parameter they belong to, with a note that NIRF publishes only the five parameter scores;
    in Research Institutions, research -> QnR (that list has no RPC);
  * categories: everyday words (engg, B-schools, pharma, MBA colleges, arts colleges) -> the NIRF
    category; nursing and polytechnics are said plainly not to be NIRF categories;
  * years: numbers, ranges and phrases ("last 3 years", "since 2020", "2020 se", "'21", "2024-25",
    "recent years", "three years ago") -> the years the category was actually published in; a year with
    no ranking says so instead of returning an empty year.
"""

from __future__ import annotations

import re
from datetime import date
from typing import NamedTuple

from core.data import (LATEST_YEAR, PARAMETERS, PLACE_SYNONYMS, RESEARCH_PARAMETERS, SHORT, YEARS,
                       NirfInputError, NotRankedError, category_years, check_category, check_states, fmt_years,
                       institution_city, institution_keys_named, institution_names, match_institution,
                       region_states, short_label)

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
          "iiitd": "Indraprastha Institute of Information Technology",
          "mahe": "Manipal Academy of Higher Education", "mahe manipal": "Manipal Academy of Higher Education",
          "ism": "Indian Institute of Technology (Indian School of Mines)",
          "ism dhanbad": "Indian Institute of Technology (Indian School of Mines)",
          "iit ism dhanbad": "Indian Institute of Technology (Indian School of Mines)",
          "srmist": "S.R.M. Institute of Science and Technology", "srm ist": "S.R.M. Institute of Science and "
          "Technology", "srm chennai": "S.R.M. Institute of Science and Technology",
          "srm kattankulathur": "S.R.M. Institute of Science and Technology",
          "ju": "Jadavpur University", "cmc ludhiana": "Christian Medical College, Brown Road, Ludhiana",
          "jipmer": "Jawaharlal Institute of Post Graduate Medical Education & Research",
          "jipmer puducherry": "Jawaharlal Institute of Post Graduate Medical Education & Research",
          "pgi": "Post Graduate Institute of Medical Education and Research",
          "pgimer chandigarh": "Post Graduate Institute of Medical Education and Research",
          "sgpgi": "Sanjay Gandhi Postgraduate Institute of Medical Sciences",
          "sgpgims": "Sanjay Gandhi Postgraduate Institute of Medical Sciences",
          "pgi lucknow": "Sanjay Gandhi Postgraduate Institute of Medical Sciences",
          "nlud": "National Law University New Delhi", "nlu new delhi": "National Law University New Delhi",
          "nluj": "National Law University, Jodhpur", "nluo": "National Law University Cuttack",
          "rvce": "R.V. College of Engineering", "rv college": "R.V. College of Engineering",
          "mit manipal": "Manipal Institute of Technology", "lsr": "Lady Shri Ram College For Women",
          "soa": "Siksha O Anusandhan", "soa university": "Siksha O Anusandhan", "soa bhubaneswar": "Siksha O "
          "Anusandhan", "tifr": "Tata Institute of Fundamental Research", "ict": "Institute of Chemical Technology",
          "ict mumbai": "Institute of Chemical Technology", "udct": "Institute of Chemical Technology",
          "tiet": "Thapar Institute of Engineering and Technology",
          "thapar university": "Thapar Institute of Engineering and Technology"}
# Well-known institutions that are not in any NIRF ranking list, 2017-2025: (message, ranked institution to offer).
NOT_IN_NIRF = {
    "isb": ("The Indian School of Business (ISB) does not appear in any NIRF ranking (2017-2025), so there is no "
            "rank or score to chart.", None),
    "bits goa": ("BITS Pilani's Goa campus is not ranked on its own in NIRF: only BITS Pilani (Birla Institute of "
                 "Technology & Science - Pilani) appears in the rankings.", "Birla Institute of Technology and "
                 "Science Pilani"),
    "bits hyderabad": ("BITS Pilani's Hyderabad campus is not ranked on its own in NIRF: only BITS Pilani (Birla "
                       "Institute of Technology & Science - Pilani) appears in the rankings.", "Birla Institute of "
                       "Technology and Science Pilani"),
}
for _k in ("indian school of business", "isb hyderabad", "isb mohali"):
    NOT_IN_NIRF[_k] = NOT_IN_NIRF["isb"]
for _k in ("bits pilani goa", "bits goa campus", "bits pilani goa campus", "bits k k birla goa"):
    NOT_IN_NIRF[_k] = NOT_IN_NIRF["bits goa"]
for _k in ("bits pilani hyderabad", "bits hyderabad campus", "bits pilani hyderabad campus"):
    NOT_IN_NIRF[_k] = NOT_IN_NIRF["bits hyderabad"]


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


def _not_in_nirf(text: str) -> None:
    """Raise a NotRankedError for a well-known institution that NIRF does not rank (ISB, BITS Goa)."""
    t = re.sub(r"[\s.\-()']+", " ", text.strip().lower()).strip()
    if t in NOT_IN_NIRF:
        message, offer = NOT_IN_NIRF[t]
        raise NotRankedError(message, [match_institution(offer).key] if offer else [])


def _shown(key: str) -> str:
    """The institution's name, plus its city when another institution has the same name ('National Law
    University (New Delhi)' vs '(Cuttack)')."""
    name = institution_names([key])[key]
    if len(institution_keys_named(name)) > 1:
        return f"{name} ({institution_city(key)})"
    return name


def resolve_institution(text: str) -> ResolvedInstitution:
    """(institution_key, assumption or None, alternative keys).

    Order: an institution key; the known short forms above (iitb, LPU, IIIT Bangalore ...); then
    core.data.match_institution: exact name, word match, close spelling last, with the family and place
    guards, then the never-ranked participants (NotRankedError) and the family swap ('IIT Bangalore' ->
    IIIT Bangalore, with IISc and IIM Bangalore as alternatives). Raises NirfInputError when nothing fits.
    """
    text = str(text).strip()
    _not_in_nirf(text)
    target, short = _short_form(text)
    m = match_institution(target, typed=text)
    name = _shown(m.key)
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
    region = resolve_region(text)
    if region and t not in STATE_CODES:
        raise NirfInputError(f"'{str(text).strip()}' is a region, not a state: {region[2]}")
    official = STATE_CODES.get(t) or STATE_CODES.get(t.replace(" ", ""))
    try:
        name = check_states([official or text])[0]
    except NirfInputError:
        state = city_state(text)
        if state is None:
            raise
        return state, f"'{str(text).strip()}' = {state} (we filter by state, not city)."
    return name, (None if name.lower() == str(text).strip().lower() else f"I read '{text}' as {name}.")


REGION_WORDS = {
    "north east": "North-East", "northeast": "North-East", "north eastern": "North-East", "ne": "North-East",
    "seven sisters": "North-East", "south": "South", "southern": "South", "south indian": "South",
    "north": "North", "northern": "North", "north indian": "North", "east": "East", "eastern": "East",
    "west": "West", "western": "West", "central": "Central",
}


def resolve_region(text: str) -> tuple[str, list[str], str] | None:
    """('South', its states, a note) for a region typed as a place ('South India', 'north-east states');
    None when the text is not a region. Uses the region column of the cleaned data (data/mappings/state_map.csv)."""
    t = " ".join(re.sub(r"[^a-z ]+", " ", str(text).lower()).split())
    t = re.sub(r"\b(india|indian states|states|state|region|zone|part of india)\b", " ", t)
    t = " ".join(t.replace("north east", "northeast").split()).replace("northeast", "north east")
    region = REGION_WORDS.get(t)
    if region is None:
        return None
    states = region_states(region)
    return region, states, (f"'{str(text).strip()}' = the {region} region in our data ({', '.join(states)}); "
                            f"ranks stay national.")


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
# NIRF's sub-parameters -> the parameter they are part of. NIRF publishes only the parameter scores, so a
# question about patents is answered with RPC, and the answer says so.
SUB_PARAMETERS = {
    "patents": "rpc", "patent": "rpc", "ipr": "rpc", "citations": "rpc", "publication quality": "rpc",
    "research projects": "rpc", "consultancy": "rpc",
    "student strength": "tlr", "students": "tlr", "faculty ratio": "tlr", "faculty student ratio": "tlr",
    "student faculty ratio": "tlr", "teacher ratio": "tlr", "faculty qualification": "tlr",
    "financial resources": "tlr", "phd students": "tlr",
    "median salary": "go", "salary": "go", "salaries": "go", "package": "go", "higher studies": "go",
    "university exams": "go", "phd graduates": "go",
    "women": "oi", "women diversity": "oi", "gender": "oi", "regional diversity": "oi",
    "economically challenged": "oi", "disabled": "oi", "accessibility": "oi",
    "employer perception": "pr", "academic perception": "pr",
}
_SCORE_WORDS = {"score", "scores", "marks", "points", "value", "values", "parameter"}


def resolve_parameter(text: str, category: str | None = None) -> tuple[str, str | None]:
    """(column code such as 'rpc', assumption or None). Raises NirfInputError for an unknown word.

    'research score' = 'research'; a NIRF sub-parameter (patents, median salary) gives its parameter with a
    note; in Research Institutions (no TLR / RPC / GO) research -> QnR and teaching -> SFC, with a note.
    """
    t = re.sub(r"[^a-z ]+", " ", str(text).lower().replace("&", " and "))
    t = " ".join(t.split())
    if len(t.split()) > 1 and t.split()[-1] in _SCORE_WORDS:          # 'research score' -> 'research'
        t = " ".join(t.split()[:-1])
    note = None
    code = t.replace(" ", "") if t.replace(" ", "") in ALL_PARAMETERS else PARAMETER_WORDS.get(t)
    if code is None and t in SUB_PARAMETERS:
        code = SUB_PARAMETERS[t]
        note = (f"NIRF publishes only the 5 parameter scores, not the sub-parameters, so '{text}' is shown "
                f"through {LABELS_PLAIN[code]}, the parameter it is part of.")
    if code is None:
        words = [PARAMETER_WORDS[w] for w in t.split() if w in PARAMETER_WORDS]
        code = words[0] if len(set(words)) == 1 else None
    if code is None:
        raise NirfInputError(f"'{text}' is not a NIRF number. Use the overall score or a parameter: "
                             f"TLR (teaching), RPC (research), GO (graduation outcomes), OI (outreach), "
                             f"PR (perception).")
    if category == "Research Institutions" and code in RESEARCH_SWAPS:
        new, why = RESEARCH_SWAPS[code]
        return new, f"Research Institutions have no {SHORT[code]} score; {why}, so {SHORT[new]} is used."
    plain = t.replace(" ", "")
    return code, note or (None if plain == code else f"I read '{text}' as {SHORT[code]}.")


LABELS_PLAIN = {"tlr": "TLR (Teaching, Learning & Resources)", "rpc": "RPC (Research & Professional Practice)",
                "go": "GO (Graduation Outcomes)", "oi": "OI (Outreach & Inclusivity)", "pr": "PR (Perception)"}
# Research Institutions are scored on QnR, QlR, SFC, OI, PR instead of TLR, RPC, GO.
RESEARCH_SWAPS = {
    "rpc": ("qnr", "NIRF splits research there into QnR (Quantitative Research: publications, citations, "
                   "patents) and QlR (Qualitative Research)"),
    "tlr": ("sfc", "the nearest there is SFC (Student, Faculty & Collaboration)"),
}


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
    "sustainable development goals": "SDG", "sustainability": "SDG", "sustainable": "SDG", "sdgs": "SDG",
    "b tech": "Engineering", "be": "Engineering", "b e": "Engineering", "m tech": "Engineering",
    "pgdm": "Management", "bba": "Management", "b pharm": "Pharmacy", "b pharma": "Pharmacy",
    "dentistry": "Dental", "b arch": "Architecture & Planning", "planning": "Architecture & Planning",
    "agricultural": "Agriculture & Allied Sectors", "arts": "College", "arts and science": "College",
    "science": "College", "commerce": "College", "arts science and commerce": "College", "degree": "College",
    "law universities": "Law", "nlus": "Law",
}
# Words people use for things NIRF does not rank: said plainly instead of "not a category".
NOT_CATEGORIES = {
    "nursing": "Nursing", "nursing colleges": "Nursing", "polytechnic": "Polytechnics",
    "polytechnics": "Polytechnics", "polytechnic colleges": "Polytechnics", "diploma": "Diploma institutes",
    "iti": "ITIs", "schools": "Schools", "hotel management": "Hotel management",
}
_GENERIC = r"\s+(colleges?|institutes?|institutions?|universities|university|schools?|rankings?|list|category)$"


def resolve_category(text: str) -> tuple[str, str | None]:
    """(standard category name, assumption or None).

    The everyday word is looked up first ('MBA colleges' -> Management); otherwise a trailing 'colleges',
    'institutes', 'universities' or 'ranking' is dropped and the rest looked up again ('pharmacy colleges'
    -> Pharmacy). Nursing, polytechnics ... get a plain "NIRF has no ... ranking".
    """
    t = " ".join(re.sub(r"[^a-z& ]+", " ", str(text).lower()).split())
    stripped = re.sub(_GENERIC, "", t)
    for word in (t, stripped):
        if word in NOT_CATEGORIES:
            raise NirfInputError(f"NIRF has no {NOT_CATEGORIES[word]} ranking: {NOT_CATEGORIES[word]} is not one of "
                                 f"its categories in any year from 2017 to 2025. Its categories are: "
                                 f"{', '.join(sorted(category_list()))}.")
    word = CATEGORY_WORDS.get(t) or CATEGORY_WORDS.get(stripped)
    if word is None:
        try:
            name = check_category(text)
        except NirfInputError:
            if stripped == t or not stripped:
                raise
            name = check_category(stripped)
    else:
        name = check_category(word)
    return name, (None if name.lower() == str(text).strip().lower() else f"I read '{text}' as the {name} ranking.")


def category_list() -> list[str]:
    """Every NIRF category in the data."""
    from core.data import load_master            # here, not at the top: resolve is imported before the data exists
    return sorted(load_master()["category_std"].unique())


# ---------- years ----------

_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                 "nine": 9, "ek": 1, "do": 2, "teen": 3, "char": 4, "paanch": 5}


def _no_ranking(years: list[int], category: str | None, available: list[int]) -> str:
    """Why typed years have no ranking: before the data (or the category) starts, or not published yet."""
    what = f"{category} " if category else "NIRF "
    shown = fmt_years(sorted(years))
    if min(years) > available[-1]:
        return (f"There is no {what}ranking for {shown} in the data: the latest {what.strip()} ranking is "
                f"{available[-1]} (NIRF names each ranking by the year it is published).")
    if category and max(years) < available[0] and available[0] > YEARS[0]:
        return (f"{category} starts in {available[0]} ({category} rankings exist for {fmt_years(available)}), "
                f"so there is no {category} ranking for {shown}.")
    return f"There is no {what}ranking for {shown} in the data; {what}rankings exist for {fmt_years(available)}."


def _checked(years: list[int], category: str | None, available: list[int], note: str | None
             ) -> tuple[list[int], str | None]:
    """Keep the typed years that have a ranking (with a note for the others); none -> a clear NirfInputError."""
    inside = [y for y in years if y in available]
    if len(inside) == len(years):
        return years, note
    if not inside:
        raise NirfInputError(_no_ranking(years, category, available))
    left = [y for y in years if y not in available]
    what = f"{category} " if category else ""
    msg = (f"{what}rankings exist only for {fmt_years(available)}, so {fmt_years(left)} "
           f"{'is' if len(left) == 1 else 'are'} left out.")
    return inside, msg[0].upper() + msg[1:]


def resolve_years(value, category: str | None = None, check: bool = True) -> tuple[list[int], str | None]:
    """Years for a number, a list, a range or a phrase, within the years the category was published.

    "latest"/"this year" -> the latest year; "last 3 years" / "recent years" -> the latest 3 published
    years; "since 2020" / "2020 se" -> 2020 to the latest; "2018-2022" or "between 2018 and 2022" -> that
    range; "all years" / "over the years" / "last decade" -> every year; "2020s" -> 2020 onwards;
    "'21" / "2k21" -> 2021; "FY2024" -> 2024; "2024-25" (an academic year) -> NIRF 2025, the year that
    ranking was published; "three years ago" -> the calendar year three years back.
    check=True: a typed year with no ranking (2016, 2026, Dental 2018) is left out with a note, or, when
    no typed year has one, raises a NirfInputError that says why ("Dental starts in 2020 ...").
    check=False returns the typed years as they are (the chat then moves them to the nearest year itself).
    Returns (years, assumption or None).
    """
    available = category_years(category) if category else YEARS
    where = f"{category} " if category else ""
    if isinstance(value, bool) or value is None:
        return available, None
    if isinstance(value, (int, float)):
        years = [int(value)]
        return _checked(years, category, available, None) if check else (years, None)
    if isinstance(value, (list, tuple)):
        out: list[int] = []
        for v in value:
            out += resolve_years(v, category, check=False)[0]
        years = sorted(set(out))
        return _checked(years, category, available, None) if check and years else (years, None)

    text = str(value).strip().lower()
    # "'21", "2k21" -> 2021; "FY2024" / "FY 2024" -> 2024
    text = re.sub(r"(?:(?<=\s)|^)(?:'|’|2k)(\d{2})\b", r"20\1", text)
    text = re.sub(r"\bfy\s*'?(20\d{2})\b", r"\1", text)
    academic = re.fullmatch(r"(?:nirf\s*)?(20[12]\d)\s*[-–/]\s*(\d{2})", text)
    if academic and (int(academic.group(1)) + 1) % 100 == int(academic.group(2)):
        y = int(academic.group(1)) + 1
        note = f"I read '{value}' as NIRF {y}: NIRF names each ranking by the year it is published."
        return _checked([y], category, available, note) if check else ([y], note)
    span = re.fullmatch(r"(20[12]\d)\s*[-–]\s*(\d{2})", text)
    if span:                                                    # '2018-22' -> 2018 to 2022
        text = f"{span.group(1)}-20{span.group(2)}"
    numbers = [int(n) for n in re.findall(r"\b(20[12]\d)\b", text)]
    count = re.search(r"\b(\d+|" + "|".join(_NUMBER_WORDS) + r")\s*(?:years?|yrs?|saal|sal)\b", text)
    ago = re.search(r"\b(\d+|" + "|".join(_NUMBER_WORDS) + r"|a)\s*(?:years?|saal|sal)\s*(?:ago|back|pehle)\b", text)
    if re.fullmatch(r"20[12]\d", text):
        years = [int(text)]
        note = None if str(value).strip() == text else f"I read '{value}' as {text}."      # "'21", "FY2024"
        return _checked(years, category, available, note) if check else (years, note)
    if ago and not numbers:
        n = 1 if ago.group(1) == "a" else int(ago.group(1)) if ago.group(1).isdigit() else _NUMBER_WORDS[ago.group(1)]
        y = date.today().year - n
        note = f"I read '{value}' as {y} ({n} year{'s' if n > 1 else ''} before {date.today().year})."
        return _checked([y], category, available, note) if check else ([y], note)
    decade = re.fullmatch(r"(?:the\s+)?(20[12])0s", text)
    if decade:
        lo = int(decade.group(1)) * 10
        years = [y for y in available if lo <= y < lo + 10]
        if not years:
            raise NirfInputError(_no_ranking([lo], category, available))
        return years, f"I read '{value}' as {fmt_years(years)}, the {where}years of the {lo}s in the data."
    if (re.search(r"\b(all|every|whole|entire)\b", text) or re.search(r"\bover the years\b|\bdecade\b|\bover time\b"
                                                                       r"|\bthroughout\b|\bever\b", text)) and not numbers:
        return available, f"I read '{value}' as every {where}year ({fmt_years(available)})."
    if re.search(r"\brecent years\b|\blast few years\b|\bpast few years\b", text) and not count and not numbers:
        years = available[-3:]
        return years, f"I read '{value}' as the latest {len(years)} {where}years in the data ({fmt_years(years)})."
    if count and not numbers and any(w in text for w in ("last", "past", "recent", "pichhle", "pichle", "latest")):
        n = int(count.group(1)) if count.group(1).isdigit() else _NUMBER_WORDS[count.group(1)]
        years = available[-n:]
        return years, f"I read '{value}' as the latest {len(years)} {where}years in the data ({fmt_years(years)})."
    if numbers and len(numbers) == 1 and (any(w in text for w in ("since", "from", "after", "onwards", "onward"))
                                          or re.search(r"\b(se|tak se|ke baad)\b", text)):
        years = [y for y in available if y >= numbers[0]]
        return years, f"I read '{value}' as {fmt_years(years)}."
    if numbers and any(w in text for w in ("before", "until", "till", "up to", "upto")) and len(numbers) == 1:
        years = [y for y in available if y <= numbers[0]]
        return years, f"I read '{value}' as {fmt_years(years)}."
    if len(numbers) == 2:
        lo, hi = sorted(numbers)
        years = [y for y in available if lo <= y <= hi]
        if not years and check:
            raise NirfInputError(_no_ranking(list(range(lo, hi + 1)), category, available))
        return years, None
    if numbers:
        years = sorted(set(numbers))
        note = None if re.fullmatch(r"[\d\s,and]+", str(value).strip().lower()) else \
            f"I read '{value}' as {fmt_years(years)}."
        return _checked(years, category, available, note) if check else (years, note)
    if any(w in text for w in ("latest", "this year", "current", "recent", "now", "newest", "last year")):
        latest = available[-1] if available else LATEST_YEAR
        return [latest], f"I read '{value}' as {latest}, the latest {where}ranking in the data."
    if any(w in text for w in ("first", "earliest", "oldest")):
        return [available[0]], f"I read '{value}' as {available[0]}, the first {where}ranking in the data."
    raise NirfInputError(f"'{value}' is not a year or a time period I can read. "
                         f"{where or 'NIRF '}rankings exist for {fmt_years(available)}.")
