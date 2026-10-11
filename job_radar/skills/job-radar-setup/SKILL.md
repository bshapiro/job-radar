---
name: job-radar-setup
description: Set up job-radar for a new person - accounts and secrets, a preferences interview (with an optional LinkedIn import), the rules and company list, and a first calibrated run. Use when someone runs /job-radar-setup or asks to set up their job search in this repo.
---

# Set up job-radar

You are helping someone set up a daily job search that reads public job boards, scores titles with
rules they own, has Claude review the full descriptions, and emails them the results. This repo is
their **profile repo**: `profile/` holds what they want, `data/` holds what the engine writes, and
`.github/workflows/daily.yml` runs it every weekday.

Work through the steps below in order. Say which step you're on. Each step ends with something the
person can check.

## Ground rules

- **Ask, don't assume.** Preferences are personal. When a choice isn't clear from what they've told you,
  ask, and offer two to four concrete options. Never fill a preference in on their behalf.
- **Never handle secrets.** API keys and passwords are entered by the person themselves, on GitHub's
  website (step 3). Never ask them to paste one into the chat. If they paste one anyway, tell them to
  revoke it and make a new one.
- **Go at their pace.** Many people doing this have never used a terminal. You run the commands, and
  explain in a sentence what each one is for. When something has to happen in their browser or an
  installer, give exact click-by-click steps and wait until they say it's done. Don't show them
  command output unless it matters.
- **Confirm outward-facing actions** before you take them: creating the GitHub repo, pushing, running
  the workflow, and anything that spends money (reviews cost about 1 cent per posting).
- **Keep it private.** The profile repo holds their preferences, CV notes and application history, so
  it must be a private repository.
- Run engine commands as `job-radar <command>` from the repo root. `job-radar doctor` checks
  everything and says what to fix. Run it whenever something seems off.

## 1. Prerequisites

Find out their operating system (`uname -s`, or ask), then check each one and help install whatever is
missing. Run each check yourself; for installers, walk them through it.
- **Python 3.10 or newer** (`python3 --version`). If it's older or missing, have them download the
  installer from python.org/downloads (the big yellow button), run it, and accept the defaults. On
  Windows, they must tick "Add python.exe to PATH" on the first screen. On a Mac, after installing,
  they double-click "Install Certificates.command" in the Python folder under Applications. Without
  it, downloads from job boards fail with certificate errors.
- **git** (`git --version`). On a Mac, running it the first time offers to install the developer
  tools: they click Install. On Windows, use the installer from git-scm.com with the default options.
- **The GitHub command-line tool** (`gh --version`). Use the installer from cli.github.com. On a Mac
  with Homebrew, `brew install gh` works too.
- **A GitHub account.** If they don't have one, they sign up at github.com (free).
- **GitHub sign-in** (`gh auth status`). If they're not signed in, sign them in through the browser:
  run `gh auth login --hostname github.com --git-protocol https --web`. It prints a one-time code and
  a link. Tell them the code, and have them open the link, sign in, enter the code, and approve.
  If that command waits for input you can't give it, have them type
  `! gh auth login --hostname github.com --git-protocol https --web` in this session themselves, then
  follow the same steps.
- **The engine** (`job-radar --version`). If it's missing, install the version pinned on the
  `JOB_RADAR` line of `.github/workflows/daily.yml`. If there's no workflow yet, install the version
  from the engine's README. Use a virtual environment in the folder: `python3 -m venv .venv`, then
  `.venv/bin/pip install "<that value>"` (on Windows, `.venv\Scripts\pip`). From then on, run the
  engine as `.venv/bin/job-radar`.
- If `profile/` doesn't exist yet, run `job-radar init` here.

## 2. The GitHub repo

If the folder isn't already a git repo with a GitHub remote, suggest a name (e.g. `my-job-search`)
and confirm it with them. Then run `git init`, and `gh repo create <name> --private --source .`.
Push in step 8, once there's something worth saving. In the repo's settings, Actions must be
allowed to create issues. This is on by default; the workflow asks for `issues: write`.

## 3. Accounts and secrets

The daily run needs four repository secrets. Prepare each value first, then they enter all four on
GitHub's website:

| Secret | What it is | How to get it |
|---|---|---|
| `ANTHROPIC_API_KEY` | Pays for the reviews (about 1 cent per posting, typically $2-5 a month). | Their own: console.anthropic.com > API keys > Create key. A separate workspace with a monthly spend limit is a good idea. If someone else is paying, that person creates the key and gives it to them privately (a password manager, or in person), not by email or chat. |
| `SMTP_USER` | The Gmail address that sends the email. | Any Gmail address they have. |
| `SMTP_PASSWORD` | A Gmail **app password**, not their normal password. | myaccount.google.com > Security > turn on 2-Step Verification if it's off > search the page for "App passwords" > make one called job-radar. Google shows 16 letters once, so they leave that page open until it's entered. |
| `EMAIL_TO` | Where the email goes. Several addresses can be separated by commas. | Usually the same address. |

To enter them, give them the link `https://github.com/<owner>/<repo>/settings/secrets/actions`.
For each secret: click **New repository secret**, type the name exactly as in the table, paste the
value, and click **Add secret**. (People comfortable with a terminal can type
`! gh secret set NAME` instead, which asks for the value.) Check with `job-radar doctor`, which lists
the secrets by name. It never shows the values.

Other email providers work too: they also set `SMTP_HOST` and `SMTP_PORT` (SSL). Without SMTP secrets
the digest is posted as a GitHub issue instead. Without the Anthropic key, matches are listed
unreviewed. Check the result with `job-radar doctor`.

