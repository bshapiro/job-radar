---
name: job-radar-tune
description: Tune a job-radar profile - find good jobs the rules rejected and poor jobs they let through, and adjust rules.yaml, companies.yaml or the review prompt, checking each change before it is kept. Use when someone runs /job-radar-tune or says the matches are off, too many, or too few.
---

# Tune job-radar

Improve which jobs match, based on evidence. Every change is checked against real jobs before it
is kept.

## Ground rules

- Propose each change, show its effect, and apply it only after the person agrees. Their
  preferences decide what counts as a good match, not your judgment.
- Leave the match data in `data/` to the daily run. Never run a plain `job-radar scrape` or
  `scrape --from-raw`: either one records today's jobs in `data/seen.json`, and the daily run
  would then never email them. Use `--compare`, which writes nothing in `data/`.
- Reviews cost money (about 1 cent per posting). Ask before running `review` or `recheck`.

## 1. Gather the evidence

- Save one read of the boards to compare against, without touching `data/`:
  `job-radar scrape --save-raw .cache/raw.json --compare`. Skip this if `.cache/raw.json` is from today.
- Read `profile/preferences.md`, `profile/rules.yaml` and `profile/companies.yaml`.
- Read `data/reviews.csv`. A "no" on a high-scoring match points to a rule that is too loose. A
  hand verdict that disagrees with an "Auto-review" points to the review prompt or the preferences.
- Read `data/rejected.csv`, grouped by reason. Look for titles that look right for this person but
  were rejected. Common causes: an exclusion word inside a good title, a missing `unless`, a
  location written in an unexpected way, or a score just below `min_score`.
- Read `data/jobs.csv`. Look for matches that are clearly wrong for them.
- Read `data/run.json`, where `failed_boards` lists boards that couldn't be read. If employers seem
  missing, run `job-radar discover`. It only rewrites `data/boards.json`, so it is safe here.

## 2. Propose changes

Group what you found into a short list, most impactful first. For each item, give the evidence (two
or three example titles), the change (the exact YAML edit), and the expected effect. Typical changes:
- A word added to an exclusion's `unless`, or a phrase using `not_after` / `not_before` instead of a
  bare word.
- A boost for a kind of title they keep marking strong.
- A town added to `location.not_commutable`, or a location spelling added to `local`.
- A missing employer: find its board with `job-radar find-board "Name"` and add it to companies.yaml.
- Wording in `preferences.md` or `review_prompt.md` when Claude's verdicts drift.

## 3. Check each change

After each rules edit, run `job-radar scrape --from-raw .cache/raw.json --compare` and show what
moved. A change should add the jobs it was meant to add without bringing in a pile of unwanted ones.
If it does both, narrow the change.

To test one title: `python -c "from job_radar.home import Home; print(Home().rules.score('Company', 'Title', 'Location'))"`.

For review-prompt changes, run `job-radar recheck 10` before and after (with their OK on the cost,
about $0.10 each) and compare the agreement.

## 4. Keep it

When they're happy:
- Don't rescore the data here. The next daily run applies the new rules, and jobs that newly match
  are marked NEW and included in its email.
- Run `job-radar doctor`.
- Commit the profile changes with a message saying what changed and why, and push (confirm first).
- If `preferences.md` and `rules.yaml` now disagree, update `preferences.md` too: Claude reads it on
  every review.
