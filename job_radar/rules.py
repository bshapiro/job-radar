"""Turn profile/rules.yaml into the matcher that decides which job titles are worth a look.

Every list in rules.yaml holds words or phrases. Each matches as whole words, ignoring case:
  - "product manager"           the phrase itself
  - "scien*" / "*health*"       a * stands for any letters: scientist, science...; telehealth, healthcare...
  - {word: manager, not_after: [product, program]}   "manager", but not "product manager"
  - {word: chief, not_before: [of staff]}            "chief", but not "chief of staff"
  - {then: [[director, head], [product]]}            a word from the first list, later one from the second
  - "/regular expression/"      an escape hatch for anything else (rarely needed)

A title is scored like this (see templates/profile/rules.yaml for every setting):
  1. It must mention the field (`title.topic`), or be a role that counts on its own (`title.also_relevant`),
     or be a senior role at an investor or funder (`investors`). Otherwise it is ignored entirely.
  2. The first `exclude` rule it matches rejects it, unless the title also matches that rule's `unless`.
  3. Each listed location is scored (`location`); the best counts. None in reach rejects it.
  4. Points: title boosts + location + employer bonus (+ the investor bonus). Below `min_score` rejects it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Whole-word edges. Unlike \b these also work next to punctuation, so "a.i." and "r&d" match as written.
B, E = r"(?<!\w)", r"(?!\w)"
UNKNOWN_LOCATION = re.compile(r"^\d+ locations$|^$")   # Workday hides multi-site locations; scrape looks them up


def _word(s: str) -> str:
    """One plain entry as a regex body (no surrounding boundaries): escape it, and turn * into letters."""
    return re.escape(s.lower()).replace(r"\*", r"\w*")


def _entry(e) -> tuple[str, bool]:
    """(regex, needs word boundaries) for one list entry."""
    if isinstance(e, str):
        if len(e) > 2 and e.startswith("/") and e.endswith("/"):
            return e[1:-1], False
        return _word(e), True
    if isinstance(e, dict) and "word" in e:
        core = _word(e["word"])
        before = "".join(f"(?<!{_word(w)} )" for w in e.get("not_after", []))
        after = "".join(f"(?! {_word(w)})" for w in e.get("not_before", []))
        return before + core + after, True
    if isinstance(e, dict) and "then" in e:
        parts = [B + "(?:" + "|".join(_entry(x)[0] for x in group) + ")" + E for group in e["then"]]
        return ".*".join(parts), False
    raise ValueError(f"rules.yaml: can't read entry {e!r}")


def pattern(entries) -> re.Pattern | None:
    """One compiled pattern matching any of `entries`, or None for an empty list."""
    if not entries:
        return None
    words, raw = [], []
    for e in entries:
        body, bounded = _entry(e)
        (words if bounded else raw).append(body)
    alts = ([B + "(?:" + "|".join(words) + ")" + E] if words else []) + raw
    return re.compile("|".join(alts), re.I)


def _hit(p: re.Pattern | None, text: str) -> bool:
    return bool(p and p.search(text))


@dataclass
class Exclusion:
    name: str
    match: re.Pattern
    unless: re.Pattern | None
    at_investors: re.Pattern | None   # replaces `match` for jobs at investors / funders


class Rules:
    def __init__(self, cfg: dict, companies=None):
        cfg = cfg or {}
        t = cfg.get("title", {})
        self.noise = pattern(t.get("noise", []))
        self.topic = pattern(t.get("topic", []))
        self.also_relevant = pattern(t.get("also_relevant", []))
        self.exclusions = [Exclusion(x["name"], pattern(x["words"]), pattern(x.get("unless", [])),
                                     pattern(x["at_investors"]) if "at_investors" in x else None)
                           for x in cfg.get("exclude", [])]
        self.boosts = [(pattern(b["words"]), int(b["points"])) for b in cfg.get("boosts", [])]
        loc = cfg.get("location", {})
        self.local, self.remote = pattern(loc.get("local", [])), pattern(loc.get("remote", []))
        self.commutable, self.not_commutable = pattern(loc.get("commutable", [])), pattern(loc.get("not_commutable", []))
        self.foreign = pattern(loc.get("foreign", []))
        self.loc_points = {"local": 3, "remote": 2, "commutable": 1, "unknown": 0, **loc.get("points", {})}
        emp = cfg.get("employers", {})
        self.default_bonus = int(emp.get("default_bonus", 0))
        self.bonus = {}
        for points, names in (emp.get("bonus") or {}).items():
            self.bonus.update(dict.fromkeys(names, int(points)))
        inv = cfg.get("investors", {})
        funders = set(companies.funders) if companies is not None else set()
        self.investors = set(inv.get("employers", [])) | funders
        for name in funders:
            self.bonus.setdefault(name, int(emp.get("funder_bonus", self.default_bonus)))
        self.investor_roles = pattern(inv.get("roles", []))
        self.investor_bonus = int(inv.get("bonus", 0))
        dom = cfg.get("domain", {})
        self.domain_name = dom.get("name", "")
        self.domain = pattern(dom.get("tags", []))
        s = cfg.get("searches", {})
        self.searches = list(s.get("large_boards", []))
        self.portfolio_searches = self.searches + list(s.get("portfolio_extra", []))
        self.min_score = int(cfg.get("min_score", 0))

    def in_domain(self, text: str) -> bool:
        """Whether a portfolio company's name and industry tags fit the profile's domain (always, if none set)."""
        return self.domain is None or _hit(self.domain, text.lower())

    def site_points(self, site: str) -> int | None:
        """Location points for one listed site, or None if it is out of reach."""
        site = site.strip().lower()
        if _hit(self.local, site):
            return self.loc_points["local"]
        if _hit(self.remote, site) and not _hit(self.foreign, site):
            return self.loc_points["remote"]
        if _hit(self.commutable, site) and not _hit(self.not_commutable, site):
            return self.loc_points["commutable"]
        if UNKNOWN_LOCATION.search(site):
            return self.loc_points["unknown"]
        return None

    def score(self, company: str, title: str, location: str, outside_domain: bool = False):
        """None if the title is off-topic; (None, reason) if rejected; (points, None) if it is a match."""
        t = title.lower()
        if self.noise:
            t = self.noise.sub("", t)
        investor = company in self.investors and _hit(self.investor_roles, t)
        if not (_hit(self.topic, t) or investor or _hit(self.also_relevant, t)):
            return None
        for x in self.exclusions:
            match = x.at_investors if (x.at_investors is not None and company in self.investors) else x.match
            if _hit(match, t) and not _hit(x.unless, t):
                return None, x.name
        loc = max((p for p in map(self.site_points, re.split(r";|\|", location.lower())) if p is not None), default=None)
        if loc is None:
            return None, "location"
        s = sum(points for p, points in self.boosts if _hit(p, t)) + (self.investor_bonus if investor else 0) + loc
        s += 0 if outside_domain else self.bonus.get(company, self.default_bonus)
        return (s, None) if s >= self.min_score else (None, f"low score ({s})")
