"""One reader per job system. Each yields (title, location, url, posted) for every open job, or, for
portfolio boards that list jobs at many companies, (title, location, url, posted, company, industry tags).

Large boards (Workday, Oracle, Getro) are searched with the profile's search terms instead of being listed
in full; `searches` is that list.
"""
from __future__ import annotations

import html
import http.cookiejar
import json
import re
import urllib.request
from datetime import date
from urllib.parse import quote

USER_AGENT = "job-radar/1.0"
BROWSER = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}


def get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return json.load(urllib.request.urlopen(req, timeout=30))


def greenhouse(slug, searches=()):
    for j in get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")["jobs"]:
        yield (j["title"], (j.get("location") or {}).get("name", ""), j["absolute_url"],
               (j.get("first_published") or j.get("updated_at") or "")[:10])


def lever(slug, searches=()):
    for j in get(f"https://api.lever.co/v0/postings/{slug}?mode=json"):
        c = j.get("categories", {})
        loc = ", ".join(filter(None, [c.get("location"), j.get("workplaceType")]))
        yield j["text"], loc, j["hostedUrl"], date.fromtimestamp(j["createdAt"] / 1000).isoformat()


def ashby(slug, searches=()):
    for j in get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")["jobs"]:
        addr = (j.get("address") or {}).get("postalAddress") or {}   # "location" can be just an office name
        loc = ", ".join(filter(None, [j.get("location", ""), addr.get("addressLocality"), addr.get("addressRegion")]))
        loc += " (Remote)" if j.get("workplaceType") == "Remote" else ""
        yield j["title"], loc, j["jobUrl"], (j.get("publishedAt") or "")[:10]


