"""Find an employer's job board: `job-radar find-board "Example Bio" [careers page URL]`.

Tries the short names the employer might use on Greenhouse, Lever and Ashby, and, given a careers page,
looks for links to a known job system on it. Prints what it finds as lines to paste under `boards:` in
companies.yaml, most open jobs first. Check the result is the right company: a common name can belong
to someone else.
"""
from __future__ import annotations

import re
import urllib.request

from .discover import APIS, board_from_link, count, slugs
from .fetchers import BROWSER

PAGE_LINKS = [("greenhouse", r"(?:boards|job-boards)\.greenhouse\.io/(?:embed/job_board\?for=)?([\w-]+)"),
              ("lever", r"jobs\.lever\.co/([\w-]+)"), ("ashby", r"jobs\.ashbyhq\.com/([\w.-]+)"),
              ("workable", r"apply\.workable\.com/([\w-]+)"),
              ("oracle", r"([a-z0-9-]+\.fa\.[a-z0-9]+)\.oraclecloud\.com/hcmUI/CandidateExperience/[a-z]{2}/sites/([\w-]+)")]


def from_page(url: str) -> list[dict]:
    page = urllib.request.urlopen(urllib.request.Request(url, headers=BROWSER), timeout=30).read().decode("utf-8", "ignore")
    found = []
    for m in re.finditer(r"https?://[^\s\"'<>]+", page):
        link = m.group(0)
        b = board_from_link(link + "/")
        if not b:
            for ats, pattern in PAGE_LINKS:
                if p := re.search(pattern, link):
                    b = {"ats": ats, "slug": "/".join(p.groups())}
                    break
        if b and b not in found:
            found.append(b)
    return found


def find(name: str, page: str | None = None) -> list[dict]:
    hits = [{"ats": a, "slug": s, "open_jobs": n} for s in slugs(name, []) for a in APIS if (n := count(a, s))]
    if page:
        try:
            for b in from_page(page):
                if b["ats"] in APIS:
                    b["open_jobs"] = count(b["ats"], b["slug"])
                if not any(h["ats"] == b["ats"] and h["slug"] == b["slug"] for h in hits):
                    hits.append(b)
        except Exception as e:
            print(f"!! could not read {page}: {e}")
    return sorted(hits, key=lambda h: -h.get("open_jobs", 0))


def run(name: str, page: str | None = None) -> list[dict]:
    hits = find(name, page)
    if not hits:
        print(f"No board found for {name}. If its careers page links to a job system, pass that page too; "
              "otherwise its jobs may only be on a portfolio board or a page the engine can't read.")
    for h in hits:
        jobs = f"  # {h['open_jobs']} open jobs" if "open_jobs" in h else "  # check by hand"
        print(f'  {name}: {{ats: {h["ats"]}, slug: "{h["slug"]}"}}{jobs}')
    return hits
