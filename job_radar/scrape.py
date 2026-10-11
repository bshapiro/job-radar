"""Read every board in data/boards.json, score each job title with profile/rules.yaml, and write:

  data/jobs.csv       the matches, best first, with any verdicts already given
  data/rejected.csv   on-topic jobs that were filtered out, and why (for checking the rules)
  data/seen.json      every link ever matched, with the date first seen
  data/run.json       counts for the daily email
"""
from __future__ import annotations

import csv
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from . import describe
from .fetchers import FETCH
from .home import Home
from .rules import UNKNOWN_LOCATION, Rules

FIELDS = ["fit", "score", "new", "company", "title", "location", "posted", "url", "first_seen", "via", "note"]
REJECT_FIELDS = ["reason", "company", "title", "location", "url"]
FIT_ORDER = {"strong": 0, "maybe": 1, "": 2, "no": 3}   # "" = description not reviewed yet


@dataclass
class Raw:
    """Everything read from the boards in one run."""
    jobs: list = field(default_factory=list)          # (company, title, location, url, posted, via portfolio board or "")
    outside_domain: set = field(default_factory=set)  # portfolio companies whose tags don't fit the domain
    failed: list = field(default_factory=list)        # boards that could not be read

    def save(self, path: Path) -> None:
        path.write_text(json.dumps({"jobs": self.jobs, "outside_domain": sorted(self.outside_domain),
                                    "failed": self.failed}))

    @classmethod
    def load(cls, path: Path) -> "Raw":
        d = json.loads(path.read_text())
        return cls([tuple(j) for j in d["jobs"]], set(d["outside_domain"]), d["failed"])


def fetch_board(rules: Rules, company: str, b: dict, raw: Raw, attempts: int = 3) -> list:
    searches = rules.portfolio_searches if b["ats"] == "getro" else rules.searches
    try:
        jobs = []
        for j in FETCH[b["ats"]](b["slug"], searches):
            if len(j) == 6:   # portfolio board: the employer is the portfolio company
                *j, employer, tags = j
                if not rules.in_domain(f"{tags} {employer}"):
                    raw.outside_domain.add(employer)
                jobs.append((employer, *j, company))
            else:
                loc = f"{j[1]}; {b['location']}" if b.get("location") else j[1]   # vague locations ("United States")
                jobs.append((company, j[0], loc, j[2], j[3], ""))
        return jobs
    except Exception as e:
        if attempts > 1:   # boards fail transiently (timeouts, cut-off downloads); try again
            return fetch_board(rules, company, b, raw, attempts - 1)
        print(f"!! {company}: {e}")
        raw.failed.append(company)
        return []


def fetch_all(rules: Rules, boards: dict) -> Raw:
    raw = Raw()
    with ThreadPoolExecutor(8) as ex:
        batches = ex.map(lambda kv: fetch_board(rules, kv[0], kv[1], raw), boards.items())
        raw.jobs = [j for batch in batches for j in batch]
    return raw


def load_reviews(path: Path) -> dict:
    """Verdicts by link, and by (company, title) so a verdict survives a job's link changing."""
    reviews = {}
    if path.exists():
        with open(path) as f:
            for r in csv.DictReader(f):
                reviews[r["url"]] = r
                reviews.setdefault((r["company"].lower(), r["title"].lower()), r)
    return reviews


def select(rules: Rules, raw: Raw, boards: dict, seen: dict, reviews: dict, resolve=None, today: str | None = None):
    """(matches, rejects) from one run's jobs. `resolve(company, url)` returns the real locations of a job
    listed only as "3 Locations" (None to skip the lookup)."""
    today = today or date.today().isoformat()
    outside = raw.outside_domain - set(boards)   # a company read directly keeps its own bonus
    reject_reason = f"portfolio company outside {rules.domain_name}".rstrip()
    key = lambda company, title: (company.lower().strip(), title.lower().strip())
    jobs = sorted(raw.jobs, key=lambda j: bool(j[5]))   # direct boards first, so they win over portfolio copies
    used, rows, rejected = set(), [], []
    for company, title, location, url, posted, via in jobs:
        if url in used or (via and key(company, title) in used) or "linkedin.com" in url:
            continue
        used.update([url, key(company, title)])
        r = rules.score(company, title, location, outside_domain=company in outside)
        if r and r[0] is not None and via and company in outside:
            r = (None, reject_reason)
        if r is None:
            continue
        s, reason = r
        if s is not None and resolve and UNKNOWN_LOCATION.search(location.lower()):
            try:   # "3 Locations": look up the real sites and re-check
                location = resolve(company, url)
                s, reason = rules.score(company, title, location, outside_domain=company in outside)
            except Exception as e:
                print(f"!! could not resolve location for {company} | {title}: {e}")
        if s is None:
            rejected.append(dict(reason=reason, company=company, title=title.strip(), location=location, url=url))
            continue
        rev = reviews.get(url) or reviews.get((company.lower(), title.strip().lower()), {})
        rows.append(dict(fit=rev.get("fit", ""), note=rev.get("note", ""), score=s, new="" if url in seen else "NEW",
                         company=company, title=title.strip(), location=location, posted=posted, url=url, via=via,
                         first_seen=seen.get(url, today)))
    rejected.sort(key=lambda r: (r["reason"], r["company"]))
    rows.sort(key=lambda r: (FIT_ORDER[r["fit"]], -r["score"], r["company"]))
    return rows, rejected


