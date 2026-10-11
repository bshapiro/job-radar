# Getting started with job-radar

This guide is for anyone setting up job-radar for their own search. It covers what you get, what you
need, how setup works, and what to do day to day. You don't need to know how the code works.

## What you get

Every weekday morning, job-radar checks the careers pages of the employers you choose, and emails
you the jobs posted since yesterday that fit what you're looking for. Claude has read each job's full
description before it reaches you.

**The daily email** looks like this:

> **Job matches 2026-10-13: 3 new**
>
> 3 new matching jobs (0 not yet reviewed).
>
> | Fit | Company | Role | Note |
> |---|---|---|---|
> | strong | Example Health | [Director, AI Product](#) <br> New York, NY | New York, hybrid 3 days. Owns the roadmap for clinical AI tools; $210-250k. |
> | maybe | Acme Bio | [Head of Data Science](#) <br> Remote | Remote US. Leads a team of 6 building trial-design models. Stretch on the CV: wants 8 years managing people. |
> | maybe | Big Pharma | [AI Strategy Lead](#) <br> Princeton, NJ | Princeton, about 1 hour by train. Sets AI priorities for R&D. |
>
> [Mark these Applied / Not interested](#)

Each match is marked **strong**, **maybe** or **no**, with a short note. The note covers where the job
is, what it actually involves, and the catch. Jobs Claude marks "no" are left out of the email. On a day
with nothing new you get a one-line email saying so, which tells you the search ran and found nothing.

**Tracking what you've done with each job.** The email links to a GitHub issue that lists the new
matches, each with two tick boxes: **Applied** and **Not interested**. Tick one when you act on a job.
Every Monday a reminder issue lists every strong or maybe match you haven't ticked yet, oldest first.
If one of those jobs disappears from its employer's site before you tick it, the next email says so.
That way nothing is quietly lost.

**Everything is kept in your own private GitHub repository:** every match, every verdict, and your
application history. You can open those files any time.

## What you need

| | | Cost |
|---|---|---|
| A **GitHub account** | Runs the daily search and stores your files. | Free |
| An **Anthropic API key** | Pays for Claude's reviews. Make one at [console.anthropic.com](https://console.anthropic.com), or someone else can make one for you. | About 1 cent per job reviewed, typically a few dollars a month |
| A **Gmail account** to send the email | Any Gmail address works, including your usual one. Other email providers work too. | Free |
| A computer with **Python 3.10+** and **[Claude Code](https://claude.com/claude-code)** | Used only for setup and occasional tuning; the daily search runs on GitHub. | |
| *Optional:* your **LinkedIn data export** | Your saved and applied jobs, as a starting point for your preferences. | Free |

**Time:** about an hour, mostly the interview about what you're looking for. If you want to use your
LinkedIn data, request the export first (see step 4), because it can take up to a day to arrive.

## Setting up

Setup is done with Claude Code. Claude interviews you and does the technical steps, and stops to ask
before anything that creates, publishes or costs something.

**1. Install job-radar** in a terminal:

```sh
pip install "job-radar @ git+https://github.com/bshapiro/job-radar@v1.0.1"
```

**2. Make a folder** for your search and set it up:

```sh
mkdir my-job-search
cd my-job-search
job-radar init
```

**3. Start Claude Code** in that folder (`claude`), and type **`/job-radar-setup`**.

From there, Claude walks you through the rest:

- **The GitHub repository.** It creates a *private* repository for your search.
- **Your keys and passwords.** It explains each of the four settings (the Anthropic key, the Gmail
  address that sends the email, a Gmail *app password*, and where the email goes). You type each one
  into a prompt in your own terminal, so Claude never sees them. The Gmail app password isn't your
  normal password: you make one at Google Account > Security > App passwords, which needs 2-Step
  Verification turned on.
- **What you're looking for.** Claude interviews you a few questions at a time:
  - the kind of work you want, and work that looks similar but isn't
  - your fields
  - your level, and the range you'd consider
  - where you can work
  - your strengths and any requirements you don't meet
  - employers you'd like or want to avoid

  You can give it your CV to read. It writes this up as `profile/preferences.md`, a brief Claude
  rereads before every review. You check it and change anything that's off.
- **The rules** that decide which job titles are worth reading, written from your preferences.
- **The employers to watch.** You choose from ready-made lists (health and life sciences, pharma,
  New York hospitals, AI labs, science funders, venture firms, consultancies), and Claude finds the
  careers pages of any others you name.
- **A first run and calibration.** Claude runs the search once, and you go through the results
  together. You look for good jobs that were filtered out and poor ones that got through, and Claude
  adjusts the rules. Then you judge 15-20 jobs yourself as strong, maybe or no, with a reason. Claude
  learns from these examples. A quick test checks that its verdicts agree with yours on most of them,
  costing about $0.20.
- **Going live.** Claude saves everything to GitHub and sends a test email. Check your spam folder if
  it doesn't arrive.

**4. LinkedIn data (optional).** On LinkedIn, go to Settings > Data privacy > Get a copy of your
data, and choose Jobs (or everything). The download link arrives by email, sometimes in two parts. The
job files are in the one marked "Complete". Give Claude the downloaded file when it asks during the
interview.

You can also set up without Claude Code: the steps Claude follows are written out in
[`job_radar/skills/job-radar-setup/SKILL.md`](../job_radar/skills/job-radar-setup/SKILL.md), and the
template files that `job-radar init` makes explain every setting.

## Day to day

- **Read the email** each weekday morning (about 7am New York time; 6am in winter).
- **Tick Applied or Not interested** in the linked GitHub issue for each job you act on.
- **Correct Claude when it's wrong.** In Claude Code in your folder, type **`/job-radar-review`** to go
  through matches together. Your corrections become examples for future reviews, so it gets closer to
  your judgment over time.
- **Adjust the search** if the matches drift (too many, too few, or the wrong kind). Type
  **`/job-radar-tune`**. Claude looks at what was filtered out and what got through, proposes changes,
  and shows you their effect on real jobs before keeping any of them.

Your search runs on GitHub and saves its results there every day. Before changing files on your
computer, get the latest version (`git pull`, or ask Claude to).

## When something goes wrong

Start with **`job-radar doctor`** in your folder. It checks your files, the employer list and your
GitHub settings, and says what to fix.

| What you see | What to do |
|---|---|
| No email this morning | Check spam. Then open your repository on GitHub > **Actions** > the latest run. If it failed, the log says why. To check email alone, click **Run workflow**, tick "Only email the current strong matches", and run it. |
| An email from GitHub saying a run failed | Open the run from the email to see the error. A one-off failure is often GitHub itself having an outage; the next day's run usually works. If it fails two days running, ask Claude in your folder to look at it. |
| "Boards that couldn't be read today" at the bottom of the email | An employer's careers site didn't respond. It's tried again the next day; nothing to do unless the same one fails for a week. |
| Jobs listed as "unreviewed" | Claude couldn't review them: no Anthropic key, the key was rejected, the day's limit of 25 reviews was reached, or the employer's site blocked the description download. `job-radar doctor` checks the key. |
| A job you'd want never shows up | Its employer may not be on your list, or the rules may be filtering it out. Use `/job-radar-tune`, and name the job if you know it. |
| Too many poor matches | `/job-radar-tune`. Correcting a few verdicts with `/job-radar-review` also helps. |

## Costs and limits

- **Claude reviews:** about 1 cent per job, at most 25 a day (you can change this). Only new matches
  are reviewed, and each job only once. Expect a few dollars a month. You can set a monthly spending
  limit in the Anthropic console.
- **GitHub:** the daily run takes a few minutes, well within GitHub's free allowance for private
  repositories.
- **Which employers can be read:** job-radar reads the public job listings that employers publish
  through common hiring systems (Greenhouse, Lever, Ashby, Workday, Oracle, Workable, and the
  portfolio boards of venture firms). It doesn't log in anywhere and doesn't read LinkedIn. A few
  employers run their own careers sites, which it can't read; `job-radar find-board` tells you
  whether an employer can be read.

## Privacy

Your repository is private: your preferences, CV notes, verdicts and application history stay in
it. job-radar sends job descriptions, your preferences and your past verdicts to Anthropic's API so
Claude can review each job. The daily email goes only to the address you set.
