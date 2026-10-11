"""Each board reader against canned responses shaped like the real APIs."""
import re

import pytest

from job_radar import fetchers


def test_greenhouse(web):
    web.add(r"boards-api\.greenhouse\.io/v1/boards/acme/jobs$", {"jobs": [
        {"title": "Head of AI", "location": {"name": "New York, NY"}, "absolute_url": "https://gh/1",
         "first_published": "2026-10-01T12:00:00-04:00"},
        {"title": "No dates", "location": None, "absolute_url": "https://gh/2", "updated_at": "2026-09-30T00:00:00Z"}]})
    assert list(fetchers.greenhouse("acme")) == [
        ("Head of AI", "New York, NY", "https://gh/1", "2026-10-01"), ("No dates", "", "https://gh/2", "2026-09-30")]


def test_lever(web):
    web.add(r"api\.lever\.co/v0/postings/acme\?mode=json", [
        {"text": "Director, AI", "categories": {"location": "Remote"}, "workplaceType": "remote",
         "hostedUrl": "https://lever/1", "createdAt": 1759320000000},
        {"text": "Lead", "categories": {}, "hostedUrl": "https://lever/2", "createdAt": 1759320000000}])
    jobs = list(fetchers.lever("acme"))
    assert jobs[0][:3] == ("Director, AI", "Remote, remote", "https://lever/1")
    assert re.fullmatch(r"2025-10-0\d", jobs[0][3])
    assert jobs[1][1] == ""


def test_ashby_uses_address_and_remote_flag(web):
    web.add(r"api\.ashbyhq\.com/posting-api/job-board/acme", {"jobs": [
        {"title": "Head of AI", "location": "HQ", "address": {"postalAddress": {"addressLocality": "New York",
                                                                                 "addressRegion": "NY"}},
         "workplaceType": "Remote", "jobUrl": "https://ashby/1", "publishedAt": "2026-10-02T00:00:00Z"},
        {"title": "B", "jobUrl": "https://ashby/2"}]})
    assert list(fetchers.ashby("acme")) == [
        ("Head of AI", "HQ, New York, NY (Remote)", "https://ashby/1", "2026-10-02"), ("B", "", "https://ashby/2", "")]


def test_workday_searches_pages_and_dedupes(web):
    def answer(url, body):
        assert url == "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/Careers/jobs"
        if body["searchText"] == "machine learning":
            if body["offset"] == 0:
                return {"jobPostings": [{"title": f"Job {i}", "locationsText": "New York", "externalPath": f"/job/{i}",
                                         "postedOn": "Posted Today"} for i in range(20)]}
            return {"jobPostings": [{"title": "Last", "externalPath": "/job/last"}]}
        return {"jobPostings": [{"title": "Job 0", "externalPath": "/job/0"}, {"title": "No path"}]}   # a repeat
    web.add(r"myworkdayjobs\.com/wday/cxs", answer, method="POST")
    jobs = list(fetchers.workday("acme.wd5/acme/Careers", ["machine learning", "AI"]))
    assert len(jobs) == 21
    assert jobs[0] == ("Job 0", "New York", "https://acme.wd5.myworkdayjobs.com/Careers/job/0", "Posted Today")
    assert jobs[-1] == ("Last", "", "https://acme.wd5.myworkdayjobs.com/Careers/job/last", "")
    assert [b["offset"] for _, _, b, _ in web.requests] == [0, 20, 0]


def test_workday_without_searches_reads_nothing(web):
    assert list(fetchers.workday("acme.wd5/acme/Careers", [])) == []


def test_oracle(web):
    def answer(url, body):
        assert "siteNumber=CX" in url and 'keyword="machine learning"' in url.replace("%22", '"').replace("%20", " ")
        return {"items": [{"requisitionList": [{"Id": "77", "Title": "AI Director", "PrimaryLocation": "New York, NY",
                                                "PostedDate": "2026-10-01T00:00:00+00:00"}]}]}
    web.add(r"oraclecloud\.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions\?", answer)
    assert list(fetchers.oracle("host.fa.us2/CX", ["machine learning"])) == [
        ("AI Director", "New York, NY", "https://host.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX/job/77",
         "2026-10-01")]


def test_oracle_empty_items(web):
    web.add(r"oraclecloud\.com", {"items": []})
    assert list(fetchers.oracle("host.fa.us2/CX", ["x"])) == []


