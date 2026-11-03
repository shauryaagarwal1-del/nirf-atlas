"""Institution identity: give one real institution one stable key across all years and categories.

NIRF spells the same institution in many ways ("IIT Kharagpur" with and without a comma, "&" vs "and",
UPPER CASE on one page, a city added in 2017, a full rename like "University of Petroleum and Energy
Studies" -> "UPES"). Charts that follow an institution over time need one key per real institution.

How a key is built (each rule is something we can explain in the viva):

  0. Cleaned name. Every name gets a matching key: lower case, '&' -> 'and', punctuation removed,
     "Govt" -> "government", spaced initials joined ("S. R. M." -> "srm"), legal-form words such as
     "(Autonomous)" or "Deemed to be University" dropped. Same cleaned name + same state = same node.
     When one cleaned name + state stands for two different colleges (two "Government Arts College"
     in one Tamil Nadu list), the city is added to tell them apart.
  1. NIRF ID code. From 2018 every ranked row carries an ID such as IR-O-U-0456; its last part
     (U-0456) stays the same for one institution, even across renames. Rows with the same code are
     linked, except for "parent" codes that cover several different units in the same year (Amrita).
  2. Human decisions read back from data/mappings/institution_review.csv (approve = yes / no).
  3. Alias rules: hand-made links in data/mappings/institution_alias_rules.csv, plus one general rule:
     a name that is another name + its own city or state ("Indian Institute of Science Bangalore" in
     Bengaluru = "Indian Institute of Science") is linked when only one institution could be meant.
  4. Fuzzy match: rapidfuzz token_sort_ratio >= 92 between two names in the same state is linked
     automatically, unless something speaks against it (each name has its own different word, e.g.
     Amravati vs Aurangabad; different cities; different ID codes). Those cases and all pairs with
     similarity 80-92 go to the review file for a human.

Hard rule for every link: two rows from the same ranking list (same year and category) are never
merged, because one list never contains the same institution twice.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz
from rapidfuzz.process import cdist

from pipeline.audit import fmt_years

AUTO_THRESHOLD = 92      # token_sort_ratio at or above which a pair can be linked automatically
REVIEW_THRESHOLD = 80    # pairs from here up to AUTO_THRESHOLD go to a human
CITY_SAME = 85           # two city spellings at or above this similarity are the same place
CITY_CLASH = 70          # cities below this similarity block an automatic link
WORD_CLASH = 75          # words unique to each name below this similarity = a different distinguishing word
SHARED_CODE = 80         # two names under one ID code in one year below this similarity = parent code
SUBSET_MIN_SCORE = 70    # 'one name = the other + 1-2 words' pairs are reviewed from this similarity up

KEY_PREFIX = "INST-"

# Old or English city names, used only to compare cities (never shown).
CITY_SYNONYMS = {
    "bangalore": "bengaluru", "bombay": "mumbai", "madras": "chennai", "calcutta": "kolkata",
    "gurgaon": "gurugram", "mysore": "mysuru", "mangalore": "mangaluru", "belgaum": "belagavi",
    "trichy": "tiruchirappalli", "tiruchirapalli": "tiruchirappalli", "trichirapalli": "tiruchirappalli",
    "trivandrum": "thiruvananthapuram", "calicut": "kozhikode", "trichur": "thrissur", "poona": "pune",
    "ooty": "udhagamandalam", "ootacamund": "udhagamandalam", "allahabad": "prayagraj",
    "cochin": "kochi", "baroda": "vadodara", "pondicherry": "puducherry", "vizag": "visakhapatnam",
    "visakapatnam": "visakhapatnam", "benaras": "varanasi", "banaras": "varanasi", "kanchipuram":
    "kancheepuram", "gulbarga": "kalaburagi", "hubli": "hubballi", "shimoga": "shivamogga",
}
CITY_NOISE = {"district", "dist", "taluka", "taluk", "tal", "ta", "pin", "sector", "po", "via"}

# Short forms and spelling variants of one word, used only inside the matching key.
NAME_ABBREVIATIONS = {"govt": "government", "univ": "university", "engg": "engineering",
                      "mgmt": "management", "inst": "institute", "coll": "college", "pt": "pandit",
                      "prin": "principal", "eve": "evening", "st": "saint", "shri": "sri", "shree": "sri",
                      "sree": "sri"}
NAME_DROP_PHRASES = ["deemed to be university", "deemed university", "autonomous"]


# --------------------------------------------------------------------------------------------
# Matching keys
# --------------------------------------------------------------------------------------------

def name_key(name: str) -> str:
    """Matching key for an institution name (used only for matching, never displayed).

    'S.R.M. Institute of Science & Technology' and 'SRM Institute of Science and Technology'
    both become 'srm institute of science and technology'; old city names are replaced by the
    current ones ('... Science Bangalore' -> '... science bengaluru').
    """
    s = name.lower()
    s = re.sub(r"[`'’?�]s\b", "s", s)          # possessive: xavier's / xavier`s -> xaviers
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    tokens = [CITY_SYNONYMS.get(t, NAME_ABBREVIATIONS.get(t, t)) for t in s.split()]
    joined, run = [], []                                   # join spaced initials: s r m -> srm
    for t in tokens + [""]:
        if len(t) == 1 and t.isalpha():
            run.append(t)
            continue
        if run:
            joined.append("".join(run))
            run = []
        if t:
            joined.append(t)
    s = " ".join(joined)
    for phrase in NAME_DROP_PHRASES:
        s = re.sub(rf"\b{phrase}\b", " ", s)
    s = re.sub(r"^the\s+", "", s.strip())
    return re.sub(r"\s+", " ", s).strip()


def city_key(city: str) -> str:
    """Matching key for a city: lower case, PIN codes and words like 'District' removed, old names
    replaced by current ones ('Dist. Calicut' -> 'kozhikode')."""
    s = re.sub(r"[^a-z ]+", " ", city.lower())
    tokens = [CITY_SYNONYMS.get(t, t) for t in s.split() if t not in CITY_NOISE]
    return " ".join(tokens)


def id_code(institute_id: str) -> str:
    """The stable part of a NIRF Institute ID.

    2018-2025: 'IR-2-O-OE-U-0456', 'IR-O-U-0456', 'ARI-U-0456' all -> 'U-0456' (IIT Madras).
    2017 IDs ('IR17-...') follow a different scheme that never reappears, so the whole ID is kept
    with a '2017:' prefix: it links the 2017 categories to each other, not to later years.
    """
    if not institute_id:
        return ""
    if institute_id.startswith("IR17"):
        return "2017:" + institute_id
    parts = institute_id.split("-")
    return "-".join(parts[-2:]) if len(parts) >= 3 else ""


def _sim(a: str, b: str) -> float:
    return fuzz.token_sort_ratio(a, b)


def _word_clash(a: str, b: str) -> str:
    """'' if the names differ only by a spelling slip or by words added on one side; otherwise the
    two clashing word groups (e.g. 'amravati' vs 'aurangabad')."""
    ta, tb = set(a.split()), set(b.split())
    only_a, only_b = " ".join(sorted(ta - tb)), " ".join(sorted(tb - ta))
    if only_a and only_b and fuzz.ratio(only_a, only_b) < WORD_CLASH:
        return f"'{only_a}' vs '{only_b}'"
    return ""


def _city_sim(ca: set[str], cb: set[str]) -> float:
    """Best similarity between any city of A and any city of B (100 if either is unknown)."""
    ca, cb = {c for c in ca if c}, {c for c in cb if c}
    if not ca or not cb:
        return 100.0
    return max(fuzz.token_set_ratio(x, y) for x in ca for y in cb)


# --------------------------------------------------------------------------------------------
# Nodes (cleaned name + state [+ city]) and clusters (one real institution)
# --------------------------------------------------------------------------------------------

@dataclass
class Node:
    node_id: str
    name_key: str
    state: str
    city_rep: str
    occ: set = field(default_factory=set)            # (year, category) lists this node appears in
    codes: set = field(default_factory=set)          # 2018+ ID codes
    cities: set = field(default_factory=set)         # city keys
    years: set = field(default_factory=set)
    categories: set = field(default_factory=set)
    names: Counter = field(default_factory=Counter)  # display names


class Clusters:
    """Union-find over nodes that refuses any merge that would put two rows of one list together."""

    def __init__(self, nodes: dict[str, Node], forbidden: set[frozenset]):
        self.nodes = nodes
        self.parent = {n: n for n in nodes}
        self.members = {n: {n} for n in nodes}
        self.occ = {n: set(v.occ) for n, v in nodes.items()}
        self.codes = {n: set(v.codes) for n, v in nodes.items()}
        self.forbidden = defaultdict(set)
        for pair in forbidden:
            a, b = tuple(pair)
            self.forbidden[a].add(b)
            self.forbidden[b].add(a)
        self.edges: list[tuple[str, str, str, float]] = []
        self.skipped: list[dict] = []

    def find(self, x: str) -> str:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def conflict(self, a: str, b: str) -> str:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return "already linked"
        both = self.occ[ra] & self.occ[rb]
        if both:
            y, c = sorted(both)[0]
            return f"both appear in the {y} {c} list"
        for m in self.members[ra]:
            if any(self.find(f) == rb for f in self.forbidden.get(m, ())):
                return "rejected by a human in the review file"
        return ""

    def union(self, a: str, b: str, method: str, score: float) -> bool:
        why = self.conflict(a, b)
        if why:
            if why != "already linked":
                self.skipped.append({"node_a": a, "node_b": b, "method": method,
                                     "score": round(score), "reason": why})
            return False
        ra, rb = self.find(a), self.find(b)
        if len(self.members[ra]) < len(self.members[rb]):
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.members[ra] |= self.members.pop(rb)
        self.occ[ra] |= self.occ.pop(rb)
        self.codes[ra] |= self.codes.pop(rb)
        self.edges.append((a, b, method, score))
        return True

    def roots(self) -> list[str]:
        return [n for n in self.nodes if self.find(n) == n]


# --------------------------------------------------------------------------------------------
# Building nodes
# --------------------------------------------------------------------------------------------

def _cluster_cities(city_counts: Counter) -> dict[str, str]:
    """Group spellings of one city ('tiruchirapalli' / 'tiruchirappalli'): city key -> representative."""
    reps: list[str] = []
    out = {}
    for c, _ in city_counts.most_common():
        rep = next((r for r in reps if c and r and fuzz.token_set_ratio(c, r) >= CITY_SAME), None)
        if rep is None:
            reps.append(c)
            rep = c
        out[c] = rep
    return out


def assign_nodes(df: pd.DataFrame) -> tuple[pd.Series, set, dict]:
    """Node id for every row. Expects columns name_key, state, city_key, year, category_std, code.

    A (cleaned name, state) is 'ambiguous' (two different institutions) when it occurs twice in one
    list, or when it carries 2+ ID codes in clearly different cities. Only then is the city added.
    """
    base = df["name_key"] + " | " + df["state"]
    twice_in_list = df.groupby(["year", "category_std", "name_key", "state"]).size()
    ambiguous = {f"{n} | {s}" for (_, _, n, s), k in twice_in_list.items() if k > 1}

    coded = df[df["code"].ne("") & ~df["code"].str.startswith("2017:")]
    for b, g in coded.groupby(base[coded.index]):
        cities_by_code = g.groupby("code")["city_key"].agg(set)
        if len(cities_by_code) < 2:
            continue
        sets = list(cities_by_code)
        if any(_city_sim(x, y) < CITY_SAME for i, x in enumerate(sets) for y in sets[i + 1:]):
            ambiguous.add(b)

    city_reps = {}
    for b in ambiguous:
        city_reps[b] = _cluster_cities(Counter(df.loc[base == b, "city_key"]))
    node = base.copy()
    mask = base.isin(ambiguous)
    node[mask] = [f"{b} | {city_reps[b][c]}" for b, c in zip(base[mask], df.loc[mask, "city_key"])]
    return node, ambiguous, city_reps


def build_nodes(df: pd.DataFrame) -> dict[str, Node]:
    nodes: dict[str, Node] = {}
    for r in df.itertuples(index=False):
        n = nodes.get(r.node)
        if n is None:
            parts = r.node.split(" | ")
            n = nodes[r.node] = Node(r.node, parts[0], parts[1], parts[2] if len(parts) > 2 else "")
        n.occ.add((r.year, r.category_std))
        if r.code and not r.code.startswith("2017:"):
            n.codes.add(r.code)
        n.cities.add(r.city_key)
        n.years.add(r.year)
        n.categories.add(r.category_std)
        n.names[r.institute_name] += 1
    return nodes


# --------------------------------------------------------------------------------------------
# Link rules
# --------------------------------------------------------------------------------------------

def link_by_id_code(df: pd.DataFrame, cl: Clusters) -> list[str]:
    """Rule 1. Returns the codes treated as parent codes (not used for linking)."""
    parent_codes = []
    coded = df[df["code"].ne("")]
    for code, g in coded.groupby("code"):
        nodes = list(dict.fromkeys(g.sort_values("year")["node"]))
        if len(nodes) < 2:
            continue
        shared = False
        for _, gy in g.groupby("year"):
            keys = list(dict.fromkeys(gy["name_key"]))
            if any(_sim(a, b) < SHARED_CODE for i, a in enumerate(keys) for b in keys[i + 1:]):
                shared = True
                break
        if shared:
            parent_codes.append(code)
            continue
        for n in nodes[1:]:
            cl.union(nodes[0], n, "id_code", _sim(cl.nodes[nodes[0]].name_key, cl.nodes[n].name_key))
    return parent_codes


def link_by_hand_rules(rules: pd.DataFrame, cl: Clusters) -> list[str]:
    """Rule 3a: hand-made alias rules. Each rule names two institutions (name + state, optional city)."""
    problems = []
    by_key = defaultdict(list)
    for nid, n in cl.nodes.items():
        by_key[(n.name_key, n.state)].append(nid)

    def lookup(name: str, state: str, city: str) -> list[str]:
        found = by_key.get((name_key(name), state), [])
        if city and len(found) > 1:
            found = [f for f in found if fuzz.token_set_ratio(cl.nodes[f].city_rep, city_key(city)) >= CITY_SAME]
        return found

    for r in rules.itertuples(index=False):
        a = lookup(r.name, r.state, r.city)
        b = lookup(r.same_as_name, r.same_as_state, r.same_as_city)
        if len(a) != 1 or len(b) != 1:
            problems.append(f"rule '{r.name}' = '{r.same_as_name}': found {len(a)} and {len(b)} matches")
            continue
        cl.union(a[0], b[0], "alias_rule", 100.0)
    return problems


def link_by_city_word(cl: Clusters, state_keys: dict[str, str]) -> list[dict]:
    """Rule 3b: 'X <own city and/or state>' = 'X' in the same state and city.

    Among the institutions called exactly 'X' in that state, the one in the same city is chosen.
    When there is only one 'X' but its city looks different, the pair goes to the review file.
    """
    by_key = defaultdict(list)
    for nid, n in cl.nodes.items():
        by_key[(n.name_key, n.state)].append(nid)
    review = []
    for nid, n in cl.nodes.items():
        tokens = n.name_key.split()
        places = {c for c in n.cities if c} | {state_keys.get(n.state, "")}
        cut = len(tokens)
        while True:                       # strip trailing place words: '..., Karad, Maharashtra'
            k = next((k for k in (2, 1) if cut - k >= 2 and " ".join(tokens[cut - k:cut]) in places), 0)
            if not k:
                break
            cut -= k
        if cut == len(tokens):
            continue
        stripped = " ".join(tokens[:cut])
        targets = by_key.get((stripped, n.state), [])
        same_city = [b for b in targets if _city_sim(n.cities, cl.nodes[b].cities) >= CITY_SAME]
        if len(same_city) == 1:
            cl.union(nid, same_city[0], "alias_rule", 100.0)
        elif len(targets) == 1 and not same_city:
            review.append({"node_a": nid, "node_b": targets[0], "score": 100.0,
                           "reason": "one name = the other + a place name, but the cities differ"})
    return review


def fuzzy_candidates(cl: Clusters) -> list[dict]:
    """Rule 4: pairs of nodes in one state that may be the same institution.

    (a) token_sort_ratio >= REVIEW_THRESHOLD, or
    (b) all words of one name appear in the other, which only adds 1-2 words
        ('Siksha O Anusandhan' / 'Siksha O Anusandhan University') and the cities agree;
        token_sort_ratio punishes added words, so these would otherwise be missed. They are never
        linked automatically.
    Nodes with the same cleaned name were split by city on purpose (two different colleges), so
    they are not compared again."""
    by_state = defaultdict(list)
    for nid, n in cl.nodes.items():
        by_state[n.state].append(nid)
    out = []
    for state, ids in by_state.items():
        if len(ids) < 2:
            continue
        keys = [cl.nodes[i].name_key for i in ids]
        sort = cdist(keys, keys, scorer=fuzz.token_sort_ratio)
        subset = cdist(keys, keys, scorer=fuzz.token_set_ratio, score_cutoff=100)
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                if keys[i] == keys[j]:
                    continue
                if sort[i, j] >= REVIEW_THRESHOLD:
                    out.append({"node_a": ids[i], "node_b": ids[j], "score": float(sort[i, j])})
                elif subset[i, j] == 100 and SUBSET_MIN_SCORE <= sort[i, j] and                         abs(len(keys[i].split()) - len(keys[j].split())) <= 2 and                         _city_sim(cl.nodes[ids[i]].cities, cl.nodes[ids[j]].cities) >= CITY_CLASH:
                    out.append({"node_a": ids[i], "node_b": ids[j], "score": float(sort[i, j]),
                                "subset": True})
    out.sort(key=lambda c: -c["score"])
    return out


def blockers(cl: Clusters, a: str, b: str, score: float) -> list[str]:
    """Reasons why a fuzzy pair must not be linked automatically ([] = safe to link)."""
    na, nb = cl.nodes[a], cl.nodes[b]
    reasons = []
    if score < AUTO_THRESHOLD:
        reasons.append(f"similarity {score:.0f} is below {AUTO_THRESHOLD}")
    clash = _word_clash(na.name_key, nb.name_key)
    if clash:
        reasons.append(f"each name has its own different word: {clash}")
    ca, cb = cl.codes[cl.find(a)], cl.codes[cl.find(b)]
    if ca and cb and not (ca & cb):
        reasons.append(f"different NIRF ID codes: {', '.join(sorted(ca))} vs {', '.join(sorted(cb))}")
    if _city_sim(na.cities, nb.cities) < CITY_CLASH:
        reasons.append("different cities: " + " / ".join(sorted(c for c in na.cities if c)) + " vs "
                       + " / ".join(sorted(c for c in nb.cities if c)))
    return reasons


# --------------------------------------------------------------------------------------------
# Review file (humans decide) and key assignment
# --------------------------------------------------------------------------------------------

REVIEW_COLUMNS = ["approve", "score", "reason", "name_a", "state_a", "city_a", "years_a", "categories_a",
                  "name_b", "state_b", "city_b", "years_b", "categories_b", "node_a", "node_b"]


def read_decisions(path: Path) -> tuple[pd.DataFrame, dict[frozenset, str]]:
    """Rows of the existing review file and the decisions in it ({node_a, node_b} -> 'yes'/'no')."""
    if not path.exists():
        return pd.DataFrame(columns=REVIEW_COLUMNS), {}
    old = pd.read_csv(path, dtype=str, keep_default_na=False)
    decisions = {}
    for r in old.itertuples(index=False):
        v = str(r.approve).strip().lower()
        v = {"y": "yes", "n": "no"}.get(v, v)
        if v in ("yes", "no"):
            decisions[frozenset((r.node_a, r.node_b))] = v
    return old, decisions


def _display(n: Node) -> str:
    return n.names.most_common(1)[0][0]


def review_rows(cl: Clusters, candidates: list[dict], decisions: dict[frozenset, str]
                ) -> tuple[pd.DataFrame, list[frozenset]]:
    """One row per pair a human should look at; earlier decisions are carried over.

    Returns the rows and the decided pairs that are no longer among the candidates."""
    rows, seen = [], set()
    for c in candidates:
        a, b = c["node_a"], c["node_b"]
        pair = frozenset((a, b))
        decided = decisions.get(pair, "")
        if not decided:
            ra, rb = cl.find(a), cl.find(b)
            cluster_pair = frozenset((ra, rb))
            if ra == rb or cluster_pair in seen or cl.conflict(a, b):
                continue
            seen.add(cluster_pair)
        na, nb = cl.nodes[a], cl.nodes[b]
        rows.append({
            "approve": decided, "score": round(c["score"]), "reason": c["reason"],
            "name_a": _display(na), "state_a": na.state,
            "city_a": " / ".join(sorted(x for x in na.cities if x)),
            "years_a": fmt_years(na.years), "categories_a": ", ".join(sorted(na.categories)),
            "name_b": _display(nb), "state_b": nb.state,
            "city_b": " / ".join(sorted(x for x in nb.cities if x)),
            "years_b": fmt_years(nb.years), "categories_b": ", ".join(sorted(nb.categories)),
            "node_a": a, "node_b": b,
        })
    # decisions whose nodes no longer exist (data changed) are kept so no human work is lost
    present = {frozenset((r["node_a"], r["node_b"])) for r in rows}
    out = pd.DataFrame(rows, columns=REVIEW_COLUMNS)
    return out, [p for p in decisions if p not in present]


def assign_keys(cl: Clusters, df: pd.DataFrame, previous: pd.DataFrame) -> tuple[dict[str, str], dict[str, str]]:
    """institution_key and canonical_name for every node.

    canonical_name = the name used in the most recent year (most frequent spelling that year).
    Keys are reused from the previous alias table where possible, so a key does not change between
    runs; new institutions get the next free number.
    """
    old_key = {}
    if previous is not None and not previous.empty:
        for r in previous.itertuples(index=False):
            old_key[(r.raw_name, r.state, r.city)] = r.institution_key
    root = df["node"].map(cl.find)
    raw_by_node = (pd.Series(list(zip(df["institute_name_raw"], df["state"], df["alias_city"])), index=df.index)
                   .groupby(df["node"]).agg(list))
    clusters = defaultdict(list)
    for n in cl.nodes:
        clusters[cl.find(n)].append(n)

    latest = df[df["year"].eq(df.groupby(root)["year"].transform("max"))]
    canonical = (latest.groupby([root[latest.index], "institute_name"]).size()
                 .reset_index(name="n").sort_values(["n", "institute_name"], ascending=[False, True])
                 .drop_duplicates("node").set_index("node")["institute_name"].to_dict())

    order = sorted(clusters, key=lambda r: (min(min(cl.nodes[m].years) for m in clusters[r]), canonical[r]))
    used, root_key = set(), {}
    for root in order:
        votes = Counter(old_key[k] for m in clusters[root] for k in raw_by_node[m] if k in old_key)
        for k, _ in votes.most_common():
            if k not in used:
                root_key[root] = k
                used.add(k)
                break
    next_no = max([int(k[len(KEY_PREFIX):]) for k in used if k.startswith(KEY_PREFIX)] + [0]) + 1
    for root in order:
        if root not in root_key:
            root_key[root] = f"{KEY_PREFIX}{next_no:05d}"
            next_no += 1

    node_key = {n: root_key[cl.find(n)] for n in cl.nodes}
    node_canonical = {n: canonical[cl.find(n)] for n in cl.nodes}
    return node_key, node_canonical


def attach_methods(cl: Clusters, canonical_node: dict[str, str]) -> dict[str, str]:
    """How each node joined its cluster: walk the links outward from the node that holds the
    canonical name; each node gets the rule of the link it was reached by."""
    adj = defaultdict(list)
    for a, b, method, _ in cl.edges:
        adj[a].append((b, method))
        adj[b].append((a, method))
    method = {}
    for root, start in canonical_node.items():
        method[start] = "exact"
        q = deque([start])
        while q:
            x = q.popleft()
            for y, m in adj[x]:
                if y not in method:
                    method[y] = m
                    q.append(y)
    return method


# --------------------------------------------------------------------------------------------
# Whole identity step
# --------------------------------------------------------------------------------------------

ALIAS_COLUMNS = ["raw_name", "state", "city", "institution_key", "canonical_name", "match_method",
                 "match_score"]
RULE_COLUMNS = ["name", "state", "city", "same_as_name", "same_as_state", "same_as_city", "note"]


@dataclass
class IdentityResult:
    df: pd.DataFrame                 # input rows + institution_key, canonical_name, node
    aliases: pd.DataFrame
    review: pd.DataFrame
    stats: dict
    links: pd.DataFrame              # every link made: node_a, node_b, method, score
    skipped: pd.DataFrame            # links refused because of a conflict
    lookup: dict                     # what participant rows need to find their key


def identify(df: pd.DataFrame, rules_path: Path, review_path: Path, aliases_path: Path,
             state_keys: dict[str, str]) -> IdentityResult:
    """Run rules 0-4 on the ranked rows. Expects institute_name, institute_name_raw, institute_id,
    city, state, year, category_std."""
    df = df.copy()
    df["name_key"] = df["institute_name"].map(name_key)
    df["city_key"] = df["city"].map(city_key)
    df["code"] = df["institute_id"].map(id_code)
    df["node"], ambiguous, city_reps = assign_nodes(df)
    base = df["name_key"] + " | " + df["state"]
    df["alias_city"] = df["city"].where(base.isin(ambiguous), "")
    nodes = build_nodes(df)

    old_review, decisions = read_decisions(review_path)
    forbidden = {p for p, v in decisions.items() if v == "no" and all(x in nodes for x in p)}
    cl = Clusters(nodes, forbidden)

    parent_codes = link_by_id_code(df, cl)
    n_after = {"id_code": len(cl.edges)}
    for pair, v in decisions.items():
        if v == "yes" and all(x in nodes for x in pair):
            a, b = sorted(pair)
            cl.union(a, b, "review_approved", _sim(nodes[a].name_key, nodes[b].name_key))
    rules = (pd.read_csv(rules_path, dtype=str, keep_default_na=False)
             if rules_path.exists() else pd.DataFrame(columns=RULE_COLUMNS))
    rule_problems = link_by_hand_rules(rules, cl)
    review_cands = link_by_city_word(cl, state_keys)

    decided_cands = []
    for c in fuzzy_candidates(cl):
        a, b = c["node_a"], c["node_b"]
        if frozenset((a, b)) in decisions:
            c["reason"] = "decided by a human"
            decided_cands.append(c)
            continue
        if cl.find(a) == cl.find(b):
            continue
        reasons = blockers(cl, a, b, c["score"])
        if c.get("subset"):
            reasons[0] = "one name = the other + 1-2 extra words"
        if reasons:
            c["reason"] = "; ".join(reasons)
            review_cands.append(c)
        else:
            cl.union(a, b, "fuzzy", c["score"])

    review, missing_pairs = review_rows(cl, decided_cands + review_cands, decisions)
    if missing_pairs and not old_review.empty:
        keep = old_review[[frozenset((a, b)) in set(missing_pairs)
                           for a, b in zip(old_review["node_a"], old_review["node_b"])]]
        review = pd.concat([review, keep[REVIEW_COLUMNS]], ignore_index=True)
    # undecided pairs first; among them the likeliest matches (fewest reasons against) first
    review = (review.assign(_decided=review["approve"].ne(""), _against=review["reason"].str.count(";"),
                            _score=pd.to_numeric(review["score"]))
              .sort_values(["_decided", "_against", "_score"], ascending=[True, True, False])
              .drop(columns=["_decided", "_against", "_score"]).reset_index(drop=True))

    previous = pd.read_csv(aliases_path, dtype=str, keep_default_na=False) if aliases_path.exists() else None
    node_key, node_canonical = assign_keys(cl, df, previous)
    df["institution_key"] = df["node"].map(node_key)
    df["canonical_name"] = df["node"].map(node_canonical)

    hit = df[df["institute_name"].eq(df["canonical_name"])].sort_values("year")
    canonical_node = hit.groupby(hit["node"].map(cl.find))["node"].last().to_dict()
    method = attach_methods(cl, canonical_node)

    a = df.drop_duplicates(["institute_name_raw", "state", "alias_city"])
    aliases = pd.DataFrame({
        "raw_name": a["institute_name_raw"], "state": a["state"], "city": a["alias_city"],
        "institution_key": a["institution_key"], "canonical_name": a["canonical_name"],
        "match_method": a["node"].map(method),
        "match_score": [round(_sim(name_key(r), name_key(c))) for r, c in
                        zip(a["institute_name_raw"], a["canonical_name"])],
    }).sort_values(["canonical_name", "state", "raw_name"]).reset_index(drop=True)

    links = pd.DataFrame(cl.edges, columns=["node_a", "node_b", "method", "score"])
    stats = {
        "rows": len(df), "raw_names": df["institute_name_raw"].nunique(),
        "nodes": len(nodes), "ambiguous_names": len(ambiguous),
        "institutions": df["institution_key"].nunique(), "parent_codes": parent_codes,
        "links_by_method": links["method"].value_counts().to_dict(),
        "rule_problems": rule_problems, "n_rules": len(rules),
        "decisions_yes": sum(v == "yes" for v in decisions.values()),
        "decisions_no": sum(v == "no" for v in decisions.values()),
        "review_waiting": int(review["approve"].eq("").sum()),
        "n_id_links": n_after["id_code"],
    }
    lookup = {"ambiguous": ambiguous, "city_reps": city_reps, "node_key": node_key,
              "node_canonical": node_canonical}
    return IdentityResult(df, aliases, review, stats, links, pd.DataFrame(cl.skipped), lookup)


def lookup_keys(side: pd.DataFrame, lookup: dict) -> tuple[pd.Series, pd.Series]:
    """institution_key / canonical_name for rows outside the ranked lists (participant lists), by
    exact cleaned name + state (+ city where the name is ambiguous). No fuzzy guessing here."""
    nk = side["institute_name"].map(name_key)
    base = nk + " | " + side["state"]
    node = base.copy()
    amb = base.isin(lookup["ambiguous"])
    for i in side.index[amb]:
        ck = city_key(side.at[i, "city"])
        reps = set(lookup["city_reps"][base[i]].values())
        rep = next((r for r in reps if ck and r and fuzz.token_set_ratio(ck, r) >= CITY_SAME), None)
        node[i] = f"{base[i]} | {rep}" if rep is not None else ""
    return node.map(lookup["node_key"]).fillna(""), node.map(lookup["node_canonical"]).fillna("")
