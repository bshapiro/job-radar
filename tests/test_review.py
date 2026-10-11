"""Reviews with a fake Anthropic client: no requests are sent and nothing is spent."""
import csv
import json
from types import SimpleNamespace

import anthropic
import pytest

from job_radar import review
from job_radar.describe import job_id
from job_radar.review import REVIEW_FIELDS, Reviewer
from job_radar.scrape import FIELDS


class FakeClient:
    def __init__(self, answers):
        self.answers = list(answers)   # each: (fit, note), "refusal", or an exception
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.calls.append(kw)
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        usage = SimpleNamespace(input_tokens=1000, output_tokens=100, cache_creation_input_tokens=0,
                                cache_read_input_tokens=9000)
        if a == "refusal":
            return SimpleNamespace(usage=usage, stop_reason="refusal", content=[])
        fit, note = a
        return SimpleNamespace(usage=usage, stop_reason="end_turn",
                               content=[SimpleNamespace(type="text", text=json.dumps({"fit": fit, "note": note}))])


def api_error(status):
    """An APIStatusError as the SDK raises it, without a real HTTP response (only these fields are read)."""
    e = anthropic.APIStatusError.__new__(anthropic.APIStatusError)
    e.status_code, e.message = status, "nope"
    return e


def connection_error():
    e = anthropic.APIConnectionError.__new__(anthropic.APIConnectionError)
    Exception.__init__(e, "connection reset")
    return e


def job(n, fit="", note="", score=9):
    return dict(fit=fit, score=str(score), new="NEW", company="Lab Co", title=f"Job {n}", location="NYC", posted="",
                url=f"https://a/{n}", first_seen="2026-10-11", via="", note=note)


