"""Write digest.md and digest.html (in the profile repo's root) for the daily email: today's new matches,
links to the tracker issues where they can be marked Applied / Not interested, the weekly reminder of
matches still waiting, and any waiting matches that have disappeared from their boards. On a day with
none of those it writes a one-line "nothing new" note, so a quiet day is distinguishable from a broken
run. digest_subject.txt holds the email subject.

test=True sends the current strong matches instead, to check that email arrives.
"""
from __future__ import annotations

import csv
import html
import json
import os

from .home import Home
from .review import AUTO

ORDER = {"strong": 0, "maybe": 1, "": 2, "no": 3}
FILES = ("digest.md", "digest.html", "digest_subject.txt")


def build(home: Home, test: bool = False) -> tuple[str, str, str]:
    """(markdown, html, subject)."""
    data = home.data
    with open(data / "jobs.csv") as f:
        new = [r for r in csv.DictReader(f)
               if (r["fit"] == "strong" if test else r["new"] == "NEW" and r["fit"] != "no")]
    tracker_file = data / "tracker.json"
    tracker = json.loads(tracker_file.read_text()) if tracker_file.exists() and not test else {}
    gone, weekly = tracker.get("gone", []), tracker.get("weekly_issue")
    run_file = data / "run.json"
    run = json.loads(run_file.read_text()) if run_file.exists() else {}
    quiet = not (new or gone or weekly)
    new.sort(key=lambda r: (ORDER[r["fit"]], -int(r["score"])))
    unread = sum(not r["fit"] for r in new)
    cell = lambda s: html.escape(s or "")
    md, h = [], []

    if new:
        md += [f"{len(new)} new matching jobs ({unread} not yet reviewed). Verdicts marked 'Auto-review' were "
               "made by Claude from the full description.", "",
               "| Fit | Company | Title | Location | Note |", "|---|---|---|---|---|"]
        for r in new:
            note = r["note"].replace(AUTO, "").replace("|", "/")
            md.append(f"| {r['fit'] or 'unreviewed'} | {r['company']} | [{r['title']}]({r['url']}) | "
                      f"{r['location'].replace('|', '/')[:60]} | {note} |")
        rows = "".join(
            f"<tr><td>{cell(r['fit'] or 'unreviewed')}</td><td>{cell(r['company'])}</td>"
            f"<td><a href=\"{cell(r['url'])}\">{cell(r['title'])}</a><br><small>{cell(r['location'][:80])}</small></td>"
            f"<td>{cell(r['note'].replace(AUTO, ''))}</td></tr>" for r in new)
        h.append(f"<p>{len(new)} new matching jobs ({unread} not yet reviewed).</p>"
                 "<table border=\"1\" cellpadding=\"6\" style=\"border-collapse:collapse;font-family:sans-serif;font-size:14px\">"
                 f"<tr><th>Fit</th><th>Company</th><th>Role</th><th>Note</th></tr>{rows}</table>")
        if tracker.get("new_issue"):
            md += ["", f"Mark these Applied / Not interested: {tracker['new_issue']}"]
            h.append(f"<p><a href=\"{cell(tracker['new_issue'])}\">Mark these Applied / Not interested</a></p>")

    if weekly:
        line = f"{tracker['waiting']} strong or maybe matches are still waiting for a decision."
        md += ["", f"**Weekly reminder.** {line} Tick them here: {weekly}"]
        h.append(f"<h3>Weekly reminder</h3><p>{cell(line)} <a href=\"{cell(weekly)}\">Review and tick them</a> "
                 "(oldest first; older postings close soonest).</p>")

    if gone:
        md += ["", "**No longer listed.** These matches had no Applied / Not interested mark and have "
               "disappeared from their company's board (closed, or moved):"]
        md += [f"- [{g['fit']}] {g['company']}: [{g['title']}]({g['url']}) (first seen {g['first_seen']})" for g in gone]
        items = "".join(f"<li>[{cell(g['fit'])}] {cell(g['company'])}: <a href=\"{cell(g['url'])}\">{cell(g['title'])}</a> "
                        f"(first seen {cell(g['first_seen'])})</li>" for g in gone)
        h.append(f"<h3>No longer listed</h3><p>These matches had no Applied / Not interested mark and have "
                 f"disappeared from their company's board:</p><ul>{items}</ul>")

    if quiet:
        line = (f"No new matches today. {run.get('jobs', 0):,} open jobs checked on {run.get('boards', 0)} boards; "
                f"{tracker.get('waiting', 0)} matches still waiting for an Applied / Not interested mark.")
        md.append(line)
        h.append(f"<p>{cell(line)}</p>")
    if run.get("failed_boards"):
        line = f"Boards that couldn't be read today (they'll be retried tomorrow): {', '.join(run['failed_boards'])}."
        md += ["", line]
        h.append(f"<p><small>{cell(line)}</small></p>")

    repo = os.environ.get("GITHUB_REPOSITORY", "").split("/")[-1]
    where = f"the {repo} repo" if repo else "your job-radar repo"
    h.append(f"<p><small>Full list: data/jobs.csv in {where}. Correct a verdict in data/reviews.csv.</small></p>")
    today = run.get("date") or tracker.get("date") or ""
    subject = (f"Job matches {today}: {len(new)} new" if new else
               f"Job matches {today}: weekly reminder" if weekly else
               f"Job matches {today}: {len(gone)} no longer listed" if gone else
               f"No new job matches {today}")
    print(f"{len(new)} new, {len(gone)} gone, weekly reminder {'yes' if weekly else 'no'} -> digest.md")
    return "\n".join(md) + "\n", "".join(h), subject + (" (test)" if test else "")


def run(home: Home, test: bool = False) -> None:
    for name, text in zip(FILES, build(home, test)):
        (home.root / name).write_text(text)
