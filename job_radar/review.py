"""Review unreviewed matches in data/jobs.csv with Claude: read each full description against
profile/preferences.md and the verdicts already in data/reviews.csv, and record a strong / maybe / no
verdict with a short note. Updates data/reviews.csv and data/jobs.csv in place.

The instructions come from profile/review_prompt.md (a neutral default if there is none). Model, effort
and the most postings per run come from profile/settings.yaml under `review:`; the environment variables
REVIEW_MODEL and REVIEW_EFFORT override them for one run.

Needs ANTHROPIC_API_KEY (or another Anthropic credential); without one it skips quietly.
`recheck(n)` re-reviews n jobs that already have a hand-made verdict (left out of the examples) and
prints how often Claude agrees, without saving anything: a quality check.
"""
from __future__ import annotations

import csv
import json
import os
import random
from datetime import date
from pathlib import Path

from .describe import job_id
from .home import Home
from .trim import trim

# Sonnet 5.5 at low effort agreed with hand verdicts on 18/20 postings at about 1 cent each
# (Opus 5.5 low: 17/20 at 1.8 cents; Haiku 4.5: 13/20), measured 2026-10-03.
DEFAULTS = {"model": "claude-sonnet-5-5", "effort": "low", "limit": 25}
# $ per million tokens: (input, output, cache write, cache read). Used only to print what a run cost.
PRICES = {"claude-opus-5-5": (4.00, 20.00, 5.00, 0.20), "claude-sonnet-5-5": (2.00, 10.00, 2.50, 0.20),
          "claude-haiku-4-5": (1.00, 5.00, 1.25, 0.10)}
REVIEW_FIELDS = ["url", "company", "title", "fit", "note", "reviewed"]
JOB_ORDER = {"strong": 0, "maybe": 1, "": 2, "no": 3}
AUTO = "Auto-review: "

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "fit": {"type": "string", "enum": ["strong", "maybe", "no"]},
        "note": {"type": "string"},
    },
    "required": ["fit", "note"],
    "additionalProperties": False,
}


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path) as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, fields: list, rows: list) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


class Reviewer:
    def __init__(self, home: Home, model: str | None = None, effort: str | None = None):
        cfg = {**DEFAULTS, **(home.settings.get("review") or {})}
        self.home = home
        self.model = model or os.environ.get("REVIEW_MODEL") or cfg["model"]
        self.effort = effort or os.environ.get("REVIEW_EFFORT") or cfg["effort"]
        self.limit = int(cfg["limit"])
        self.cost, self.calls = 0.0, 0
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    def system_prompt(self, reviews: list[dict]) -> str:
        examples = "\n".join(f"- [{r['fit']}] {r['company']} | {r['title']}: {r['note']}"
                             for r in reviews if r.get("company"))
        return (f"{self.home.review_prompt()}\n\n<preferences>\n{self.home.preferences()}\n</preferences>\n\n"
                f"<previous_verdicts>\n{examples}\n</previous_verdicts>")

    def record_usage(self, usage) -> float:
        """Add one response's token usage to the running cost (cache writes priced at the 5-minute rate)."""
        p_in, p_out, p_write, p_read = PRICES.get(self.model, PRICES["claude-opus-5-5"])
        cost = (usage.input_tokens * p_in + usage.output_tokens * p_out
                + (usage.cache_creation_input_tokens or 0) * p_write
                + (usage.cache_read_input_tokens or 0) * p_read) / 1e6
        self.cost += cost
        self.calls += 1
        return cost

    def review(self, system: str, job: dict, description: str):
        """(fit, note) for one job, or None if the model declined."""
        output_config = {"format": {"type": "json_schema", "schema": VERDICT_SCHEMA}}
        extra = {}
        if not self.model.startswith("claude-haiku"):   # Haiku 4.5 takes neither effort nor fallbacks
            output_config["effort"] = self.effort
            extra = {"betas": ["server-side-fallback-2026-07-01"],
                     "fallbacks": "default"}             # re-run on a fallback model if declined
        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            output_config=output_config,
            **extra,
            # The system prompt is identical for every job in a run, so cache it.
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content":
                       f"Company: {job['company']}\nTitle: {job['title']}\n"
                       f"Listed location: {job['location']}\n\n<posting>\n{trim(description)}\n</posting>"}],
        )
        cost = self.record_usage(response.usage)
        u = response.usage
        print(f"      tokens: {u.input_tokens} in, {u.cache_read_input_tokens or 0} cached, "
              f"{u.cache_creation_input_tokens or 0} cache-write, {u.output_tokens} out; ${cost:.4f}")
        if response.stop_reason == "refusal":
            return None
        verdict = json.loads(next(b.text for b in response.content if b.type == "text"))
        return verdict["fit"], verdict["note"]

    def summary(self) -> str:
        return f"${self.cost:.3f} for {self.calls} postings ({self.model}, {self.effort} effort)"


