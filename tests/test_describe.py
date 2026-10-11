import csv
import json

import pytest

from job_radar import describe
from job_radar.describe import job_id, text


def test_text_turns_html_into_paragraphs():
    assert text("&lt;p&gt;One&lt;/p&gt;&lt;ul&gt;&lt;li&gt;Two &amp;amp; three&lt;/li&gt;&lt;/ul&gt;") == "One\nTwo & three"
    assert text("<p>A</p>\n\n\n<p>B</p>") == "A\n\nB"
    assert text(None) == ""


def test_job_id_is_stable():
    assert job_id("https://a/1") == job_id("https://a/1") != job_id("https://a/2")
    assert len(job_id("x")) == 12


def test_greenhouse(web):
    web.add(r"boards/acme/jobs/123$", {"content": "&lt;p&gt;Lead AI.&lt;/p&gt;", "location": {"name": "NYC"}})
    assert describe.describe({"ats": "greenhouse", "slug": "acme"}, "https://acme.com/careers?gh_jid=123") == ("Lead AI.", "NYC")
    assert describe.describe({"ats": "greenhouse", "slug": "acme"}, "https://job-boards.greenhouse.io/acme/jobs/123")[0] == "Lead AI."


def test_lever(web):
    web.add(r"api\.lever\.co/v0/postings/acme/abc$", {
        "descriptionPlain": "Intro", "lists": [{"text": "You will", "content": "<li>Lead</li>"}],
        "additionalPlain": "Pay $200k", "categories": {"location": "Remote"}})
    body, loc = describe.describe({"ats": "lever", "slug": "acme"}, "https://jobs.lever.co/acme/abc/")
    assert body == "Intro\n\nYou will\nLead\n\nPay $200k" and loc == "Remote"


def test_ashby_finds_the_posting_or_says_it_is_gone(web):
    web.add(r"job-board/acme$", {"jobs": [{"jobUrl": "https://jobs.ashbyhq.com/acme/1", "descriptionHtml": "<p>Hi</p>",
                                           "location": "NYC"}]})
    assert describe.describe({"ats": "ashby", "slug": "acme"}, "https://jobs.ashbyhq.com/acme/1") == ("Hi", "NYC")
    with pytest.raises(LookupError):
        describe.describe({"ats": "ashby", "slug": "acme"}, "https://jobs.ashbyhq.com/acme/2")


def test_workday_lists_every_location(web):
    web.add(r"acme\.wd5\.myworkdayjobs\.com/wday/cxs/acme/Careers/job/NY/Head_R1$", {"jobPostingInfo": {
        "jobDescription": "<p>Lead</p>", "location": "New York", "additionalLocations": ["Titusville, NJ"]}})
    url = "https://acme.wd5.myworkdayjobs.com/Careers/job/NY/Head_R1"
    assert describe.describe({"ats": "workday", "slug": "acme.wd5/acme/Careers"}, url) == ("Lead", "New York; Titusville, NJ")


def test_oracle(web):
    web.add(r"recruitingCEJobRequisitionDetails", lambda url, body: {"items": [{
        "ExternalDescriptionStr": "<p>About</p>", "ExternalQualificationsStr": "<p>PhD</p>", "PrimaryLocation": "NYC"}]}
        if 'Id="77"' in url.replace("%22", '"') else AssertionError(url))
    assert describe.describe({"ats": "oracle", "slug": "host.fa.us2/CX"}, "https://host/job/77") == ("About\n\nPhD", "NYC")


def test_workable(web):
    web.add(r"api/v2/accounts/acme/jobs/AAA$", {"description": "<p>A</p>", "requirements": "<p>B</p>",
                                                "location": {"city": "New York", "region": "NY"}})
    assert describe.describe({"ats": "workable", "slug": "acme"}, "https://apply.workable.com/acme/j/AAA/") == ("A\n\nB", "New York, NY")


def test_portfolio_jobs_use_the_link_or_the_page(web):
    web.add(r"boards/acme/jobs/9$", {"content": "Direct", "location": {"name": "NYC"}})
    getro = {"ats": "getro", "slug": "jobs.fund.com"}
    assert describe.describe(getro, "https://job-boards.greenhouse.io/acme/jobs/9?utm=getro")[0] == "Direct"
    web.add(r"https://acme\.com/careers/9$", "<html><nav>Menu</nav><script>x()</script><p>The job</p></html>")
    assert describe.describe(None, "https://acme.com/careers/9#frag") == ("The job", "")


def test_unknown_system():
    with pytest.raises(ValueError):
        describe.describe({"ats": "nope", "slug": "x"}, "https://x")


def test_run_downloads_new_descriptions_only(home, web, capsys):
    (home.data / "boards.json").write_text(json.dumps({"Lab Co": {"ats": "greenhouse", "slug": "labco"}}))
    with open(home.data / "jobs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["company", "title", "url"])
        w.writeheader()
        w.writerows([{"company": "Lab Co", "title": "A", "url": "https://gh/labco/jobs/1"},
                     {"company": "Lab Co", "title": "B", "url": "https://gh/labco/jobs/2"},
                     {"company": "Lab Co", "title": "C", "url": "https://gh/labco/jobs/3"}])
    out = home.data / "descriptions"
    out.mkdir()
    (out / f"{job_id('https://gh/labco/jobs/3')}.txt").write_text("already here")
    web.add(r"boards/labco/jobs/1$", {"content": "Body A", "location": {"name": "NYC"}})
    web.add(r"boards/labco/jobs/2$", OSError("gone"))
    describe.run(home)
    saved = (out / f"{job_id('https://gh/labco/jobs/1')}.txt").read_text()
    assert saved.startswith("Company: Lab Co\nTitle: A\nLocations: NYC\nURL: https://gh/labco/jobs/1\n\nBody A")
    assert not (out / f"{job_id('https://gh/labco/jobs/2')}.txt").exists()
    assert "!! Lab Co | B: gone" in capsys.readouterr().out
    assert len(web.requests) == 2   # the third was already downloaded
