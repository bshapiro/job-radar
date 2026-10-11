"""The `job-radar` command. Run it from a profile repo (or set JOB_RADAR_HOME)."""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from . import __version__
from .home import Home


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="job-radar", description="Find jobs worth applying to on public job boards.")
    p.add_argument("--version", action="version", version=f"job-radar {__version__}")
    p.add_argument("--home", help="profile repo folder (default: JOB_RADAR_HOME or the current folder)")
    sub = p.add_subparsers(dest="command", required=True, metavar="command")

    def cmd(name, help):
        return sub.add_parser(name, help=help, description=help)

    cmd("discover", "work out each employer's job board -> data/boards.json")
    s = cmd("scrape", "read every board and score each title -> data/jobs.csv, data/rejected.csv")
    s.add_argument("--save-raw", type=Path, help="also save every job read, for re-scoring later")
    s.add_argument("--from-raw", type=Path, help="score jobs saved with --save-raw instead of reading the boards")
    s.add_argument("--compare", action="store_true",
                   help="print how matches would change under the current rules, writing nothing in data/ "
                        "(with --from-raw, or with --save-raw to read the boards first)")
    cmd("describe", "download full descriptions of the matches -> data/descriptions/")
    s = cmd("review", "have Claude read new matches' descriptions and give a verdict")
    s.add_argument("--dry-run", action="store_true", help="print the prompt for the first job and stop")
    s.add_argument("--limit", type=int, help="most jobs to review in one run (default: settings.yaml, else 25)")
    s.add_argument("--model")
    s.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"])
    s = cmd("recheck", "re-review N hand-reviewed jobs and report how often Claude agrees (saves nothing)")
    s.add_argument("n", type=int)
    s.add_argument("--model")
    s.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"])
    s = cmd("track", "read Applied / Not interested ticks from GitHub issues and open today's issues")
    s.add_argument("--weekly", action="store_true", help="open the weekly reminder issue today")
    s = cmd("digest", "write the daily email (digest.md, digest.html)")
    s.add_argument("--test", action="store_true", help="list the current strong matches instead of new ones")
    cmd("notify", "send the digest by email (or a GitHub issue without SMTP settings)")
    s = cmd("daily", "the whole daily run: discover (weekly), scrape, describe, review, track, digest")
    s.add_argument("--discover", action="store_true", help="rediscover boards even if it isn't the day for it")
    cmd("test-email", "email the current strong matches, to check that email arrives")
    s = cmd("import-linkedin", "import saved and applied jobs from a LinkedIn data export -> data/seed_jobs.csv")
    s.add_argument("export", help="the export .zip, or its unzipped folder")
    s = cmd("find-board", "find an employer's job board, to add to companies.yaml")
    s.add_argument("name")
    s.add_argument("careers_page", nargs="?", help="the employer's careers page, if the name alone finds nothing")
    cmd("packs", "list the company packs that companies.yaml can include")
    s = cmd("init", "create a new profile repo from the templates")
    s.add_argument("folder", nargs="?", default=".")
    cmd("doctor", "check the profile, boards and secrets, and say what to fix")

    a = p.parse_args(argv)
    home = Home(a.home)

    if a.command == "discover":
        from . import discover
        discover.run(home)
    elif a.command == "scrape":
        from . import scrape
        if a.compare:   # writes nothing in data/
            raw = a.from_raw
            if not raw:
                if not a.save_raw:
                    p.error("--compare needs --from-raw, or --save-raw to read the boards first")
                import json
                scrape.fetch_all(home.rules, json.loads((home.data / "boards.json").read_text())).save(a.save_raw)
                raw = a.save_raw
            scrape.compare(home, raw)
        else:
            scrape.run(home, raw_in=a.from_raw, raw_out=a.save_raw)
    elif a.command == "describe":
        from . import describe
        describe.run(home)
    elif a.command == "review":
        from . import review
        review.run(home, dry_run=a.dry_run, limit=a.limit, model=a.model, effort=a.effort)
    elif a.command == "recheck":
        from . import review
        review.recheck(home, a.n, model=a.model, effort=a.effort)
    elif a.command == "track":
        from . import tracker
        tracker.run(home, weekly=a.weekly)
    elif a.command == "digest":
        from . import digest
        digest.run(home, test=a.test)
    elif a.command == "notify":
        from . import notify
        notify.run(home)
    elif a.command == "daily":
        from . import describe, digest, discover, review, scrape, tracker
        day = str((home.settings.get("discover") or {}).get("weekly_on", "monday")).lower()
        if a.discover or tracker.DAYS[date.today().weekday()] == day or not (home.data / "boards.json").exists():
            discover.run(home)
        scrape.run(home)
        describe.run(home)
        review.run(home)
        tracker.run(home)
        digest.run(home)
    elif a.command == "test-email":
        from . import digest, notify
        digest.run(home, test=True)
        notify.run(home)
    elif a.command == "import-linkedin":
        from . import linkedin
        linkedin.run(home, a.export)
    elif a.command == "find-board":
        from . import findboard
        findboard.run(a.name, a.careers_page)
    elif a.command == "packs":
        from .companies import available_packs
        for name, desc in available_packs().items():
            print(f"{name:24} {desc}")
    elif a.command == "init":
        from . import setup
        setup.init(Path(a.folder))
    elif a.command == "doctor":
        from . import setup
        return 0 if setup.doctor(home) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