def write_csv(path: Path, rows: list, fields: list) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def compare(home: Home, raw_in: Path) -> None:
    """Score saved jobs with the current rules and print how the matches and rejects would change against
    data/jobs.csv and data/rejected.csv. Writes nothing, so it is safe for trying out rule edits."""
    data = home.data
    boards = json.loads((data / "boards.json").read_text())
    seen = json.loads((data / "seen.json").read_text()) if (data / "seen.json").exists() else {}
    from .review import read_csv
    read = lambda name: read_csv(data / name)
    old_rows = {r["url"]: r for r in read("jobs.csv")}
    old_rej = {r["url"]: r["reason"] for r in read("rejected.csv")}
    # Hidden locations ("3 Locations") already looked up in the last run are reused; others are fetched.
    known = {r["url"]: r["location"] for r in [*old_rows.values(), *read("rejected.csv")]
             if not UNKNOWN_LOCATION.search(r["location"].lower())}
    resolve = lambda company, url: known.get(url) or describe.describe(boards.get(company), url)[1]
    rows, rejected = select(home.rules, Raw.load(raw_in), boards, seen, load_reviews(data / "reviews.csv"), resolve)
    new_rows, new_rej = {r["url"]: r for r in rows}, {r["url"]: r["reason"] for r in rejected}
    line = lambda r: f"{r['company'][:24]:24} {r['title'][:70]}"
    added = [u for u in new_rows if u not in old_rows]
    dropped = [u for u in old_rows if u not in new_rows]
    print(f"{len(rows)} matches now ({len(old_rows)} in jobs.csv): {len(added)} added, {len(dropped)} dropped")
    for u in added:
        print(f"  + {new_rows[u]['score']:>3} {line(new_rows[u])}  (was: {old_rej.get(u, 'not on topic')})")
    for u in dropped:
        print(f"  - {line(old_rows[u])}  (now: {new_rej.get(u, 'not on topic')}; fit was {old_rows[u]['fit'] or 'unread'})")
    moved = [(u, old_rej[u], r) for u, r in new_rej.items() if u in old_rej and old_rej[u] != r]
    if moved:
        print(f"{len(moved)} rejects with a different reason:")
        for u, was, now in moved:
            print(f"  ~ {line(next(x for x in rejected if x['url'] == u))}: {was} -> {now}")


def run(home: Home, raw_in: Path | None = None, raw_out: Path | None = None) -> None:
    data = home.data
    boards = json.loads((data / "boards.json").read_text())
    out = data / "jobs.csv"
    # Kept apart from jobs.csv so a job that drops out for a day (a board failing, say) isn't announced as new
    # when it comes back.
    seen_file = data / "seen.json"
    seen = json.loads(seen_file.read_text()) if seen_file.exists() else {}
    if out.exists():
        with open(out) as f:
            for r in csv.DictReader(f):
                seen.setdefault(r["url"], r["first_seen"])
    raw = Raw.load(raw_in) if raw_in else fetch_all(home.rules, boards)
    if raw_out:
        raw.save(raw_out)
    resolve = lambda company, url: describe.describe(boards.get(company), url)[1]
    rows, rejected = select(home.rules, raw, boards, seen, load_reviews(data / "reviews.csv"), resolve)
    write_csv(data / "rejected.csv", rejected, REJECT_FIELDS)
    seen.update({r["url"]: r["first_seen"] for r in rows})
    seen_file.write_text(json.dumps(seen, indent=0, sort_keys=True))
    write_csv(out, rows, FIELDS)
    (data / "run.json").write_text(json.dumps(
        {"date": date.today().isoformat(), "jobs": len(raw.jobs), "boards": len(boards), "matches": len(rows),
         "failed_boards": sorted(raw.failed)}, indent=1))
    print(f"{len(raw.jobs)} open jobs on {len(boards)} boards -> {len(rows)} matches "
          f"({sum(r['new'] == 'NEW' for r in rows)} new, {sum(not r['fit'] for r in rows)} unread) -> {out}; "
          f"{len(rejected)} on-topic rejects -> rejected.csv")
    for r in rows[:60]:
        print(f"{r['fit'] or 'unread':6} {r['score']:>3} {r['company'][:20]:20} {r['title'][:62]:62} {r['location'][:28]}")
