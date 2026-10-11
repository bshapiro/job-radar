# Changelog

## 1.0.2

- Setup for people who have never used a terminal: the setup skill installs Python, git and GitHub's
  tool step by step, signs in to GitHub through the browser, and has secrets entered on GitHub's website.
- The getting-started guide has a no-terminal path, with a message to paste into Claude Code.

## 1.0.1

- Create `data/` when it's missing. Git doesn't keep an empty folder, so a freshly cloned profile repo
  (including the daily workflow's checkout) had none, and the first run failed.

## 1.0.0

First release.
- Readers for Greenhouse, Lever, Ashby, Workday, Oracle Recruiting, Workable, Getro and Consider boards.
- Rules in YAML: whole words, `*` wildcards, `not_after` / `not_before`, `then` sequences.
- Company packs: health-life-sciences, pharma, nyc-hospitals, ai-labs, science-funders, venture, advisory.
- Claude reviews with prompt caching and a cost report; `recheck` for measuring agreement.
- Applied / Not interested tracking in GitHub issues, with a weekly reminder and notice of postings
  that disappear.
- `init`, `doctor`, `find-board`, `import-linkedin`, `scrape --compare`, and Claude Code skills for setup,
  tuning and reviewing.
