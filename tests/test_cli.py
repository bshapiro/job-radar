import json
import subprocess
import sys
from pathlib import Path

import pytest

from job_radar import __version__, cli, setup
from job_radar.home import Home

ROOT = Path(__file__).parents[1]


def run(*args):
    return cli.main([str(a) for a in args])


def test_version(capsys):
    with pytest.raises(SystemExit):
        run("--version")
    assert __version__ in capsys.readouterr().out


def test_module_entry_point():
    out = subprocess.run([sys.executable, "-m", "job_radar", "packs"], capture_output=True, text=True)
    assert out.returncode == 0 and "science-funders" in out.stdout


def test_packs(capsys):
    assert run("packs") == 0
    assert "venture" in capsys.readouterr().out


def test_home_from_option_and_environment(home, monkeypatch, tmp_path):
    assert Home(home.root).profile == home.root / "profile"
    monkeypatch.setenv("JOB_RADAR_HOME", str(home.root))
    assert Home().root == home.root
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("JOB_RADAR_HOME")
    assert Home().root == tmp_path.resolve()


def test_missing_files_are_empty(tmp_path):
    h = Home(tmp_path)
    assert h.settings == {} and h.preferences() == "" and h.companies.boards == {}


def test_each_command_calls_its_step(home, monkeypatch):
    called = []
    from job_radar import describe, digest, discover, findboard, linkedin, notify, review, scrape, tracker
    for mod, fn in [(discover, "run"), (scrape, "run"), (scrape, "compare"), (describe, "run"), (review, "run"),
                    (review, "recheck"), (tracker, "run"), (digest, "run"), (notify, "run"), (linkedin, "run"),
                    (findboard, "run")]:
        monkeypatch.setattr(mod, fn, lambda *a, _n=f"{mod.__name__.split('.')[-1]}.{fn}", **k: called.append((_n, a[1:], k)))
    h = ["--home", home.root]
    run(*h, "discover")
    run(*h, "scrape", "--save-raw", "r.json")
    run(*h, "scrape", "--from-raw", "r.json", "--compare")
    run(*h, "describe")
    run(*h, "review", "--limit", "3", "--model", "m", "--effort", "high")
    run(*h, "recheck", "10")
    run(*h, "track", "--weekly")
    run(*h, "digest", "--test")
    run(*h, "notify")
    run(*h, "import-linkedin", "export.zip")
    run(*h, "find-board", "Acme", "https://acme.example/careers")
    names = [c[0] for c in called]
    assert names == ["discover.run", "scrape.run", "scrape.compare", "describe.run", "review.run", "review.recheck",
                     "tracker.run", "digest.run", "notify.run", "linkedin.run", "findboard.run"]
    assert called[1][2] == {"raw_in": None, "raw_out": Path("r.json")}
    assert called[4][2] == {"dry_run": False, "limit": 3, "model": "m", "effort": "high"}
    assert called[5][1] == (10,) and called[6][2] == {"weekly": True} and called[7][2] == {"test": True}
    assert called[10][0] == "findboard.run"


def test_daily_runs_the_steps_in_order(home, monkeypatch):
    called = []
    from job_radar import describe, digest, discover, review, scrape, tracker
    for mod in (discover, scrape, describe, review, tracker, digest):
        monkeypatch.setattr(mod, "run", lambda *a, _n=mod.__name__.split(".")[-1], **k: called.append(_n))
    (home.data / "boards.json").write_text("{}")
    (home.profile / "settings.yaml").write_text("discover: {weekly_on: sunday}\n")
    import datetime as dt
    monkeypatch.setattr(cli, "date", type("D", (), {"today": staticmethod(lambda: dt.date(2026, 10, 14))}))
    run("--home", home.root, "daily")
    assert called == ["scrape", "describe", "review", "tracker", "digest"]
    called.clear()
    run("--home", home.root, "daily", "--discover")
    assert called[0] == "discover"
    called.clear()
    (home.data / "boards.json").unlink()                 # never discovered yet
    run("--home", home.root, "daily")
    assert called[0] == "discover"


def test_test_email(home, monkeypatch):
    called = []
    from job_radar import digest, notify
    monkeypatch.setattr(digest, "run", lambda h, test=False: called.append(("digest", test)))
    monkeypatch.setattr(notify, "run", lambda h: called.append(("notify",)))
    run("--home", home.root, "test-email")
    assert called == [("digest", True), ("notify",)]


def test_compare_needs_jobs_to_compare(home):
    with pytest.raises(SystemExit):
        run("--home", home.root, "scrape", "--compare")


def test_compare_with_save_raw_reads_boards_first(home, monkeypatch):
    from job_radar import scrape
    (home.data / "boards.json").write_text(json.dumps({"Lab Co": {"ats": "greenhouse", "slug": "labco"}}))
    monkeypatch.setitem(scrape.FETCH, "greenhouse", lambda slug, s=(): iter([("Head of AI", "NYC", "https://x", "")]))
    compared = []
    monkeypatch.setattr(scrape, "compare", lambda h, raw: compared.append(raw))
    run("--home", home.root, "scrape", "--save-raw", home.root / "raw.json", "--compare")
    assert compared == [home.root / "raw.json"] and (home.root / "raw.json").exists()
    assert not (home.data / "jobs.csv").exists()


def test_init_and_doctor_exit_codes(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "_secrets_on_github", lambda: None)
    assert run("init", tmp_path / "p") == 0
    assert run("--home", tmp_path / "p", "doctor") == 1        # preferences are still the template
    (tmp_path / "p" / "profile" / "preferences.md").write_text("# Mine\nAI product roles.\n")
    assert run("--home", tmp_path / "p", "doctor") == 0
