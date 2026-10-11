"""Download the full description for every match in data/jobs.csv into data/descriptions/<id>.txt.
Already-downloaded descriptions are skipped, so this is cheap to re-run."""
from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import urllib.request
from urllib.parse import quote

from .fetchers import get
from .home import Home


def text(s):
    s = re.sub(r"<(br|/p|/li|/h\d|/div)[^>]*>", "\n", html.unescape(s or ""), flags=re.I)
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    return re.sub(r"\n\s*\n+", "\n\n", s).strip()


def job_id(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:12]


URL_PATTERNS = [("greenhouse", r"greenhouse\.io/([\w-]+)/jobs/\d+"), ("lever", r"jobs\.lever\.co/([\w-]+)/[\w-]+"),
                ("ashby", r"jobs\.ashbyhq\.com/([^/]+)/[\w-]+")]


def describe(board: dict | None, url: str) -> tuple[str, str]:
    """(description, locations) for one posting. Jobs found through a portfolio board have no board of their
    own, so work it out from the link, or fall back to the page text."""
    if not board or board["ats"] in ("getro", "consider", "arpah"):
        board = next(({"ats": a, "slug": m.group(1)} for a, p in URL_PATTERNS if (m := re.search(p, url))), None)
        if not board:
            req = urllib.request.Request(url.split("#")[0], headers={"User-Agent": "Mozilla/5.0"})
            page = urllib.request.urlopen(req, timeout=30).read(800000).decode("utf-8", "ignore")
            page = re.sub(r"<(script|style|nav|header|footer)[^>]*>.*?</\1>", "", page, flags=re.S | re.I)
            return text(page)[:15000], ""
        url = url.split("?")[0]
    ats, slug = board["ats"], board["slug"]
    if ats == "greenhouse":
        gid = re.search(r"gh_jid=(\d+)|/jobs/(\d+)", url)
        j = get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{gid.group(1) or gid.group(2)}")
        return text(j["content"]), j["location"]["name"]
    if ats == "lever":
        j = get(f"https://api.lever.co/v0/postings/{slug}/{url.rstrip('/').split('/')[-1]}")
        lists = "\n\n".join(f"{item['text']}\n{text(item['content'])}" for item in j.get("lists", []))
        body = "\n\n".join(filter(None, [j.get("descriptionPlain"), lists, j.get("additionalPlain")]))
        return body, j["categories"].get("location", "")
    if ats == "ashby":
        for j in get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")["jobs"]:
            if j["jobUrl"] == url:
                return j.get("descriptionPlain") or text(j.get("descriptionHtml")), j.get("location", "")
        raise LookupError("posting no longer listed")
    if ats == "workday":
        host, tenant, site = slug.split("/")
        info = get(f"https://{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{url.split('/' + site, 1)[1]}")["jobPostingInfo"]
        locs = [info.get("location", ""), *info.get("additionalLocations", [])]
        return text(info["jobDescription"]), "; ".join(filter(None, locs))
    if ats == "oracle":
        host, site = slug.split("/")
        finder = f'ById;Id="{url.rstrip("/").split("/")[-1]}",siteNumber={site}'
        j = get(f"https://{host}.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"
                f"?expand=all&onlyData=true&finder=" + quote(finder, safe=";=,"))["items"][0]
        parts = [j.get("ExternalDescriptionStr"), j.get("ExternalResponsibilitiesStr"), j.get("ExternalQualificationsStr")]
        return text("\n".join(filter(None, parts))), j.get("PrimaryLocation", "")
    if ats == "workable":
        j = get(f"https://apply.workable.com/api/v2/accounts/{slug}/jobs/{url.rstrip('/').split('/')[-1]}")
        loc = j.get("location") or {}
        body = "\n".join(filter(None, [j.get("description"), j.get("requirements"), j.get("benefits")]))
        return text(body), ", ".join(filter(None, [loc.get("city"), loc.get("region")]))
    raise ValueError(ats)


def run(home: Home) -> None:
    out = home.data / "descriptions"
    out.mkdir(parents=True, exist_ok=True)
    boards = json.loads((home.data / "boards.json").read_text())
    with open(home.data / "jobs.csv") as f:
        jobs = list(csv.DictReader(f))
    fetched = 0
    for r in jobs:
        path = out / f"{job_id(r['url'])}.txt"
        if path.exists():
            continue
        try:
            body, locations = describe(boards.get(r["company"]), r["url"])
        except Exception as e:
            print(f"!! {r['company']} | {r['title']}: {e}")
            continue
        path.write_text(f"Company: {r['company']}\nTitle: {r['title']}\nLocations: {locations}\nURL: {r['url']}\n\n{body}\n")
        fetched += 1
    print(f"{fetched} new descriptions, {len(list(out.glob('*.txt')))} total in {out}")