## 4. Preferences interview

The goal is `profile/preferences.md`: a plain-language brief that Claude reads before every review.
The section headings are already in the template.

1. **Optional LinkedIn import.** Ask whether they'd like to use their LinkedIn saved and applied jobs
   as a starting signal. If yes: linkedin.com > Settings > Data privacy > Get a copy of your data >
   select "Jobs" (or everything). The export arrives by email, sometimes in two parts, and the job
   files are in the "Complete" one. Then run `job-radar import-linkedin <the zip>` and read
   `data/seed_jobs.csv`. Summarize the patterns you see (kinds of role, fields, levels, places,
   employers), then ask whether they're right. Don't treat the patterns as preferences until
   they've confirmed them.
2. **CV.** Ask whether they'd like you to read their CV (a file path). Use it for the "What my CV
   supports" section: strengths with years, and requirements they clearly don't meet.
3. **Interview**, a few questions at a time. Cover:
   - The kind of work they want to own, and what looks similar but isn't. For example: setting
     direction or doing the hands-on work; managing people or not.
   - Fields: the ones they care most about, the ones that are acceptable, and the ones that are out.
   - Seniority: their current level, and the highest and lowest titles they'd consider.
     Exceptions, such as junior titles being fine at investors.
   - Location: home, acceptable commute (which towns are really in reach), remote, relocation.
   - Employers they especially want, and any to avoid.
4. Write `preferences.md`, show it to them, and revise until they're happy.

## 5. Rules (`profile/rules.yaml`)

Draft the rules from the preferences and the seed jobs. The template's comments explain the syntax
and the scoring. Explain the draft in a few sentences per section, not line by line:
- `title.topic`: words that put a title in their field. `also_relevant`: roles that count without
  one of those words.
- `exclude`: one rule per kind of role they don't want. Each rule's `unless` keeps exceptions
  (e.g. "engineer" is out unless "director").
- `boosts`: what makes a title more promising. `min_score`: the threshold. Start at 7 and tune.
- `location`: local / remote / commutable, plus the towns inside the commutable area that are not
  actually in reach.
- `investors`, `domain`, `searches`: only if they apply. Explain each before including it.

Check the draft against the seed jobs: titles they saved should mostly pass, and titles they ignored
should mostly be rejected. You can test titles directly:
`python -c "from job_radar.home import Home; print(Home().rules.score('Company', 'Title', 'New York, NY'))"`.

## 6. Companies (`profile/companies.yaml`)

1. Run `job-radar packs`, explain the packs, and ask which ones fit. Packs are starting lists. A
   pack employer they don't want goes under `exclude:`.
2. Build their own list from the seed jobs' employers, the interview, and research. Use web search
   if it's available, and ask before making many requests. Look for employers in their fields and
   places that the packs don't cover.
3. For each employer: `job-radar find-board "Name"` (add its careers page URL if the name alone
   finds nothing). Check that the board belongs to the right company. Common names often belong to
   someone else, and a wrong guess goes under `wrong_slugs`. Boards found this way go under
   `boards:`. Employers whose board can't be found yet go under `find_boards:` (they're retried weekly).
4. Large employers on Workday or Oracle are searched with `searches.large_boards` from rules.yaml,
   so make sure those terms cover their field.
5. Run `job-radar discover` and show the result: how many boards were found, and which employers
   had none.

## 7. First run and calibration

1. Run `job-radar scrape --save-raw .cache/raw.json`, then `job-radar describe`.
2. Go through `data/jobs.csv` (matches) and `data/rejected.csv` (on-topic rejects, with the reason)
   with them. Look for good jobs that were rejected and bad jobs that matched. Fix the rules, then
   check the effect without re-reading the boards:
   `job-radar scrape --from-raw .cache/raw.json --compare` (this writes nothing). When the rules look
   right, run `job-radar scrape --from-raw .cache/raw.json` to update the files. (This is fine
   before going live. Once the daily run is on, leave `data/` to it: a local scrape records jobs as
   seen, so they'd never be emailed.)
3. **Hand verdicts.** Ask them to judge 15-20 matches: strong / maybe / no, plus a short note on why.
   Include several strong and maybe ones. Read each description from
   `data/descriptions/<id>.txt` to them in a few lines, if that helps. Record the verdicts in
   `data/reviews.csv` (columns: url, company, title, fit, note, reviewed). Claude learns from these
   examples.
4. Adjust `profile/review_prompt.md`: their home area (for commute notes), any requirement that
   usually rules them out, and how they'd like to be referred to.
5. With their OK on the cost (roughly $0.20), run `job-radar review`. Then run `job-radar recheck 10`.
   It re-reviews 10 hand-judged jobs with those verdicts hidden and reports agreement. Around 8 out
   of 10 or better is good. For each disagreement, decide with them whether to fix the preferences,
   the review prompt, or the hand verdict.

## 8. Go live

1. Run `job-radar doctor` and fix anything it flags.
2. Commit `profile/`, `data/`, `.github/` and `.claude/` (but not `.cache/`), and push. Confirm first.
3. Send a test email: `gh workflow run daily.yml -f test_email=true` (confirm first). Ask them to
   check that it arrived, including the spam folder. If it didn't arrive, check the run's log with
   `gh run list` / `gh run view --log`.
4. Explain the daily rhythm:
   - The email arrives on weekday mornings.
   - Each new strong or maybe match gets Applied / Not interested tick boxes in a GitHub issue.
   - On Mondays there's a reminder issue listing every match still waiting.
   - `/job-radar-review` helps them judge matches by hand.
   - `/job-radar-tune` adjusts the rules when the matches drift.
