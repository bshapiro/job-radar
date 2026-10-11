---
name: job-radar-review
description: Go through job-radar matches with the person - read the full descriptions, record their strong / maybe / no verdicts with notes, correct Claude's auto-reviews, and mark applications. Use when someone runs /job-radar-review or wants to go through their matches.
---

# Review matches with the person

Hand verdicts are what Claude's daily reviews learn from: every row in `data/reviews.csv` is
shown to it as an example. A few careful verdicts with notes do more than many quick ones.

## Ground rules

- The verdict is theirs. Summarize each job, and give your read if they ask for it, but record what
  they decide, in their words.
- Don't spend money without asking: reading descriptions is free; `job-radar review` is not.

## Steps

1. Pull the latest data first (`git pull`), since the daily run commits to the repo.
2. Ask what they want to go through. Options:
   - new matches not reviewed yet (`fit` empty in `data/jobs.csv`)
   - Claude's auto-reviews to check (`note` starting "Auto-review:"), strong and maybe ones first
   - everything still waiting for Applied / Not interested
   - one company or kind of role
3. For each job:
   - Read `data/descriptions/<id>.txt`, where the id is the first 12 hex characters of the SHA-1 of
     the job's URL: `python -c "from job_radar.describe import job_id; print(job_id('<url>'))"`.
     Run `job-radar describe` if it's missing.
   - Give a summary in four or five lines: what the job actually is, the location and office days,
     the pay if it's listed, the requirements that matter for them, and the catch.
   - Ask for their verdict (strong / maybe / no) and a one-line reason.
4. Record each verdict in `data/reviews.csv` (url, company, title, fit, note, reviewed = today):
   - For a job Claude already reviewed, replace that row. Don't add a second one.
   - Write the note in the style of the existing hand notes, without the "Auto-review:" prefix.
   - Update the job's `fit` and `note` in `data/jobs.csv` as well.
5. If they've applied to something or ruled it out, they can tick the box in the tracker issue. Or
   you can add a row to `data/applications.csv` (recorded, job = the 12-character id, company,
   title, status = Applied or Not interested, issue left empty, url).
6. Watch for patterns. If they keep overruling Claude in the same way, suggest updating
   `profile/preferences.md` or `profile/review_prompt.md`, or running `/job-radar-tune`.
7. Commit and push the updated data files (confirm first).
