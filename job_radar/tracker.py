"""Track which matches have been acted on, and keep the rest from being forgotten.

Strong and maybe matches get "Applied" / "Not interested" tick boxes in GitHub issues labelled
`tracker`: one issue for each day's new matches, and on Mondays a reminder issue listing every match
still open with no status, oldest first. Each run reads all tracker issues back into
data/applications.csv (latest tick wins), so a job can be marked from any issue it appears in.
Issues are never edited after creation, so a tick can't be overwritten. They are closed after
`close_after_days` (settings.yaml, `tracker:`) but are still read.

A status can also be recorded by adding a row to data/applications.csv by hand.

Each run also notices strong / maybe matches with no status that have disappeared from their
company's board (missing two runs in a row), so a missed posting is reported, not silently lost.

Writes data/tracker.json for the digest: the issues opened this run, the disappeared jobs, and how
many matches are still waiting. Without GitHub (GH_TOKEN and GITHUB_REPOSITORY), no issues are read or opened.
"""
from __future__ import annotations

import csv
import json
import os
import re
import subprocess
from datetime import date, timedelta

from .describe import job_id
from .home import Home
from .review import AUTO, read_csv

LABEL = "tracker"
CHOICES = ["Applied", "Not interested"]
ACTIVE_FITS = ("strong", "maybe")
DEFAULTS = {"close_after_days": 21, "weekly_on": "monday"}
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MARK = re.compile(r"<!-- job:([0-9a-f]{12}) -->")
BOX = re.compile(r"^\s*- \[([ xX])\] (.+?)\s*$")
APP_FIELDS = ["recorded", "job", "company", "title", "status", "issue", "url"]


def gh(*args) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def github_available() -> bool:
    return bool(os.environ.get("GH_TOKEN") and os.environ.get("GITHUB_REPOSITORY"))


def statuses(home: Home) -> dict:
    """{job id: latest status row} from data/applications.csv."""
    return {r["job"]: r for r in read_csv(home.data / "applications.csv")}


def parse(body: str) -> dict:
    """{job id: status} for every job block in an issue body; status is "" when nothing is ticked."""
    out, ticked = {}, []
    for line in body.splitlines():
        m = MARK.search(line)
        if m:
            picked = [t for t in ticked if t in CHOICES]
            out[m.group(1)] = picked[-1] if picked else ""   # two ticks: the later choice wins
            ticked = []
            continue
        b = BOX.match(line)
        if b and b.group(1) in "xX":
            ticked.append(b.group(2))
        elif line.startswith("### "):
            ticked = []
    return out


def sync(home: Home, jobs_by_id: dict, today: str, close_after_days: int) -> int:
    """Read every tracker issue and append status changes to data/applications.csv."""
    if not github_available():
        return 0
    issues = json.loads(gh("issue", "list", "--label", LABEL, "--state", "all", "--limit", "500",
                           "--json", "number,body,createdAt,state"))
    ticks = {}
    for iss in sorted(issues, key=lambda i: i["createdAt"]):   # a later issue's tick wins
        for jid, status in parse(iss["body"]).items():
            if status:
                ticks[jid] = (status, iss["number"])
    current, rows = statuses(home), []
    for jid, (status, number) in ticks.items():
        if current.get(jid, {}).get("status") == status:
            continue
        job = jobs_by_id.get(jid, current.get(jid, {}))
        rows.append(dict(recorded=today, job=jid, company=job.get("company", ""), title=job.get("title", ""),
                         status=status, issue=number, url=job.get("url", "")))
    if rows:
        path = home.data / "applications.csv"
        new = not path.exists()
        with open(path, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=APP_FIELDS)
            if new:
                w.writeheader()
            w.writerows(rows)
    cutoff = (date.fromisoformat(today) - timedelta(days=close_after_days)).isoformat()
    for iss in issues:
        if iss["state"] == "OPEN" and iss["createdAt"][:10] < cutoff:
            gh("issue", "close", str(iss["number"]))
    return len(rows)


def block(job: dict, today: str) -> str:
    days = (date.fromisoformat(today) - date.fromisoformat(job["first_seen"])).days
    age = "new today" if days == 0 else f"first seen {days} day{'s' if days != 1 else ''} ago"
    note = job["note"].replace(AUTO, "")
    return "\n".join([f"### [{job['fit']}] {job['company']}: [{job['title']}]({job['url']})",
                      f"{job['location'][:90]} · {age}", "", note, "",
                      *[f"- [ ] {c}" for c in CHOICES], "", f"<!-- job:{job_id(job['url'])} -->"])


def open_issue(title: str, intro: str, jobs: list, today: str):
    """Create a tracker issue; returns its URL, or None when there is nothing to list or no GitHub."""
    if not jobs or not github_available():
        return None
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER")
    body = "\n\n".join([intro + (f" cc @{owner}" if owner else "")] + [block(j, today) for j in jobs])
    gh("label", "create", LABEL, "--color", "1f883d", "--description", "Job application tracker", "--force")
    return gh("issue", "create", "--title", title, "--label", LABEL, "--body", body).strip()


def run(home: Home, weekly: bool = False, today: date | None = None) -> dict:
    cfg = {**DEFAULTS, **(home.settings.get("tracker") or {})}
    day = today or date.today()
    today = day.isoformat()
    weekly = weekly or DAYS[day.weekday()] == str(cfg["weekly_on"]).lower()
    jobs = read_csv(home.data / "jobs.csv")
    by_id = {job_id(j["url"]): j for j in jobs}
    changed = sync(home, by_id, today, int(cfg["close_after_days"]))
    done = statuses(home)

    waiting = [j for j in jobs if j["fit"] in ACTIVE_FITS and job_id(j["url"]) not in done]
    waiting.sort(key=lambda j: (j["first_seen"], j["fit"] != "strong"))   # oldest first
    new = [j for j in waiting if j["new"] == "NEW"]

    # Matches that were waiting and are no longer on their company's board. A job must be missing for
    # two runs in a row before it is reported, so one failed board fetch doesn't raise a false alarm.
    pending_file = home.data / "pending.json"
    before = json.loads(pending_file.read_text()) if pending_file.exists() else {}
    pending = {job_id(j["url"]): {**{k: j[k] for k in ("company", "title", "fit", "url", "first_seen")}, "missing": 0}
               for j in waiting}
    gone = []
    for k, v in before.items():
        if k in by_id or k in done:
            continue
        if v.get("missing", 0) >= 1:
            gone.append(v)
        else:
            pending[k] = {**v, "missing": 1}
    pending_file.write_text(json.dumps(pending, indent=1, sort_keys=True))

    intro = "Tick **Applied** or **Not interested** for each job you act on; untouched jobs stay on the weekly reminder."
    new_issue = open_issue(f"New matches {today} ({len(new)})", intro, new, today)
    weekly_issue = open_issue(f"Still to act on {today} ({len(waiting)})",
                              intro + " Oldest first; older postings close soonest.", waiting, today) if weekly else None

    out = {"date": today, "new_issue": new_issue, "weekly_issue": weekly_issue, "waiting": len(waiting), "gone": gone}
    (home.data / "tracker.json").write_text(json.dumps(out, indent=1))
    print(f"tracker: {changed} status changes recorded; {len(waiting)} matches waiting; "
          f"{len(gone)} disappeared; issues: {new_issue or '-'} {weekly_issue or '-'}")
    return out