def workday(slug, searches=()):
    """Workday boards are large, so search for the field instead of listing everything. Slug: host/tenant/site."""
    host, tenant, site = slug.split("/")
    base = f"https://{host}.myworkdayjobs.com"
    done = set()
    for query in searches:
        for offset in range(0, 200, 20):
            body = json.dumps({"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": query}).encode()
            req = urllib.request.Request(f"{base}/wday/cxs/{tenant}/{site}/jobs", data=body,
                                         headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"})
            posts = json.load(urllib.request.urlopen(req, timeout=30)).get("jobPostings", [])
            for j in posts:
                if j.get("externalPath") and j["externalPath"] not in done:
                    done.add(j["externalPath"])
                    yield j["title"], j.get("locationsText", ""), f"{base}/{site}{j['externalPath']}", j.get("postedOn", "")
            if len(posts) < 20:
                break


def oracle(slug, searches=()):
    """Oracle Cloud recruiting (large hospital systems). Slug: host/site; searched like Workday."""
    host, site = slug.split("/")
    base = f"https://{host}.oraclecloud.com"
    done = set()
    for query in searches:
        for offset in range(0, 200, 25):
            finder = f'findReqs;siteNumber={site},limit=25,offset={offset},keyword="{query}"'
            d = get(f"{base}/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true"
                    f"&expand=requisitionList.secondaryLocations&finder=" + quote(finder, safe=";=,"))
            posts = (d.get("items") or [{}])[0].get("requisitionList", [])
            for j in posts:
                if j["Id"] not in done:
                    done.add(j["Id"])
                    yield (j["Title"], j.get("PrimaryLocation") or "",
                           f"{base}/hcmUI/CandidateExperience/en/sites/{site}/job/{j['Id']}", (j.get("PostedDate") or "")[:10])
            if len(posts) < 25:
                break


def workable(slug, searches=()):
    token = None
    while True:
        body = json.dumps({"query": "", **({"token": token} if token else {})}).encode()
        req = urllib.request.Request(f"https://apply.workable.com/api/v3/accounts/{slug}/jobs", data=body,
                                     headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"})
        d = json.load(urllib.request.urlopen(req, timeout=30))
        for j in d["results"]:
            loc = j.get("location") or {}
            place = ", ".join(filter(None, [loc.get("city"), loc.get("region"), "Remote" if j.get("remote") else None]))
            yield j["title"], place, f"https://apply.workable.com/{slug}/j/{j['shortcode']}", (j.get("published") or "")[:10]
        token = d.get("nextPage")
        if not token:
            break


def getro(host, searches=()):
    """Getro portfolio board (a venture firm's listing of jobs at its companies), searched with `searches`."""
    page = urllib.request.urlopen(urllib.request.Request(f"https://{host}/jobs", headers=BROWSER), timeout=30).read().decode()
    network = json.loads(re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S).group(1)
                         )["props"]["pageProps"]["network"]["id"]
    done = set()
    for query in searches:
        for page_no in range(5):
            body = json.dumps({"hitsPerPage": 100, "page": page_no, "filters": {}, "query": query}).encode()
            req = urllib.request.Request(f"https://api.getro.com/api/v2/collections/{network}/search/jobs", data=body,
                                         headers={**BROWSER, "Content-Type": "application/json", "Accept": "application/json",
                                                  "Origin": f"https://{host}", "Referer": f"https://{host}/"})
            posts = json.load(urllib.request.urlopen(req, timeout=30))["results"]["jobs"]
            for j in posts:
                if j["url"] not in done:
                    done.add(j["url"])
                    org = j.get("organization") or {}
                    loc = "; ".join(j.get("searchable_locations") or []) + (" (Remote)" if j.get("work_mode") == "remote" else "")
                    yield (j["title"], loc, j["url"], date.fromtimestamp(j["created_at"]).isoformat(),
                           org.get("name", ""), " ".join(org.get("industry_tags") or []))
            if len(posts) < 100:
                break


def consider(host, searches=()):
    """Consider portfolio board. No text search, so page through everything."""
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    page = opener.open(urllib.request.Request(f"https://{host}/jobs", headers=BROWSER), timeout=30).read().decode()
    token = re.search(r'"csrfToken":"([^"]+)"', page).group(1)
    board = re.search(r'"fixedBoard":"([^"]+)"', page).group(1)
    meta = {"size": 500}
    for _ in range(40):
        body = json.dumps({"meta": meta, "board": {"id": board, "isParent": True}, "query": {}}).encode()
        req = urllib.request.Request(f"https://{host}/api-boards/search-jobs", data=body,
                                     headers={**BROWSER, "Content-Type": "application/json", "X-CSRF-Token": token})
        d = json.load(opener.open(req, timeout=60))
        for j in d["jobs"]:
            loc = "; ".join(j.get("locations") or []) + (" (Remote)" if j.get("remote") else "")
            yield (j["title"], loc, j.get("applyUrl") or j["url"], (j.get("timeStamp") or "")[:10],
                   j.get("companyName", ""), " ".join(m["label"] for m in j.get("markets") or []))
        if len(d["jobs"]) < meta["size"] or not d["meta"].get("sequence"):
            break
        meta = {"size": 500, "sequence": d["meta"]["sequence"]}


def arpah(_slug="", searches=()):
    """ARPA-H lists staff openings as headings on its careers page; the program manager role is a standing
    application, not a posting, so it is always yielded."""
    url = "https://arpa-h.gov/careers"
    page = urllib.request.urlopen(urllib.request.Request(url, headers=BROWSER), timeout=30).read().decode("utf-8", "ignore")
    section = page.split("Open Positions", 1)[-1].split("Program Managers", 1)[0]
    for h in re.findall(r"<h[2-4][^>]*>(.*?)</h[2-4]>", section, re.S):
        title = html.unescape(re.sub(r"<[^>]+>", "", h)).strip()
        if title:
            yield title.replace("ARPA-H ", ""), "", f"{url}#{quote(title)}", ""
    yield "Program Manager (standing application)", "", "https://arpa-h.gov/careers/program-managers", ""


FETCH = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby, "workday": workday, "oracle": oracle,
         "workable": workable, "getro": getro, "consider": consider, "arpah": arpah}
PORTFOLIO = {"getro", "consider"}          # boards listing jobs at many companies
SEARCHED = {"workday", "oracle", "getro"}  # boards read with the profile's search terms
