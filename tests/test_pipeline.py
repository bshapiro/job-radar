import csv
import json
import zipfile
from datetime import date
from pathlib import Path

import pytest
import yaml

from job_radar import digest, linkedin, setup, tracker
from job_radar.companies import PACKS, Companies, available_packs
from job_radar.describe import job_id
from job_radar.discover import board_from_link, slugs
from job_radar.fetchers import FETCH
from job_radar.home import Home
from job_radar.scrape import FIELDS, Raw, select

FIXTURE = Path(__file__).parent / "fixtures" / "home"


# ---- companies and packs ----

def test_packs_are_valid():
    known_ats = set(FETCH)
    for name in available_packs():
        cfg = yaml.safe_load((PACKS / f"{name}.yaml").read_text())
        assert cfg.get("description"), name
        c = Companies.load({"packs": [name]})
        for company, b in c.boards.items():
            assert b["ats"] in known_ats, (name, company)
            assert "slug" in b, (name, company)
        for company, b in c.portfolio_boards.items():
            assert b["ats"] in ("getro", "consider") and b.get("host"), (name, company)


def test_companies_merge_packs_then_file(home):
    c = home.companies
    assert "Schmidt Sciences" in c.boards and c.boards["Schmidt Sciences"]["funder"]
    assert "Simons Foundation" not in c.boards              # excluded
    assert c.find_boards["Example Health"] == ["examplehealth"]
    assert ("ashby", "example") in c.wrong_slugs
    assert c.funders >= {"A Fund", "Schmidt Sciences", "ARPA-H"}


def test_unknown_pack_is_reported():
    with pytest.raises(FileNotFoundError, match="no pack named"):
        Companies.load({"packs": ["nope"]})


def test_slug_guesses_and_board_links():
    assert slugs("The Example Group", ["ex"])[:3] == ["theexamplegroup", "example", "the-example-group"]
    assert board_from_link("https://job-boards.greenhouse.io/acme/jobs/123") == {"ats": "greenhouse", "slug": "acme"}
    assert board_from_link("https://jobs.lever.co/acme/abc-def") == {"ats": "lever", "slug": "acme"}
    assert board_from_link("https://acme.wd5.myworkdayjobs.com/en-US/External/job/x") == \
        {"ats": "workday", "slug": "acme.wd5/acme/External"}
    assert board_from_link("https://example.com/careers") is None


# ---- selecting matches ----

def test_select(home):
    rules = home.rules
    raw = Raw(jobs=[
        ("Lab Co", "Director, Machine Learning", "New York, NY", "https://a/1", "2026-10-01", ""),
        # the same job on a portfolio board: dropped in favour of the direct copy
        ("Lab Co", "Director, Machine Learning", "New York", "https://portfolio/1", "2026-10-01", "Some Ventures portfolio"),
        ("Lab Co", "Machine Learning Engineer", "New York", "https://a/2", "", ""),
        ("Lab Co", "Head of AI", "Remote", "https://www.linkedin.com/jobs/3", "", ""),
        ("Payments Inc", "Head of AI", "New York", "https://p/4", "", "Some Ventures portfolio"),
        ("Example Health", "Chief of Staff", "NYC", "https://e/5", "", ""),
        ("Example Health", "Office Manager", "NYC", "https://e/6", "", ""),     # off-topic: not even logged
    ], outside_domain={"Payments Inc"})
    seen = {"https://e/5": "2026-09-01"}
    reviews = {("example health", "chief of staff"): {"fit": "strong", "note": "Good."}}
    rows, rejected = select(rules, raw, {}, seen, reviews, today="2026-10-11")
    assert [(r["company"], r["title"], r["score"]) for r in rows] == [
        ("Example Health", "Chief of Staff", 9), ("Lab Co", "Director, Machine Learning", 8)]
    assert rows[0]["fit"] == "strong" and rows[0]["new"] == "" and rows[0]["first_seen"] == "2026-09-01"
    assert rows[1]["new"] == "NEW" and rows[1]["first_seen"] == "2026-10-11"
    assert set(rows[0]) == set(FIELDS)
    assert {(r["company"], r["reason"]) for r in rejected} == {
        ("Lab Co", "hands-on engineering"), ("Payments Inc", "portfolio company outside health")}