def setup_data(home, jobs, reviews=(), described=None):
    with open(home.data / "jobs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(jobs)
    with open(home.data / "reviews.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=REVIEW_FIELDS)
        w.writeheader()
        w.writerows(reviews)
    (home.data / "descriptions").mkdir(exist_ok=True)
    for j in jobs if described is None else described:
        (home.data / "descriptions" / f"{job_id(j['url'])}.txt").write_text(
            f"Title: {j['title']}\n\nWe are an equal opportunity employer.\nSalary $200k.\nLead the AI roadmap.")


@pytest.fixture
def client(monkeypatch):
    holder = {}

    def make(*answers):
        holder["c"] = FakeClient(answers)
        monkeypatch.setattr(anthropic, "Anthropic", lambda: holder["c"])
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        return holder["c"]
    return make


def read(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def test_review_records_verdicts_and_resorts(home, client):
    setup_data(home, [job(1, score=9), job(2, score=8), job(3, fit="no", note="Mine.", score=12)],
               reviews=[dict(url="https://a/3", company="Lab Co", title="Job 3", fit="no", note="Mine.", reviewed="")])
    c = client(("maybe", "NYC. Fine."), ("strong", "NYC. Great."))
    review.run(home)
    jobs = read(home.data / "jobs.csv")
    assert [(j["title"], j["fit"]) for j in jobs] == [("Job 2", "strong"), ("Job 1", "maybe"), ("Job 3", "no")]
    assert jobs[0]["note"] == "Auto-review: NYC. Great."
    revs = read(home.data / "reviews.csv")
    assert [(r["title"], r["fit"]) for r in revs] == [("Job 3", "no"), ("Job 1", "maybe"), ("Job 2", "strong")]
    # what was sent
    call = c.calls[0]
    system = call["system"][0]
    assert system["cache_control"] == {"type": "ephemeral"}
    assert "<preferences>" in system["text"] and "- [no] Lab Co | Job 3: Mine." in system["text"]
    assert call["model"] == "claude-sonnet-5-5" and call["output_config"]["effort"] == "low"
    assert call["output_config"]["format"]["schema"]["properties"]["fit"]["enum"] == ["strong", "maybe", "no"]
    assert call["fallbacks"] == "default" and call["betas"] == ["server-side-fallback-2026-07-01"]
    posting = call["messages"][0]["content"]
    assert "Salary $200k" in posting and "equal opportunity" not in posting   # boilerplate trimmed


def test_review_skips_without_a_key(home, monkeypatch, capsys):
    setup_data(home, [job(1)])
    monkeypatch.setattr(anthropic, "Anthropic", lambda: pytest.fail("no client without a key"))
    review.run(home)
    assert "no Anthropic credential" in capsys.readouterr().out
    assert read(home.data / "jobs.csv")[0]["fit"] == ""


def test_review_only_jobs_with_descriptions(home, client, capsys):
    setup_data(home, [job(1)], described=[])
    client()
    review.run(home)
    assert "no unreviewed jobs with descriptions" in capsys.readouterr().out


def test_dry_run_prints_prompt(home, client, capsys):
    setup_data(home, [job(1)])
    c = client()
    review.run(home, dry_run=True)
    out = capsys.readouterr().out
    assert "<previous_verdicts>" in out and "Lead the AI roadmap" in out and c.calls == []


def test_refusal_and_errors_leave_jobs_unreviewed(home, client, capsys):
    setup_data(home, [job(1), job(2), job(3), job(4)])
    client("refusal", api_error(529), connection_error(),
           ("no", "Remote. Wrong field."))
    review.run(home)
    out = capsys.readouterr().out
    assert "declined" in out and "API error 529" in out and "connection error" in out
    fits = {j["title"]: j["fit"] for j in read(home.data / "jobs.csv")}
    assert fits == {"Job 1": "", "Job 2": "", "Job 3": "", "Job 4": "no"}


def test_bad_key_stops_the_run(home, client, capsys):
    setup_data(home, [job(1), job(2)])
    c = client(api_error(401), ("strong", "x"))
    review.run(home)
    assert len(c.calls) == 1 and "API error 401" in capsys.readouterr().out


def test_limit_and_settings(home, client, capsys):
    (home.profile / "settings.yaml").write_text("review: {model: claude-opus-5-5, effort: medium, limit: 1}\n")
    setup_data(home, [job(1), job(2)])
    c = client(("maybe", "x"))
    review.run(home)
    assert len(c.calls) == 1 and c.calls[0]["model"] == "claude-opus-5-5"
    assert c.calls[0]["output_config"]["effort"] == "medium"
    assert "(limit reached)" in capsys.readouterr().out


def test_environment_overrides_settings(home, monkeypatch):
    (home.profile / "settings.yaml").write_text("review: {model: claude-opus-5-5}\n")
    monkeypatch.setenv("REVIEW_MODEL", "claude-haiku-4-5")
    assert Reviewer(home).model == "claude-haiku-4-5"
    assert Reviewer(home, model="claude-sonnet-5-5").model == "claude-sonnet-5-5"


def test_haiku_gets_no_effort_or_fallbacks(home, client):
    setup_data(home, [job(1)])
    c = client(("no", "x"))
    review.run(home, model="claude-haiku-4-5")
    assert "effort" not in c.calls[0]["output_config"] and "fallbacks" not in c.calls[0]


def test_cost_is_counted(home):
    rv = Reviewer(home)
    usage = SimpleNamespace(input_tokens=1_000_000, output_tokens=0, cache_creation_input_tokens=None,
                            cache_read_input_tokens=1_000_000)
    assert rv.record_usage(usage) == pytest.approx(2.20)   # Sonnet: $2 in + $0.20 cached
    assert rv.calls == 1 and "$2.200 for 1 postings" in rv.summary()


def test_recheck_holds_out_the_sample(home, client):
    jobs = [job(i) for i in range(1, 7)]
    reviews = [dict(url=f"https://a/{i}", company="Lab Co", title=f"Job {i}", fit=fit, note=note, reviewed="")
               for i, fit, note in [(1, "strong", "Hand 1"), (2, "maybe", "Hand 2"), (3, "no", "Hand 3"),
                                    (4, "no", "Hand 4"), (5, "strong", "Auto-review: auto"), (6, "no", "Hand 6")]]
    setup_data(home, jobs, reviews)
    c = client(*[("strong", "x")] * 4)
    agreed, total = review.recheck(home, 4)
    assert total == 4 and c.calls
    system = c.calls[0]["system"][0]["text"]
    held = [r for r in reviews if f"Lab Co | {r['title']}: {r['note']}" not in system]
    assert len(held) == 4 and all(not r["note"].startswith("Auto-review") for r in held)
    assert sum(r["fit"] in ("strong", "maybe") for r in held) == 2       # half from strong / maybe
    assert agreed == sum(r["fit"] == "strong" for r in held)
    assert read(home.data / "reviews.csv") == [{k: str(v) for k, v in r.items()} for r in reviews]   # nothing saved


def test_neutral_default_prompt(home):
    assert "they" in home.review_prompt() and " his " not in home.review_prompt()
    (home.profile / "review_prompt.md").write_text("Custom instructions.\n")
    assert home.review_prompt() == "Custom instructions."
