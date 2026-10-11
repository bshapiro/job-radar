"""init, doctor, the templates, the skills, the packs and the privacy check."""
import importlib.util
import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml

from job_radar import __version__, setup
from job_radar.companies import Companies, available_packs
from job_radar.home import Home
from job_radar.trim import trim

import sys

import job_radar

ROOT = Path(__file__).parents[1]
PACKAGE = Path(job_radar.__file__).parent   # the installed package, wherever it is


@pytest.fixture
def profile(tmp_path, monkeypatch):
    """A fresh profile that passes every check."""
    setup.init(tmp_path / "p")
    (tmp_path / "p" / "profile" / "preferences.md").write_text("# Mine\nAI product roles in health.\n")
    monkeypatch.setattr(setup, "_secrets_on_github", lambda: set(setup.SECRETS))
    return Home(tmp_path / "p")


def test_doctor_passes_a_good_profile(profile, capsys):
    (profile.data / "boards.json").write_text(json.dumps({"A": {}, "B": {}}))
    (profile.data / "run.json").write_text(json.dumps({"date": "2026-10-11", "jobs": 1234, "matches": 5,
                                                       "failed_boards": ["B"]}))
    assert setup.doctor(profile)
    out = capsys.readouterr().out
    assert "data/boards.json: 2 boards" in out and "1,234 jobs read" in out and "failed last run: B" in out
    assert "All good." in out


@pytest.mark.parametrize("change,message", [
    (lambda p: (p.profile / "rules.yaml").write_text("title: [unclosed"), "isn't valid YAML"),
    (lambda p: (p.profile / "rules.yaml").write_text("min_score: 7\n"), "nothing would ever match"),
    (lambda p: (p.profile / "companies.yaml").write_text("packs: [nope]\n"), "can't be read"),
    (lambda p: ((p.profile / "companies.yaml").write_text("harvest_portfolio: true\n"),
                (p.profile / "rules.yaml").write_text("title: {topic: [ai]}\n")), "every portfolio company would be added"),
    (lambda p: ((p.profile / "companies.yaml").write_text("boards: {X: {ats: workday, slug: a/b/c}}\n"),
                (p.profile / "rules.yaml").write_text("title: {topic: [ai]}\n")), "searches.large_boards is empty"),
    (lambda p: (p.profile / "companies.yaml").write_text("boards: {X: {ats: taleo, slug: x}}\n"), "unknown job systems"),
    (lambda p: (p.root / ".github" / "workflows" / "daily.yml").unlink(), "daily.yml is missing"),
    (lambda p: (p.profile / "rules.yaml").unlink(), "profile/rules.yaml is missing"),
])
def test_doctor_finds_problems(profile, capsys, change, message):
    change(profile)
    assert not setup.doctor(Home(profile.root))
    assert message in capsys.readouterr().out


def test_doctor_reports_missing_secrets(profile, monkeypatch, capsys):
    monkeypatch.setattr(setup, "_secrets_on_github", lambda: {"ANTHROPIC_API_KEY"})
    assert not setup.doctor(profile)
    out = capsys.readouterr().out
    assert "gh secret set SMTP_PASSWORD" in out and "FIX   secret ANTHROPIC_API_KEY" not in out


def test_doctor_notes_a_different_engine_version(profile, capsys):
    wf = profile.root / ".github" / "workflows" / "daily.yml"
    wf.write_text(wf.read_text().replace(f"@v{__version__}", "@v0.9.0"))
    assert setup.doctor(profile)
    assert "pins a different engine version" in capsys.readouterr().out


def test_secrets_listing(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, '[{"name": "X"}]', ""))
    assert setup._secrets_on_github() == {"X"}
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "not logged in"))
    assert setup._secrets_on_github() is None

    def missing(*a, **k):
        raise FileNotFoundError("gh")
    monkeypatch.setattr(subprocess, "run", missing)
    assert setup._secrets_on_github() is None


def test_init_keeps_existing_files(tmp_path):
    (tmp_path / "p" / "profile").mkdir(parents=True)
    (tmp_path / "p" / "profile" / "rules.yaml").write_text("mine")
    setup.init(tmp_path / "p")
    assert (tmp_path / "p" / "profile" / "rules.yaml").read_text() == "mine"
    assert (tmp_path / "p" / ".claude" / "skills" / "job-radar-setup" / "SKILL.md").exists()


