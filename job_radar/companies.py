"""Which employers and job boards to read: profile/companies.yaml plus any packs it includes.

companies.yaml (and every pack in job_radar/packs/) has the same sections, all optional:

  packs: [health-life-sciences, venture]    # only in companies.yaml: packs to include
  find_boards:                              # employers whose board is found by guessing its name
    Example Health: [examplehealth]         #   (extra guesses for the board's short name, may be empty)
  boards:                                   # boards already known
    Example Bio: {ats: greenhouse, slug: examplebio}
    Big Pharma: {ats: workday, slug: host.wd1/tenant/Site}
    A Foundation: {ats: lever, slug: afoundation, funder: true}   # an investor or funder (see rules.yaml)
    Hospital: {ats: oracle, slug: host.fa.us2/CX, location: "New York, NY"}   # adds to vague locations
  portfolio_boards:                         # a venture firm's board of jobs at its portfolio companies
    Some Ventures: {ats: getro, host: jobs.someventures.com}
  harvest_portfolio: true                   # also read the own boards of in-domain portfolio companies
  not_in_domain: [Mislabelled Co]           # portfolio companies to skip even if their tags match
  wrong_slugs: [ashby/genesis]              # name guesses known to belong to a different company
  exclude: [Some Pack Company]              # only in companies.yaml: drop an employer a pack brings in

Job systems (`ats`): greenhouse, lever, ashby, workday, oracle, workable, arpah; portfolio boards: getro, consider.
Later entries win: packs in the order listed, then companies.yaml itself.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

PACKS = Path(__file__).parent / "packs"


def available_packs() -> dict[str, str]:
    """{pack name: its one-line description}."""
    out = {}
    for p in sorted(PACKS.glob("*.yaml")):
        out[p.stem] = (yaml.safe_load(p.read_text()) or {}).get("description", "")
    return out


@dataclass
class Companies:
    find_boards: dict[str, list[str]] = field(default_factory=dict)
    boards: dict[str, dict] = field(default_factory=dict)
    portfolio_boards: dict[str, dict] = field(default_factory=dict)
    harvest_portfolio: bool = False
    not_in_domain: set[str] = field(default_factory=set)
    wrong_slugs: set[tuple[str, str]] = field(default_factory=set)

    @property
    def funders(self) -> set[str]:
        return {name for name, b in self.boards.items() if b.get("funder")}

    def add(self, cfg: dict) -> None:
        for name, guesses in (cfg.get("find_boards") or {}).items():
            self.find_boards[name] = list(guesses or [])
        for name, b in (cfg.get("boards") or {}).items():
            self.boards[name] = dict(b)
        for name, b in (cfg.get("portfolio_boards") or {}).items():
            self.portfolio_boards[name] = dict(b)
        if "harvest_portfolio" in cfg:
            self.harvest_portfolio = bool(cfg["harvest_portfolio"])
        self.not_in_domain |= set(cfg.get("not_in_domain") or [])
        self.wrong_slugs |= {tuple(s.split("/", 1)) for s in cfg.get("wrong_slugs") or []}

    @classmethod
    def load(cls, cfg: dict, packs_dir: Path = PACKS) -> "Companies":
        c = cls()
        for name in cfg.get("packs") or []:
            path = packs_dir / f"{name}.yaml"
            if not path.exists():
                raise FileNotFoundError(f"companies.yaml: no pack named {name!r} (have: {', '.join(available_packs())})")
            c.add(yaml.safe_load(path.read_text()) or {})
        c.add(cfg)
        for name in cfg.get("exclude") or []:
            c.find_boards.pop(name, None)
            c.boards.pop(name, None)
            c.portfolio_boards.pop(name, None)
        return c
