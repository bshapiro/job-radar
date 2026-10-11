# job-radar

A daily job search that runs on GitHub Actions. job-radar reads employers' public job boards, scores
every title with rules you write, has Claude read the full description of each match, and emails you
the new ones every weekday morning. Each match gets Applied / Not interested tick boxes, so you can
keep track of what you've acted on.

It reads only public job-board data, from the systems employers use for their careers pages: Greenhouse,
Lever, Ashby, Workday, Oracle Recruiting, Workable, and the Getro and Consider boards that venture firms use
for their portfolio companies. It does not scrape LinkedIn or anything else behind a login.

## How it works

```
companies.yaml ─► discover ─► data/boards.json        (weekly: work out each employer's board)
                     │
rules.yaml ─────► scrape ───► data/jobs.csv            (matches, scored)
                     │        data/rejected.csv        (on-topic jobs that were filtered out, and why)
                     ▼
                 describe ──► data/descriptions/       (full text of each match)
                     │
preferences.md ─► review ───► data/reviews.csv         (Claude: strong / maybe / no, with a note)
                     │
                  track ────► GitHub issues            (Applied / Not interested tick boxes)
                     │
                  digest ───► email                    (new matches, weekly reminder, closed postings)
```

The engine (this repo) is public. Your preferences, rules, verdicts and application history live
in a **private profile repo** of your own, which installs a pinned version of the engine:

```
profile/
  preferences.md     what you're looking for, in plain language (Claude reads it for every review)
  rules.yaml         which titles match and how they rank
  companies.yaml     which employers to read (plus any packs)
  settings.yaml      review model, tracker timing (optional)
  review_prompt.md   instructions for the reviewer (optional; a neutral default is built in)
data/                written by the engine, committed by the daily run
.github/workflows/daily.yml
.claude/skills/      Claude Code skills for setup, tuning and reviewing
```

## Getting started

You need Python 3.10+, a GitHub account with the [GitHub CLI](https://cli.github.com/), an Anthropic
API key for the reviews, and a Gmail account (or any SMTP account) to send the email.

```sh
pip install "job-radar @ git+https://github.com/bshapiro/job-radar@v1.0.1"
mkdir my-job-search && cd my-job-search
job-radar init
```

Then open [Claude Code](https://claude.com/claude-code) in that folder and run **`/job-radar-setup`**.
It walks you through creating the private repo and its secrets. Then it interviews you about what
you're looking for, with an optional import of your LinkedIn saved and applied jobs. It drafts your
rules and company list, and calibrates a first run against verdicts you make by hand. The setup
skill's steps are in [`job_radar/skills/job-radar-setup/SKILL.md`](job_radar/skills/job-radar-setup/SKILL.md),
if you'd rather follow them yourself.

Later:
- **`/job-radar-review`** goes through matches with you and records your verdicts. Claude learns
  from these.
- **`/job-radar-tune`** finds good jobs the rules rejected and poor ones they let through, and
  checks each fix against real jobs.
- **`job-radar doctor`** checks the profile, boards and secrets, and says what to fix.

## Rules

`rules.yaml` is lists of words and phrases, matched as whole words ignoring case:

```yaml
exclude:
  - name: hands-on engineering
    words: [engineer, developer]
    unless: [director, head, manager]        # keeps "Engineering Director"
boosts:
  - points: 4
    words: [director, head, {word: manager, not_after: [product]}]
  - points: 2
    words: [health*, clinical, bio*]         # * stands for any letters
```

A title must mention your field, or be a role that counts on its own. The first exclusion it
matches rejects it. It then scores points for boosts, location and employer, and passes at
`min_score`. Every rejection is logged with its reason in `data/rejected.csv`. The template
([`templates/profile/rules.yaml`](job_radar/templates/profile/rules.yaml)) documents every setting.

## Company packs

Starting lists of employers with known boards, which `companies.yaml` can include
(`job-radar packs` lists them):

| Pack | |
|---|---|
| `health-life-sciences` | Health tech, AI for biology and drug discovery, longevity research |
| `pharma` | Large pharmaceutical and medical technology companies |
| `nyc-hospitals` | New York City hospital systems and cancer centers |
| `ai-labs` | Frontier AI labs |
| `science-funders` | Science foundations and public research funders |
| `venture` | Venture firms and studios, plus their portfolio-company job boards |
| `advisory` | Consultancies, government S&T contractors, AI evaluation, safety and biosecurity groups |

Contributions of new packs or corrected boards are welcome.

## Commands

| Command | |
|---|---|
| `job-radar daily` | The whole daily run (what the workflow calls) |
| `job-radar discover` | Work out each employer's board |
| `job-radar scrape` | Read the boards and score titles. `--save-raw FILE` keeps what was read. `--from-raw FILE --compare` shows how a rules change would move the matches, writing nothing |
| `job-radar describe` | Download the matches' full descriptions |
| `job-radar review` | Claude reviews new matches (`--dry-run` prints the prompt) |
| `job-radar recheck N` | Re-review N hand-judged jobs and report agreement |
| `job-radar track` / `digest` / `notify` | Tracker issues, the email, sending it |
| `job-radar test-email` | Email the current strong matches, to check delivery |
| `job-radar find-board NAME [URL]` | Find an employer's board |
| `job-radar import-linkedin EXPORT` | Saved and applied jobs from a LinkedIn data export |
| `job-radar init` / `doctor` | Make a profile repo / check one |

## Cost

The scraping is free, and GitHub Actions minutes for a private repo are well within the free tier.
Reviews use Claude Sonnet 5.5 at low effort, at about 1 cent per posting. That's typically a few
dollars a month, capped at 25 postings per run (`settings.yaml`). In a test on 20 hand-judged
postings, Sonnet 5.5 at low effort agreed with the hand verdict on 18. Opus 5.5 agreed on 17, at
nearly twice the cost, and Haiku 4.5 on 13.

## Upgrading

The profile's workflow pins an engine version (`JOB_RADAR` in `.github/workflows/daily.yml`). To
upgrade, read the [changelog](CHANGELOG.md), change the tag, and push.

## License

MIT