def test_workflow_template(profile):
    wf = yaml.safe_load((profile.root / ".github" / "workflows" / "daily.yml").read_text())
    on = wf[True] if True in wf else wf["on"]           # YAML reads a bare `on:` as true
    assert on["schedule"][0]["cron"] == "0 11 * * 1-5"
    assert set(on["workflow_dispatch"]["inputs"]) == {"recheck", "model", "effort", "test_email"}
    assert wf["env"]["JOB_RADAR"] == f"job-radar @ git+https://github.com/{setup.ENGINE_REPO}@v{__version__}"
    steps = {s.get("name", s.get("run", s.get("uses"))): s for s in wf["jobs"]["run"]["steps"]}
    assert "job-radar daily" in steps["Find jobs, review them, and update the tracker"]["run"]
    assert set(setup.SECRETS) <= {k for s in steps.values() for k in s.get("env", {})}
    assert "git pull --rebase" in steps["Commit updated data"]["run"]
    assert wf["permissions"] == {"contents": "write", "issues": "write"}


def test_skills_have_matching_names():
    skills = sorted((PACKAGE / "skills").glob("*/SKILL.md"))
    assert [s.parent.name for s in skills] == ["job-radar-review", "job-radar-setup", "job-radar-tune"]
    for s in skills:
        front = yaml.safe_load(s.read_text().split("---")[1])
        assert front["name"] == s.parent.name and len(front["description"]) > 50


def test_skills_and_readme_only_use_real_commands():
    help_text = subprocess.run([sys.executable, "-m", "job_radar", "--help"], capture_output=True, text=True).stdout
    real = set(re.findall(r"^    ([a-z][a-z-]+)(?:  |$)", help_text, re.M))
    docs = [*(PACKAGE / "skills").glob("*/SKILL.md"), ROOT / "README.md"]
    used = set(re.findall(r"`job-radar ([a-z][a-z-]*)", "".join(p.read_text() for p in docs)))
    assert used and used <= real, used - real


def test_packs_do_not_contradict_each_other():
    boards = {}
    for name in available_packs():
        for company, b in Companies.load({"packs": [name]}).boards.items():
            key = {k: v for k, v in b.items() if k != "funder"}
            assert boards.setdefault(company, key) == key, f"{company} differs between packs"


def test_trim_drops_boilerplate_but_keeps_facts():
    text = ("About the role\nLead the AI roadmap.\nWe are an equal opportunity employer.\n"
            "Base pay range: $180,000 - $220,000. We offer dental and vision insurance.\n"
            "5+ years of experience. Paid time off.\n\n\nHybrid, 3 days per week in New York.")
    assert trim(text) == ("About the role\nLead the AI roadmap.\nBase pay range: $180,000 - $220,000. We offer dental "
                          "and vision insurance.\n5+ years of experience. Paid time off.\n\nHybrid, 3 days per week in New York.")


def load_privacy_check():
    spec = importlib.util.spec_from_file_location("privacy_check", ROOT / "scripts" / "privacy_check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_privacy_check(tmp_path, monkeypatch, capsys):
    pc = load_privacy_check()
    repo = tmp_path / "repo"
    (repo / "pkg").mkdir(parents=True)
    (repo / "pkg" / "a.py").write_text("ok = 1\nowner = 'Jane Doe'\nurl = 'github.com/jdoe/thing'\n")
    (repo / "jane-doe-notes.txt").write_text("nothing")
    (repo / "binary.bin").write_bytes(b"\xff\xfe Jane")
    terms = tmp_path / "terms.txt"
    terms.write_text("# comment\nJane Doe\njdoe\nallow: github.com/jdoe/thing\n")
    monkeypatch.setattr(pc, "ROOT", repo)
    assert pc.main([str(terms)]) == 1
    out = capsys.readouterr().out
    assert "pkg/a.py:2: 'jane doe'" in out and "jdoe" not in out.split("hit(s)")[0].replace("Jane Doe", "")
    assert "1 hit(s)" in out
    terms.write_text("Jane\n")
    assert pc.main([str(terms)]) == 1
    assert "binary.bin" in capsys.readouterr().out
    terms.write_text("Nobody\n")
    assert pc.main([str(terms)]) == 0
    assert pc.main([]) == 2


def test_privacy_check_reads_history(tmp_path, monkeypatch, capsys):
    pc = load_privacy_check()
    repo = tmp_path / "repo"
    repo.mkdir()
    git = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)
    git("init", "-q")
    git("config", "user.name", "x")
    git("config", "user.email", "x@example.com")
    (repo / "f.txt").write_text("secret plan\n")
    git("add", ".")
    git("commit", "-qm", "first")
    (repo / "f.txt").write_text("clean\n")
    git("commit", "-qam", "second")
    (tmp_path / "t.txt").write_text("secret plan\n")
    monkeypatch.setattr(pc, "ROOT", repo)
    assert pc.main([str(tmp_path / "t.txt")]) == 1
    assert "git history" in capsys.readouterr().out