def test_select_resolves_hidden_locations(home):
    # Only a job that already passes with 0 location points is looked up (as before the refactor).
    raw = Raw(jobs=[("Lab Co", "Head of AI, Health", "2 Locations", "https://a/1", "", ""),   # 4 + 2 + 0 + 1
                    ("Lab Co", "Director of AI, Biology", "3 Locations", "https://a/2", "", ""),
                    ("Lab Co", "Head of AI", "3 Locations", "https://a/3", "", "")])           # 5: not looked up
    where = {"https://a/1": "Remote", "https://a/2": "London"}
    rows, rejected = select(home.rules, raw, {}, {}, {}, resolve=lambda company, url: where[url])
    assert [(r["title"], r["location"], r["score"]) for r in rows] == [("Head of AI, Health", "Remote", 9)]
    assert {r["url"]: r["reason"] for r in rejected} == {"https://a/2": "location", "https://a/3": "low score (5)"}


def test_raw_round_trip(tmp_path):
    raw = Raw(jobs=[("A", "t", "l", "u", "p", "")], outside_domain={"X"}, failed=["B"])
    raw.save(tmp_path / "raw.json")
    back = Raw.load(tmp_path / "raw.json")
    assert back.jobs == raw.jobs and back.outside_domain == {"X"} and back.failed == ["B"]


# ---- tracker and digest ----

def job(url, fit="strong", new="NEW", first_seen="2026-10-11", **kw):
    return dict(fit=fit, score="9", new=new, company="Lab Co", title=f"Job {url[-1]}", location="New York",
                posted="", url=url, first_seen=first_seen, via="", note="Auto-review: Fine.", **kw)


