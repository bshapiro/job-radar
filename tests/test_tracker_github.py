"""The tracker against a fake `gh` command."""
import csv
import json
from datetime import date

import pytest

from job_radar import tracker
from job_radar.describe import job_id
from job_radar.scrape import FIELDS


class FakeGH:
    def __init__(self, issues):
        self.issues = issues
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        if args[:2] == ("issue", "list"):
            return json.dumps(self.issues)
        if args[:2] == ("issue", "create"):
            return f"https://github.com/me/jobs/issues/{100 + len(self.calls)}\n"
        return ""

    def created(self):
        return [dict(zip(a[2::2], a[3::2])) for a in self.calls if a[:2] == ("issue", "create")]


def body(*blocks):
    return "\n\n".join(f"### [strong] X\n- [{'x' if s == 'Applied' else ' '}] Applied\n"
                       f"- [{'x' if s == 'Not interested' else ' '}] Not interested\n\n<!-- job:{job_id(u)} -->"
                       for u, s in blocks)


def job(n, fit="strong", new="NEW", first_seen="2026-10-01"):
    return dict(fit=fit, score="9", new=new, company="Lab Co", title=f"Job {n}", location="NYC", posted="",
                url=f"https://a/{n}", first_seen=first_seen, via="", note="Auto-review: ok")


@pytest.fixture
def github(home, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "x")
    monkeypatch.setenv("GITHUB_REPOSITORY", "me/jobs")
    monkeypatch.setenv("GITHUB_REPOSITORY_OWNER", "me")

    def make(issues, jobs):
        fake = FakeGH(issues)
        monkeypatch.setattr(tracker, "gh", fake)
        with open(home.data / "jobs.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(jobs)
        return fake
    return make


def apps(home):
    with open(home.data / "applications.csv") as f:
        return list(csv.DictReader(f))


def test_ticks_are_recorded_and_the_latest_issue_wins(home, github):
    issues = [
        {"number": 1, "createdAt": "2026-10-01T11:00:00Z", "state": "OPEN",
         "body": body(("https://a/1", "Applied"), ("https://a/2", "Applied"))},
        {"number": 2, "createdAt": "2026-10-06T11:00:00Z", "state": "OPEN",
         "body": body(("https://a/2", "Not interested"), ("https://a/3", ""))},
    ]
    gh = github(issues, [job(1), job(2), job(3), job(4, new="")])
    out = tracker.run(home, today=date(2026, 10, 14))     # a Wednesday
    rows = {r["title"]: (r["status"], r["issue"]) for r in apps(home)}
    assert rows == {"Job 1": ("Applied", "1"), "Job 2": ("Not interested", "2")}
    assert out["waiting"] == 2 and out["weekly_issue"] is None
    new = gh.created()
    assert len(new) == 1 and new[0]["--title"] == "New matches 2026-10-14 (1)" and new[0]["--label"] == "tracker"
    assert "cc @me" in new[0]["--body"] and "Job 3" in new[0]["--body"] and "Job 4" not in new[0]["--body"]
    assert out["new_issue"].startswith("https://github.com/me/jobs/issues/")
    # nothing changed: a second run records nothing new
    tracker.run(home, today=date(2026, 10, 14))
    assert len(apps(home)) == 2


def test_old_issues_are_closed(home, github):
    issues = [{"number": 7, "createdAt": "2026-09-01T11:00:00Z", "state": "OPEN", "body": ""},
              {"number": 8, "createdAt": "2026-10-10T11:00:00Z", "state": "OPEN", "body": ""},
              {"number": 6, "createdAt": "2026-08-01T11:00:00Z", "state": "CLOSED", "body": ""}]
    gh = github(issues, [])
    tracker.run(home, today=date(2026, 10, 14))
    assert ("issue", "close", "7") in gh.calls and not any(c[:3] == ("issue", "close", "8") for c in gh.calls)
    assert not any(c[:3] == ("issue", "close", "6") for c in gh.calls)


def test_weekly_reminder_on_the_set_day(home, github):
    gh = github([], [job(1, new=""), job(2, fit="maybe", new="", first_seen="2026-09-20")])
    out = tracker.run(home, today=date(2026, 10, 12))     # a Monday
    weekly = [c for c in gh.created() if c["--title"].startswith("Still to act on")]
    assert len(weekly) == 1 and weekly[0]["--title"] == "Still to act on 2026-10-12 (2)"
    assert weekly[0]["--body"].index("Job 2") < weekly[0]["--body"].index("Job 1")   # oldest first
    assert out["weekly_issue"] and out["new_issue"] is None


def test_weekly_day_is_a_setting(home, github):
    (home.profile / "settings.yaml").write_text("tracker: {weekly_on: friday, close_after_days: 3}\n")
    github([], [job(1, new="")])
    assert tracker.run(home, today=date(2026, 10, 12))["weekly_issue"] is None
    assert tracker.run(home, today=date(2026, 10, 16))["weekly_issue"]
    assert tracker.run(home, today=date(2026, 10, 13), weekly=True)["weekly_issue"]


def test_without_github_nothing_is_read_or_opened(home, monkeypatch):
    monkeypatch.setattr(tracker, "gh", lambda *a: pytest.fail("gh called"))
    with open(home.data / "jobs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerow(job(1))
    out = tracker.run(home, today=date(2026, 10, 12))
    assert out["new_issue"] is None and out["weekly_issue"] is None and out["waiting"] == 1