def test_workable_follows_pages(web):
    def answer(url, body):
        if "token" not in body:
            return {"results": [{"title": "A", "location": {"city": "New York", "region": "NY"}, "remote": True,
                                 "shortcode": "AAA", "published": "2026-10-01T00:00:00Z"}], "nextPage": "t2"}
        assert body["token"] == "t2"
        return {"results": [{"title": "B", "shortcode": "BBB"}]}
    web.add(r"apply\.workable\.com/api/v3/accounts/acme/jobs", answer, method="POST")
    assert list(fetchers.workable("acme")) == [
        ("A", "New York, NY, Remote", "https://apply.workable.com/acme/j/AAA", "2026-10-01"),
        ("B", "", "https://apply.workable.com/acme/j/BBB", "")]


def test_getro(web):
    web.add(r"https://jobs\.fund\.com/jobs$",
            '<html><script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"network":{"id":42}}}}</script>')

    def answer(url, body):
        assert url.endswith("/collections/42/search/jobs")
        if body["query"] == "AI" and body["page"] == 0:
            return {"results": {"jobs": [
                {"url": "https://x/1", "title": "Head of AI", "searchable_locations": ["New York", "Boston"],
                 "work_mode": "remote", "created_at": 1759320000,
                 "organization": {"name": "Acme Health", "industry_tags": ["Healthcare", "AI"]}}]}}
        return {"results": {"jobs": [{"url": "https://x/1", "title": "dup", "created_at": 0}]}}
    web.add(r"api\.getro\.com", answer, method="POST")
    jobs = list(fetchers.getro("jobs.fund.com", ["AI", "product"]))
    assert len(jobs) == 1
    title, loc, url, posted, company, tags = jobs[0]
    assert (title, loc, url, company, tags) == ("Head of AI", "New York; Boston (Remote)", "https://x/1", "Acme Health",
                                                "Healthcare AI")


def test_consider_pages_with_sequence(web):
    web.add(r"https://jobs\.fund\.com/jobs$", 'x "csrfToken":"tok" y "fixedBoard":"board1" z')
    calls = []

    def answer(url, body):
        calls.append(body["meta"])
        if "sequence" not in body["meta"]:
            jobs = [{"title": f"J{i}", "locations": ["NYC"], "remote": i == 0, "url": f"https://c/{i}",
                     "applyUrl": None, "timeStamp": "2026-10-01T00:00:00Z", "companyName": "Acme",
                     "markets": [{"label": "Biotech"}]} for i in range(500)]
            return {"jobs": jobs, "meta": {"sequence": "s2"}}
        return {"jobs": [{"title": "Last", "url": "https://c/last", "applyUrl": "https://apply/last"}], "meta": {}}
    web.add(r"jobs\.fund\.com/api-boards/search-jobs", answer, method="POST")
    jobs = list(fetchers.consider("jobs.fund.com"))
    assert len(jobs) == 501
    assert jobs[0] == ("J0", "NYC (Remote)", "https://c/0", "2026-10-01", "Acme", "Biotech")
    assert jobs[-1][2] == "https://apply/last"
    assert calls == [{"size": 500}, {"size": 500, "sequence": "s2"}]
    assert web.requests[1][3]["X-csrf-token"] == "tok"


def test_arpah(web):
    web.add(r"arpa-h\.gov/careers$", "<h2>Intro</h2> Open Positions <h3>ARPA-H Deputy <b>Director</b></h3>"
                                     "<h3> </h3><h4>Chief of Staff</h4> Program Managers <h3>Ignored</h3>")
    assert list(fetchers.arpah()) == [
        ("Deputy Director", "", "https://arpa-h.gov/careers#ARPA-H%20Deputy%20Director", ""),
        ("Chief of Staff", "", "https://arpa-h.gov/careers#Chief%20of%20Staff", ""),
        ("Program Manager (standing application)", "", "https://arpa-h.gov/careers/program-managers", "")]


def test_every_reader_is_registered():
    assert set(fetchers.FETCH) == {"greenhouse", "lever", "ashby", "workday", "oracle", "workable", "getro",
                                   "consider", "arpah"}
    assert fetchers.PORTFOLIO <= set(fetchers.FETCH) and fetchers.SEARCHED <= set(fetchers.FETCH)


def test_errors_propagate(web):
    web.add(r"greenhouse", OSError("timed out"))
    with pytest.raises(OSError):
        list(fetchers.greenhouse("acme"))