def write_jobs(home, jobs):
    with open(home.data / "jobs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(jobs)


def test_tracker_parse_issue_body():
    a, b, c = job_id("https://a/1"), job_id("https://a/2"), job_id("https://a/3")
    body = "\n".join(["intro", "### [strong] A", "- [x] Applied", "- [ ] Not interested", f"<!-- job:{a} -->",
                      "### [maybe] B", "- [ ] Applied", "- [ ] Not interested", f"<!-- job:{b} -->",
                      "### [maybe] C", "- [x] Applied", "- [X] Not interested", f"<!-- job:{c} -->"])
    assert tracker.parse(body) == {a: "Applied", b: "", c: "Not interested"}


def test_tracker_block_has_marker():
    text = tracker.block(job("https://a/1", first_seen="2026-10-09"), "2026-10-11")
    assert "first seen 2 days ago" in text and f"<!-- job:{job_id('https://a/1')} -->" in text
    assert "Auto-review" not in text and tracker.parse(text) == {job_id("https://a/1"): ""}


def test_tracker_reports_jobs_gone_two_runs_running(home, monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    write_jobs(home, [job("https://a/1"), job("https://a/2", fit="no")])
    out = tracker.run(home, today=date(2026, 10, 13))         # a Tuesday
    assert out["waiting"] == 1 and out["gone"] == [] and out["weekly_issue"] is None
    write_jobs(home, [])
    assert tracker.run(home, today=date(2026, 10, 14))["gone"] == []        # missing once: not yet
    gone = tracker.run(home, today=date(2026, 10, 15))["gone"]
    assert [g["url"] for g in gone] == ["https://a/1"]
    assert tracker.run(home, today=date(2026, 10, 16))["gone"] == []        # reported once only


def test_tracker_skips_jobs_with_a_status(home, monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    write_jobs(home, [job("https://a/1"), job("https://a/2")])
    with open(home.data / "applications.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=tracker.APP_FIELDS)
        w.writeheader()
        w.writerow(dict(recorded="2026-10-10", job=job_id("https://a/1"), company="Lab Co", title="Job 1",
                        status="Applied", issue="", url="https://a/1"))
    assert tracker.run(home, today=date(2026, 10, 13))["waiting"] == 1


def test_digest_new_and_quiet(home):
    write_jobs(home, [job("https://a/1"), job("https://a/2", fit="no"), job("https://a/3", new="")])
    (home.data / "run.json").write_text(json.dumps({"date": "2026-10-11", "jobs": 1000, "boards": 10, "matches": 3}))
    md, html, subject = digest.build(home)
    assert subject == "Job matches 2026-10-11: 1 new"
    assert "Job 1" in md and "Job 2" not in md and "Auto-review: " not in html
    write_jobs(home, [job("https://a/3", new="")])
    md, _, subject = digest.build(home)
    assert subject == "No new job matches 2026-10-11" and "1,000 open jobs checked on 10 boards" in md
    _, _, subject = digest.build(home, test=True)
    assert subject.endswith("(test)")


# ---- LinkedIn import ----

def test_linkedin_import_from_zip(home, tmp_path):
    saved = 'Saved Date,Job Url,Job Title,Company Name\n"10/2/26, 9:15 AM",https://li/1,Head of AI,Lab Co\n,https://li/2,,Gone\n'
    applied = ('Application Date,Contact Email,Contact Phone Number,Company Name,Job Title,Job Url\n'
               '"9/30/26, 4:01\u202fPM",x,y,Example Health,Chief of Staff,https://li/3\n')
    export = tmp_path / "export.zip"
    with zipfile.ZipFile(export, "w") as z:
        z.writestr("Jobs/Saved Jobs.csv", "﻿" + saved)
        z.writestr("Jobs/Job Applications.csv", applied)
    rows = linkedin.run(home, str(export))
    assert [(r["source"], r["date"], r["company"]) for r in rows] == [
        ("saved", "2026-10-02", "Lab Co"), ("applied", "2026-09-30", "Example Health")]
    assert (home.data / "seed_jobs.csv").exists()


# ---- init and doctor ----

def test_init_makes_a_working_profile(tmp_path, monkeypatch):
    made = setup.init(tmp_path / "me")
    names = {str(p.relative_to(tmp_path / "me")) for p in made}
    assert {"profile/rules.yaml", "profile/companies.yaml", "profile/preferences.md", "profile/settings.yaml",
            "profile/review_prompt.md", ".github/workflows/daily.yml", ".gitignore"} <= names
    wf = (tmp_path / "me" / ".github" / "workflows" / "daily.yml").read_text()
    assert "{version}" not in wf and "{engine_repo}" not in wf and "${{ secrets.ANTHROPIC_API_KEY }}" in wf
    assert setup.init(tmp_path / "me") == []          # never overwrites
    monkeypatch.setattr(setup, "_secrets_on_github", lambda: None)
    assert setup.doctor(Home(tmp_path / "me")) is False   # preferences.md is still the template


def test_digest_weekly_gone_and_failed_boards(home):
    write_jobs(home, [job("https://a/1")])
    (home.data / "run.json").write_text(json.dumps({"date": "2026-10-12", "jobs": 10, "boards": 2, "matches": 1,
                                                    "failed_boards": ["Broken Co"]}))
    (home.data / "tracker.json").write_text(json.dumps({
        "date": "2026-10-12", "new_issue": "https://gh/issues/5", "weekly_issue": "https://gh/issues/6", "waiting": 4,
        "gone": [{"fit": "strong", "company": "Old Co", "title": "Gone <Role>", "url": "https://o/1",
                  "first_seen": "2026-09-01"}]}))
    md, html, subject = digest.build(home)
    assert subject == "Job matches 2026-10-12: 1 new"
    assert "Mark these Applied / Not interested: https://gh/issues/5" in md
    assert "**Weekly reminder.** 4 strong or maybe matches" in md and 'href="https://gh/issues/6"' in html
    assert "**No longer listed.**" in md and "Gone &lt;Role&gt;" in html          # escaped in HTML
    assert "Broken Co" in md and "Broken Co" in html
    write_jobs(home, [])
    assert digest.build(home)[2] == "Job matches 2026-10-12: weekly reminder"
    t = json.loads((home.data / "tracker.json").read_text())
    t["weekly_issue"] = None
    (home.data / "tracker.json").write_text(json.dumps(t))
    assert digest.build(home)[2] == "Job matches 2026-10-12: 1 no longer listed"


def test_digest_run_writes_files_and_names_the_repo(home, monkeypatch):
    write_jobs(home, [job("https://a/1")])
    monkeypatch.setenv("GITHUB_REPOSITORY", "me/my-jobs")
    digest.run(home)
    assert (home.root / "digest_subject.txt").read_text().endswith("1 new")
    assert "in the my-jobs repo" in (home.root / "digest.html").read_text()
    assert (home.root / "digest.md").exists()


def test_linkedin_import_from_folder_and_empty(home, tmp_path, capsys):
    (tmp_path / "export" / "Jobs").mkdir(parents=True)
    (tmp_path / "export" / "Jobs" / "Saved Jobs.csv").write_text(
        'Saved Date,Job Url,Job Title,Company Name\n"1/5/26, 10:00 PM",https://li/1,Head of AI,Lab Co\n')
    assert [r["date"] for r in linkedin.run(home, str(tmp_path / "export"))] == ["2026-01-05"]
    (tmp_path / "other").mkdir()
    assert linkedin.run(home, str(tmp_path / "other")) == []
    assert "try the other one" in capsys.readouterr().out
