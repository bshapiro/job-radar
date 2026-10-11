"""Import saved and applied jobs from a LinkedIn data export into data/seed_jobs.csv.

These are a strong signal of what someone wants, used when writing preferences.md and rules.yaml (the
setup skill reads them). Request the export at linkedin.com > Settings > Data privacy > Get a copy of
your data; pass the downloaded .zip or its unzipped folder. LinkedIn sometimes sends the export in two
parts: the job files are in the "Complete" one.
"""
from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime
from pathlib import Path

from .home import Home

FILES = {"Saved Jobs.csv": ("Saved Date", "saved"), "Job Applications.csv": ("Application Date", "applied")}
FIELDS = ["source", "date", "company", "title", "url"]


def li_date(s: str) -> str:
    return datetime.strptime(s.replace(" ", " ").strip(), "%m/%d/%y, %I:%M %p").date().isoformat()


def _open(export: Path) -> dict[str, str]:
    """{file name: text} for the job files in an export folder or zip."""
    out = {}
    if export.is_dir():
        for name in FILES:
            for p in export.rglob(name):
                out[name] = p.read_text(encoding="utf-8-sig")
    else:
        with zipfile.ZipFile(export) as z:
            for info in z.infolist():
                name = Path(info.filename).name
                if name in FILES:
                    out[name] = z.read(info).decode("utf-8-sig")
    return out


def read(export: Path) -> list[dict]:
    rows = []
    for name, text in _open(export).items():
        date_col, source = FILES[name]
        for r in csv.DictReader(io.StringIO(text)):
            if r.get(date_col) and r.get("Job Title", "").strip():   # skip expired postings with no title
                rows.append(dict(source=source, date=li_date(r[date_col]), company=r["Company Name"].strip(),
                                 title=r["Job Title"].strip(), url=r["Job Url"]))
    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows


def run(home: Home, export: str) -> list[dict]:
    rows = read(Path(export).expanduser())
    if not rows:
        print(f"no saved or applied jobs found in {export} (if LinkedIn sent two parts, try the other one)")
        return rows
    home.data.mkdir(parents=True, exist_ok=True)
    out = home.data / "seed_jobs.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    by = {s: sum(r["source"] == s for r in rows) for s in ("saved", "applied")}
    print(f"{len(rows)} jobs ({by['saved']} saved, {by['applied']} applied) -> {out}")
    return rows
