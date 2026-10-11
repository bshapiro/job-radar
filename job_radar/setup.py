"""`job-radar init` (make a new profile repo) and `job-radar doctor` (check one and say what to fix)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import yaml

from . import __version__
from .home import Home

ENGINE_REPO = "bshapiro/job-radar"
HERE = Path(__file__).parent
TEMPLATES = HERE / "templates"
SKILLS = HERE / "skills"
SECRETS = {"ANTHROPIC_API_KEY": "reviews by Claude", "SMTP_USER": "the daily email",
           "SMTP_PASSWORD": "the daily email", "EMAIL_TO": "the daily email"}


def _copy_tree(src: Path, dst: Path, made: list, fill=None, dotted=()) -> None:
    """Copy src into dst without overwriting. Top-level names in `dotted` get a leading dot (templates are
    stored without one, since packaging leaves out hidden files)."""
    for f in sorted(src.rglob("*")):
        if f.is_dir() or "__pycache__" in f.parts:
            continue
        rel = f.relative_to(src)
        if rel.parts[0] in dotted:
            rel = Path("." + rel.parts[0], *rel.parts[1:])
        target = dst / rel
        if target.exists():
            continue   # never overwrite someone's own files
        target.parent.mkdir(parents=True, exist_ok=True)
        text = f.read_text()
        target.write_text(fill(text) if fill else text)
        made.append(target)


def init(folder: Path) -> list[Path]:
    folder = folder.resolve()
    made: list[Path] = []
    fill = lambda s: s.replace("{engine_repo}", ENGINE_REPO).replace("{version}", __version__)
    _copy_tree(TEMPLATES / "profile", folder / "profile", made)
    _copy_tree(TEMPLATES / "repo", folder, made, fill, dotted=("github", "gitignore"))
    _copy_tree(SKILLS, folder / ".claude" / "skills", made)
    (folder / "data").mkdir(exist_ok=True)
    for p in made:
        print(f"  created {p.relative_to(folder)}")
    print(f"\nProfile repo ready in {folder}. Next: open Claude Code there and run /job-radar-setup.")
    return made


class Report:
    def __init__(self):
        self.problems = 0

    def ok(self, msg):
        print(f"  ok    {msg}")

    def warn(self, msg):
        print(f"  check {msg}")

    def bad(self, msg):
        print(f"  FIX   {msg}")
        self.problems += 1


def _secrets_on_github() -> set[str] | None:
    """Names of the repo's Actions secrets, or None if gh can't tell."""
    try:
        out = subprocess.run(["gh", "secret", "list", "--json", "name"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode:
        return None
    return {s["name"] for s in json.loads(out.stdout or "[]")}


def doctor(home: Home) -> bool:
    r = Report()
    print(f"job-radar {__version__}, profile in {home.root}\n")

    print("Profile")
    for name in ("preferences.md", "rules.yaml", "companies.yaml"):
        if (home.profile / name).exists():
            r.ok(f"profile/{name}")
        else:
            r.bad(f"profile/{name} is missing (job-radar init makes it)")
    template = (TEMPLATES / "profile" / "preferences.md").read_text()
    if home.preferences().strip() == template.strip():
        r.bad("preferences.md is still the template: run /job-radar-setup, or fill it in")
    for name in ("rules.yaml", "companies.yaml", "settings.yaml"):
        try:
            home.yaml(name)
        except yaml.YAMLError as e:
            r.bad(f"{name} isn't valid YAML: {e}")
            return False
    try:
        rules, comp = home.rules, home.companies
        r.ok(f"rules.yaml: {len(rules.exclusions)} exclude rules, {len(rules.boosts)} boosts, min_score {rules.min_score}")
        r.ok(f"companies.yaml: {len(comp.boards)} known boards, {len(comp.find_boards)} to find by name, "
             f"{len(comp.portfolio_boards)} portfolio boards, {len(comp.funders)} funders")
    except Exception as e:
        r.bad(f"rules or companies can't be read: {e}")
        return False
    if rules.topic is None and rules.also_relevant is None:
        r.bad("rules.yaml has no title.topic or title.also_relevant: nothing would ever match")
    if comp.harvest_portfolio and rules.domain is None:
        r.bad("harvest_portfolio is on but rules.yaml has no domain.tags: every portfolio company would be added")
    if (comp.portfolio_boards or any(b["ats"] in ("workday", "oracle") for b in comp.boards.values())) and not rules.searches:
        r.bad("large boards (Workday, Oracle, portfolio boards) are listed but searches.large_boards is empty")
    unknown = {b["ats"] for b in comp.boards.values()} - {"greenhouse", "lever", "ashby", "workday", "oracle", "workable", "arpah"}
    if unknown:
        r.bad(f"unknown job systems in companies.yaml: {', '.join(sorted(unknown))}")

    print("\nData")
    boards = home.data / "boards.json"
    if boards.exists():
        r.ok(f"data/boards.json: {len(json.loads(boards.read_text()))} boards")
    else:
        r.warn("no data/boards.json yet: run job-radar discover")
    run = home.data / "run.json"
    if run.exists():
        d = json.loads(run.read_text())
        r.ok(f"last run {d['date']}: {d['jobs']:,} jobs read, {d['matches']} matches")
        if d.get("failed_boards"):
            r.warn(f"boards that failed last run: {', '.join(d['failed_boards'])}")

    print("\nGitHub")
    wf = home.root / ".github" / "workflows" / "daily.yml"
    if not wf.exists():
        r.bad(".github/workflows/daily.yml is missing (job-radar init makes it)")
    else:
        text = wf.read_text()
        if f"@v{__version__}" not in text:
            r.warn(f"the workflow pins a different engine version from the one installed here ({__version__})")
        else:
            r.ok(f"workflow runs job-radar {__version__}")
    secrets = _secrets_on_github()
    if secrets is None:
        r.warn("couldn't list the repo's secrets (needs the gh command, logged in, inside the repo)")
    else:
        for name, purpose in SECRETS.items():
            if name in secrets:
                r.ok(f"secret {name} ({purpose})")
            else:
                r.bad(f"secret {name} ({purpose}) is not set: run  gh secret set {name}  in your own terminal")

    print("\nThis machine")
    if os.environ.get("ANTHROPIC_API_KEY"):
        r.ok("ANTHROPIC_API_KEY is set")
    else:
        r.warn("ANTHROPIC_API_KEY isn't set here (only needed to run reviews on this machine)")
    if shutil.which("gh"):
        r.ok("gh command found")
    else:
        r.warn("gh command not found (needed to set secrets and to use the tracker from this machine)")

    print(f"\n{'All good.' if not r.problems else f'{r.problems} thing(s) to fix.'}")
    return not r.problems
