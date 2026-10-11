import json

import pytest

from job_radar import discover, findboard


@pytest.fixture
def boards_with_jobs(monkeypatch):
    """Pretend these (ats, slug) boards exist with this many open jobs; every other guess has none."""
    def make(known):
        seen = []

        def count(ats, slug):
            seen.append((ats, slug))
            return known.get((ats, slug), 0)
        monkeypatch.setattr(discover, "count", count)
        monkeypatch.setattr(findboard, "count", count)
        return seen
    return make


def test_count_reads_any_board_shape(web):
    web.add(r"greenhouse\.io/v1/boards/a/jobs", {"jobs": [1, 2, 3]})
    web.add(r"api\.lever\.co/v0/postings/a", [1, 2])
    web.add(r"job-board/missing", OSError("404"))
    assert discover.count("greenhouse", "a") == 3
    assert discover.count("lever", "a") == 2
    assert discover.count("ashby", "missing") == 0


def test_guess_picks_the_biggest_board_and_skips_wrong_ones(boards_with_jobs):
    tried = boards_with_jobs({("lever", "example"): 4, ("ashby", "example"): 50, ("greenhouse", "examplehealth"): 9})
    assert discover.guess("Example Health", ["eh"], {("ashby", "example")}) == \
        {"ats": "greenhouse", "slug": "examplehealth", "open_jobs": 9}
    assert ("ashby", "example") not in tried and ("lever", "eh") in tried
    assert discover.guess("Nobody", [], set()) is None


def test_run_writes_known_portfolio_and_found_boards(home, boards_with_jobs, monkeypatch, capsys):
    boards_with_jobs({("greenhouse", "examplehealth"): 12})
    monkeypatch.setitem(discover.FETCH, "getro", lambda host, searches: iter([
        ("Head of AI", "NYC", "https://job-boards.greenhouse.io/acmebio/jobs/1", "", "Acme Bio", "Biotech"),
        ("Head of AI", "NYC", "https://jobs.lever.co/payco/1", "", "PayCo", "Fintech"),
        ("Lead", "NYC", "https://jobs.lever.co/mis/1", "", "Mislabelled Co", "Healthcare"),
        ("Lead", "NYC", "https://acme.example/careers", "", "No Board Health", "Healthcare")]))
    (home.profile / "companies.yaml").write_text(
        (home.profile / "companies.yaml").read_text().replace("harvest_portfolio", "x") + "\nharvest_portfolio: true\n")
    found = discover.run(home)
    saved = json.loads((home.data / "boards.json").read_text())
    assert saved == found
    assert found["Lab Co"] == {"ats": "greenhouse", "slug": "labco"}
    assert found["Some Ventures portfolio"] == {"ats": "getro", "slug": "jobs.someventures.com"}
    assert found["Example Health"]["slug"] == "examplehealth"
    assert found["Schmidt Sciences"]["ats"] == "lever"                       # from the pack
    assert found["Acme Bio"] == {"ats": "greenhouse", "slug": "acmebio", "found_via": "Some Ventures portfolio"}
    assert "PayCo" not in found and "Mislabelled Co" not in found and "No Board Health" not in found
    assert "1 companies added from portfolio boards" in capsys.readouterr().out


def test_unfound_employers_are_listed(home, boards_with_jobs, capsys):
    boards_with_jobs({})
    found = discover.run(home)
    assert "Example Health" not in found
    assert "No board found (add one under `boards:` if you know it): Example Health" in capsys.readouterr().out


def test_find_board_by_name_and_careers_page(boards_with_jobs, web, capsys):
    boards_with_jobs({("lever", "acme"): 3, ("greenhouse", "acme-labs"): 20})
    web.add(r"https://acme\.example/careers$", '<a href="https://boards.greenhouse.io/acme-labs">Jobs</a>'
                                               '<a href="https://apply.workable.com/acme-eu/">EU</a>'
                                               '<a href="https://acme.wd1.myworkdayjobs.com/en-US/Ext/job/1">x</a>')
    hits = findboard.run("Acme", "https://acme.example/careers")
    assert [(h["ats"], h["slug"]) for h in hits] == [("greenhouse", "acme-labs"), ("lever", "acme"),
                                                     ("workable", "acme-eu"), ("workday", "acme.wd1/acme/Ext")]
    out = capsys.readouterr().out
    assert '  Acme: {ats: greenhouse, slug: "acme-labs"}  # 20 open jobs' in out and "# check by hand" in out


def test_find_board_reports_nothing(boards_with_jobs, web, capsys):
    boards_with_jobs({})
    web.add(r"acme\.example", OSError("down"))
    assert findboard.run("Acme", "https://acme.example/careers") == []
    out = capsys.readouterr().out
    assert "could not read" in out and "No board found for Acme" in out


def test_harvest_survives_a_broken_portfolio_board(home, boards_with_jobs, monkeypatch, capsys):
    boards_with_jobs({})

    def broken(host, searches):
        raise OSError("timed out")
        yield
    monkeypatch.setitem(discover.FETCH, "getro", broken)
    (home.profile / "companies.yaml").write_text((home.profile / "companies.yaml").read_text() + "\nharvest_portfolio: true\n")
    found = discover.run(home)
    assert "Some Ventures portfolio" in found and "!! Some Ventures portfolio: timed out" in capsys.readouterr().out
