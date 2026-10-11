"""Work out each employer's job board and write data/boards.json.

Known boards are used as they are. For `find_boards` employers, the short names a board might use on
Greenhouse, Lever and Ashby are tried and the one with the most open jobs wins (check new finds: a
common name can belong to a different company). With `harvest_portfolio`, every portfolio board is read
and the own boards of its in-domain companies are added, so their full listings are read directly.
"""
from __future__ import annotations

import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .fetchers import FETCH, PORTFOLIO, USER_AGENT
from .home import Home

APIS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{}/jobs",
    "lever": "https://api.lever.co/v0/postings/{}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{}",
}
BOARD_LINKS = [("greenhouse", r"greenhouse\.io/(?:embed/job_app\?for=)?([\w-]+)/jobs"),
               ("lever", r"jobs\.lever\.co/([\w-]+)/"), ("ashby", r"jobs\.ashbyhq\.com/([^/?]+)/"),
               ("workday", r"([a-z0-9-]+\.wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([\w-]+)/")]


def count(ats: str, slug: str) -> int:
    try:
        req = urllib.request.Request(APIS[ats].format(slug), headers={"User-Agent": USER_AGENT})
        d = json.load(urllib.request.urlopen(req, timeout=15))
    except Exception:
        return 0
    return len(d if isinstance(d, list) else d.get("jobs", []))


def slugs(name: str, extra: list[str]) -> list[str]:
    words = re.sub(r"[^a-z0-9 ]", "", name.lower()).split()
    core = [w for w in words if w not in ("the", "group", "health", "ai", "inc")] or words
    return list(dict.fromkeys(["".join(words), "".join(core), "-".join(words), core[0], *extra]))


def guess(name: str, extra: list[str], wrong: set) -> dict | None:
    hits = [(count(a, s), a, s) for s in slugs(name, extra) for a in APIS if (a, s) not in wrong]
    n, ats, slug = max(hits)
    return {"ats": ats, "slug": slug, "open_jobs": n} if n else None


def board_from_link(url: str) -> dict | None:
    for ats, pattern in BOARD_LINKS:
        if m := re.search(pattern, url):
            if ats == "workday":
                host, site = m.groups()
                return {"ats": ats, "slug": f"{host}/{host.split('.')[0]}/{site}"}
            return {"ats": ats, "slug": m.group(1)}
    return None


def harvest(home: Home, found: dict) -> dict:
    """Own boards of in-domain companies seen on portfolio boards."""
    rules, comp = home.rules, home.companies
    out = {}
    for name, b in found.items():
        if b["ats"] not in PORTFOLIO:
            continue
        try:
            jobs = list(FETCH[b["ats"]](b["slug"], rules.portfolio_searches))
        except Exception as e:
            print(f"!! {name}: {e}")
            continue
        for _, _, url, _, company, tags in jobs:
            company = company.strip()
            if (company in out or company in found or company in comp.not_in_domain
                    or not rules.in_domain(f"{tags} {company}")):
                continue
            if board := board_from_link(url):
                out[company] = {**board, "found_via": name}
    return out


def run(home: Home) -> dict:
    comp = home.companies
    known = {**comp.boards,
             **{f"{name} portfolio": {"ats": b["ats"], "slug": b["host"]} for name, b in comp.portfolio_boards.items()}}
    todo = {k: v for k, v in comp.find_boards.items() if k not in known}
    with ThreadPoolExecutor(8) as ex:
        guessed = dict(zip(todo, ex.map(lambda kv: guess(kv[0], kv[1], comp.wrong_slugs), todo.items())))
    found = {**known, **{k: v for k, v in guessed.items() if v}}
    if comp.harvest_portfolio:
        added = harvest(home, found)
        print(f"{len(added)} companies added from portfolio boards")
        found.update(added)
    home.data.mkdir(parents=True, exist_ok=True)
    (home.data / "boards.json").write_text(json.dumps(found, indent=2))
    for k, v in found.items():
        print(f"{k:38} {v['ats']:11} {v['slug']:45} {v.get('open_jobs', '')}")
    missing = [k for k, v in guessed.items() if not v]
    if missing:
        print("\nNo board found (add one under `boards:` if you know it):", ", ".join(missing))
    return found
