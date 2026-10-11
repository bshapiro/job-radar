"""The whole scrape step with fake boards: reading, retries, files written, and --compare."""
import csv
import json

import pytest

from job_radar import scrape
from job_radar.scrape import Raw, fetch_all, fetch_board

BOARDS = {
    "Lab Co": {"ats": "greenhouse", "slug": "labco"},
    "Hospital": {"ats": "oracle", "slug": "host.fa.us2/CX", "location": "New York, NY"},
    "Some Ventures portfolio": {"ats": "getro", "slug": "jobs.someventures.com"},
    "Broken": {"ats": "lever", "slug": "broken"},
}


@pytest.fixture
def boards(home, monkeypatch):
    calls = {"broken": 0, "searches": {}}

    def greenhouse(slug, searches=()):
        yield "Director, Machine Learning", "New York, NY", "https://gh/1", "2026-10-01"
        yield "Machine Learning Engineer", "New York, NY", "https://gh/2", "2026-10-01"

    def oracle(slug, searches=()):
        calls["searches"]["oracle"] = list(searches)
        yield "Head of AI, Health", "United States", "https://or/1", ""

    def getro(slug, searches=()):
        calls["searches"]["getro"] = list(searches)
        yield "Head of AI", "NYC", "https://pf/1", "", "Acme Health", "Healthcare"
        yield "Head of AI", "NYC", "https://pf/2", "", "PayCo", "Fintech"
        yield "Director, Machine Learning", "NYC", "https://pf/3", "", "Lab Co", "Biotech"   # copy of gh/1

    def broken(slug, searches=()):
        calls["broken"] += 1
        raise OSError("cut off")
        yield

    for ats, f in {"greenhouse": greenhouse, "oracle": oracle, "getro": getro, "lever": broken}.items():
        monkeypatch.setitem(scrape.FETCH, ats, f)
    (home.data / "boards.json").write_text(json.dumps(BOARDS))
    return calls


def read(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def test_fetch_board_shapes_and_retries(home, boards, capsys):
    raw = Raw()
    assert fetch_board(home.rules, "Hospital", BOARDS["Hospital"], raw) == [
        ("Hospital", "Head of AI, Health", "United States; New York, NY", "https://or/1", "", "")]
    assert boards["searches"]["oracle"] == ["machine learning"]
    jobs = fetch_board(home.rules, "Some Ventures portfolio", BOARDS["Some Ventures portfolio"], raw)
    assert jobs[0] == ("Acme Health", "Head of AI", "NYC", "https://pf/1", "", "Some Ventures portfolio")
    assert boards["searches"]["getro"] == ["machine learning", "AI"]
    assert raw.outside_domain == {"PayCo"}
    assert fetch_board(home.rules, "Broken", BOARDS["Broken"], raw) == []
    assert boards["broken"] == 3 and raw.failed == ["Broken"]
    assert "!! Broken: cut off" in capsys.readouterr().out


def test_run_writes_every_file(home, boards):
    (home.data / "seen.json").write_text(json.dumps({"https://or/1": "2026-09-01"}))
    scrape.run(home, raw_out=home.root / "raw.json")
    jobs = read(home.data / "jobs.csv")
    assert [(j["company"], j["title"], j["new"]) for j in jobs] == [
        ("Hospital", "Head of AI, Health", ""), ("Acme Health", "Head of AI", "NEW"),
        ("Lab Co", "Director, Machine Learning", "NEW")]
    assert jobs[0]["first_seen"] == "2026-09-01" and jobs[1]["via"] == "Some Ventures portfolio"
    rejected = {(r["company"], r["reason"]) for r in read(home.data / "rejected.csv")}
    assert rejected == {("Lab Co", "hands-on engineering"), ("PayCo", "portfolio company outside health")}
    seen = json.loads((home.data / "seen.json").read_text())
    assert set(seen) == {"https://or/1", "https://pf/1", "https://gh/1"}
    run = json.loads((home.data / "run.json").read_text())
    assert (run["jobs"], run["boards"], run["matches"], run["failed_boards"]) == (6, 4, 3, ["Broken"])
    assert len(Raw.load(home.root / "raw.json").jobs) == 6


def test_seen_survives_a_job_dropping_out(home, boards):
    scrape.run(home)
    day2 = Raw(jobs=[("Acme Health", "Head of AI", "NYC", "https://pf/1", "", "Some Ventures portfolio")])
    day2.save(home.root / "day2.json")
    scrape.run(home, raw_in=home.root / "day2.json")        # Lab Co's board was empty for a day
    assert [j["url"] for j in read(home.data / "jobs.csv")] == ["https://pf/1"]
    day3 = Raw(jobs=[("Lab Co", "Director, Machine Learning", "New York, NY", "https://gh/1", "", "")])
    day3.save(home.root / "day3.json")
    scrape.run(home, raw_in=home.root / "day3.json")
    assert read(home.data / "jobs.csv")[0]["new"] == ""     # back again, but not announced as new


def test_reviews_carry_over(home, boards):
    with open(home.data / "reviews.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["url", "company", "title", "fit", "note", "reviewed"])
        w.writeheader()
        w.writerow(dict(url="https://old-link", company="Lab Co", title="Director, Machine Learning", fit="strong",
                        note="Great.", reviewed=""))
    scrape.run(home)
    jobs = read(home.data / "jobs.csv")
    assert jobs[0]["title"] == "Director, Machine Learning" and jobs[0]["fit"] == "strong"   # reviewed first


def test_compare_writes_nothing(home, boards, capsys):
    scrape.run(home, raw_out=home.root / "raw.json")
    before = {p.name: p.read_bytes() for p in home.data.iterdir() if p.is_file()}
    (home.profile / "rules.yaml").write_text((home.profile / "rules.yaml").read_text()
                                             .replace("words: [engineer, developer]", "words: [developer]"))
    home2 = type(home)(home.root)          # fresh, so the edited rules are read
    scrape.compare(home2, home.root / "raw.json")
    out = capsys.readouterr().out
    assert "3 matches now (3 in jobs.csv): 0 added, 0 dropped" in out
    assert "Machine Learning Engineer: hands-on engineering -> low score (4)" in out
    assert {p.name: p.read_bytes() for p in home.data.iterdir() if p.is_file()} == before


def test_fetch_all(home, boards):
    raw = fetch_all(home.rules, BOARDS)
    assert len(raw.jobs) == 6 and raw.failed == ["Broken"] and raw.outside_domain == {"PayCo"}


def test_location_lookup_failure_keeps_the_job(home, boards, monkeypatch, capsys):
    from job_radar import describe
    monkeypatch.setitem(scrape.FETCH, "greenhouse",
                        lambda slug, s=(): iter([("Head of AI, Health", "2 Locations", "https://gh/9", "")]))

    def fail(board, url):
        raise OSError("down")
    monkeypatch.setattr(describe, "describe", fail)
    scrape.run(home)
    assert "!! could not resolve location for Lab Co | Head of AI, Health: down" in capsys.readouterr().out
    assert any(j["url"] == "https://gh/9" for j in read(home.data / "jobs.csv"))


def test_compare_reports_dropped_jobs(home, boards, capsys):
    scrape.run(home, raw_out=home.root / "raw.json")
    (home.profile / "rules.yaml").write_text((home.profile / "rules.yaml").read_text().replace("min_score: 7", "min_score: 9"))
    scrape.compare(type(home)(home.root), home.root / "raw.json")
    out = capsys.readouterr().out
    assert "1 dropped" in out and "- Lab Co" in out and "(now: low score (8); fit was unread)" in out