def has_credential() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def run(home: Home, dry_run: bool = False, limit: int | None = None, model=None, effort=None) -> None:
    data, rv = home.data, Reviewer(home, model, effort)
    limit = limit or rv.limit
    jobs = read_csv(data / "jobs.csv")
    reviews = read_csv(data / "reviews.csv")
    todo = []
    for j in jobs:
        path = data / "descriptions" / f"{job_id(j['url'])}.txt"
        if not j["fit"] and path.exists():
            todo.append((j, path.read_text()))
    if not todo:
        print("no unreviewed jobs with descriptions")
        return
    system = rv.system_prompt(reviews)
    if dry_run:
        print(system, "\n\n----- first job -----\n", todo[0][1][:3000])
        return
    if not has_credential():
        print(f"{len(todo)} unreviewed jobs, but no Anthropic credential; skipping review")
        return

    import anthropic
    done = {}
    for job, description in todo[:limit]:
        try:
            result = rv.review(system, job, description)
        except anthropic.APIStatusError as e:
            print(f"!! {job['company']} | {job['title']}: API error {e.status_code}: {e.message}")
            if e.status_code in (401, 403):
                break      # bad key: no point trying the rest
            continue
        except anthropic.APIConnectionError as e:
            print(f"!! {job['company']} | {job['title']}: connection error: {e}")
            continue
        if result is None:
            print(f"!! {job['company']} | {job['title']}: declined; left unreviewed")
            continue
        fit, note = result
        done[job["url"]] = (fit, AUTO + note)
        reviews.append(dict(url=job["url"], company=job["company"], title=job["title"],
                            fit=fit, note=AUTO + note, reviewed=date.today().isoformat()))
        print(f"{fit:6} {job['company']} | {job['title']}")

    if done:
        write_csv(data / "reviews.csv", REVIEW_FIELDS, reviews)
        for j in jobs:
            if j["url"] in done:
                j["fit"], j["note"] = done[j["url"]]
        jobs.sort(key=lambda r: (JOB_ORDER[r["fit"]], -int(r["score"]), r["company"]))
        write_csv(data / "jobs.csv", list(jobs[0].keys()), jobs)
    if rv.calls:
        print(f"review cost {rv.summary()}")
    print(f"reviewed {len(done)}; {len(todo) - len(done)} still unreviewed"
          + (" (limit reached)" if len(todo) > limit else ""))


def recheck(home: Home, n: int, model=None, effort=None) -> tuple[int, int]:
    """Re-review n hand-reviewed jobs and report agreement. Returns (agreed, total)."""
    data, rv = home.data, Reviewer(home, model, effort)
    reviews = [r for r in read_csv(data / "reviews.csv") if r.get("company")]
    jobs = {j["url"]: j for j in read_csv(data / "jobs.csv")}
    desc = lambda url: data / "descriptions" / f"{job_id(url)}.txt"
    sample = [r for r in reviews if not r["note"].startswith(AUTO) and r["url"] in jobs and desc(r["url"]).exists()]
    # Half the sample from strong / maybe verdicts: most verdicts are "no", and those are the easy calls.
    rng = random.Random(0)
    hard = [r for r in sample if r["fit"] in ("strong", "maybe")]
    easy = [r for r in sample if r["fit"] == "no"]
    k = min(n // 2, len(hard))
    sample = rng.sample(hard, k) + rng.sample(easy, min(n - k, len(easy)))
    held_out = {r["url"] for r in sample}
    system = rv.system_prompt([r for r in reviews if r["url"] not in held_out])
    agree = 0
    for r in sample:
        result = rv.review(system, jobs[r["url"]], desc(r["url"]).read_text())
        fit = result[0] if result else "declined"
        agree += fit == r["fit"]
        print(f"{'same' if fit == r['fit'] else 'DIFF'}  hand={r['fit']:6} claude={fit:6} {r['company']} | {r['title']}")
        if result and fit != r["fit"]:
            print(f"      claude's note: {result[1]}")
    print(f"agreement: {agree}/{len(sample)}; cost {rv.summary()}")
    return agree, len(sample)
