"""Where a person's files live. A profile repo has two folders:

  profile/   what they want: preferences.md, rules.yaml, companies.yaml, settings.yaml, review_prompt.md
  data/      what the engine writes: boards, matches, verdicts, applications, descriptions

The home is the current directory, or JOB_RADAR_HOME if set.
"""
from __future__ import annotations

import os
from functools import cached_property
from pathlib import Path

import yaml


class Home:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or os.environ.get("JOB_RADAR_HOME") or ".").resolve()
        self.profile = self.root / "profile"
        self.data = self.root / "data"

    def yaml(self, name: str, default=None):
        path = self.profile / name
        if not path.exists():
            return {} if default is None else default
        return yaml.safe_load(path.read_text()) or {}

    @cached_property
    def settings(self) -> dict:
        return self.yaml("settings.yaml")

    @cached_property
    def companies(self):
        from .companies import Companies
        return Companies.load(self.yaml("companies.yaml"))

    @cached_property
    def rules(self):
        from .rules import Rules
        return Rules(self.yaml("rules.yaml"), self.companies)

    def preferences(self) -> str:
        path = self.profile / "preferences.md"
        return path.read_text() if path.exists() else ""

    def review_prompt(self) -> str:
        path = self.profile / "review_prompt.md"
        if path.exists():
            return path.read_text().strip()
        return (Path(__file__).parent / "templates" / "profile" / "review_prompt.md").read_text().strip()
