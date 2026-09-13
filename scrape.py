#!/usr/bin/env python3
"""
scrape.py - pulls early-career finance roles straight from company ATS systems.

Categories: off-cycle, graduate, summer, placement.
Writes docs/jobs.json, which the website reads.

    python scrape.py verify     # test which company endpoints work
    python scrape.py run        # fetch everything, write docs/jobs.json
"""

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import time

import requests

HERE = pathlib.Path(__file__).parent
OUT = HERE / "docs"
OUT.mkdir(exist_ok=True)

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept": "application/json"})
TIMEOUT = 25

# --------------------------------------------------------------------------
# COMPANIES
#
# Slugs below are starting guesses. Run `python scrape.py verify` and fix the
# failures. Finding a slug:
#   greenhouse  boards.greenhouse.io/<slug>
#   lever       jobs.lever.co/<slug>
#   ashby       jobs.ashbyhq.com/<slug>
#   smartrec    careers.smartrecruiters.com/<slug>
#   workday     open careers site, DevTools > Network > XHR, find the call to
#               /wday/cxs/<tenant>/<site>/jobs
# --------------------------------------------------------------------------
COMPANIES = [
    {"name": "J.P. Morgan",      "kind": "workday", "host": "jpmc.wd5.myworkdayjobs.com",      "tenant": "jpmc",      "site": "External"},
    {"name": "Morgan Stanley",   "kind": "workday", "host": "ms.wd5.myworkdayjobs.com",        "tenant": "ms",        "site": "External"},
    {"name": "Citi",             "kind": "workday", "host": "citi.wd5.myworkdayjobs.com",      "tenant": "citi",      "site": "2"},
    {"name": "Barclays",         "kind": "workday", "host": "barclays.wd3.myworkdayjobs.com",  "tenant": "barclays",  "site": "External"},
    {"name": "Deutsche Bank",    "kind": "workday", "host": "db.wd3.myworkdayjobs.com",        "tenant": "db",        "site": "DBWebsite"},
    {"name": "Jefferies",        "kind": "workday", "host": "jefferies.wd5.myworkdayjobs.com", "tenant": "jefferies", "site": "Jefferies_Careers"},
    {"name": "Houlihan Lokey",   "kind": "workday", "host": "hl.wd1.myworkdayjobs.com",        "tenant": "hl",        "site": "HL"},

    {"name": "Evercore",         "kind": "greenhouse", "slug": "evercore"},
    {"name": "Moelis",           "kind": "greenhouse", "slug": "moelis"},
    {"name": "PJT Partners",     "kind": "greenhouse", "slug": "pjtpartners"},
    {"name": "Perella Weinberg", "kind": "greenhouse", "slug": "perellaweinbergpartners"},

    {"name": "Citadel",          "kind": "greenhouse", "slug": "citadel"},
    {"name": "Jane Street",      "kind": "greenhouse", "slug": "janestreet"},
    {"name": "Point72",          "kind": "greenhouse", "slug": "point72"},
    {"name": "Balyasny",         "kind": "greenhouse", "slug": "balyasnyassetmanagement"},
    {"name": "Squarepoint",      "kind": "greenhouse", "slug": "squarepointcapital"},
    {"name": "Man Group",        "kind": "greenhouse", "slug": "mangroup"},
    {"name": "Marshall Wace",    "kind": "greenhouse", "slug": "marshallwace"},
    {"name": "G-Research",       "kind": "greenhouse", "slug": "gresearch"},

    {"name": "Blackstone",       "kind": "greenhouse", "slug": "blackstone"},
    {"name": "KKR",              "kind": "greenhouse", "slug": "kkr"},
    {"name": "Apollo",           "kind": "greenhouse", "slug": "apolloglobalmanagement"},
    {"name": "Ares",             "kind": "greenhouse", "slug": "aresmanagement"},
]

WORKDAY_SEARCHES = ["intern", "graduate", "analyst programme", "placement"]

# --------------------------------------------------------------------------
# CLASSIFIER
# --------------------------------------------------------------------------
EXPERIENCED = [
    r"\bvice president\b", r"\bv\.?p\.?\b", r"\bmanaging director\b",
    r"\bexecutive director\b", r"\bdirector\b", r"\bsenior\b", r"\bprincipal\b",
    r"\bhead of\b", r"\blead\b", r"\b[3-9]\+? years\b", r"\bexperienced hire\b",
]
OFFCYCLE = [
    r"off[\s\-]?cycle",
    r"\b(6|six|9|nine|12|twelve)[\s\-]?month\b.{0,30}\b(intern|placement)",
    r"\bintern(ship)?\b.{0,30}\b(6|six|9|nine|12|twelve)[\s\-]?month",
    r"\bwinter intern", r"\bspring intern",
]
PLACEMENT = [
    r"industrial placement", r"placement (year|student|programme|program)",
    r"\bplacement\b", r"\bsandwich (year|placement)\b", r"\byear in industry\b",
]
GRADUATE = [
    r"\bgraduate\b", r"\bnew grad\b", r"\bcampus hire\b",
    r"\banalyst (programme|program|scheme|rotational)\b",
    r"\bfull[\s\-]?time analyst\b", r"\bfirst year analyst\b",
    r"\b20\d\d\b.{0,20}\banalyst\b.{0,20}\b(programme|program|scheme)\b",
    r"\bentry[\s\-]?level\b",
]
SUMMER = [
    r"\bsummer (analyst|associate|intern|internship)\b",
    r"\bsummer (programme|program)\b",
]
EXCLUDE = [
    r"\bspring week\b", r"\binsight (week|day|programme|program|series)\b",
    r"\bmba\b", r"\bphd\b", r"\bapprentice", r"\bschool leaver\b",
]
FINANCE = [
    r"investment bank", r"\bibd\b", r"\bm&a\b", r"market", r"equit", r"credit",
    r"fixed income", r"research", r"coverage", r"leveraged finance", r"restructur",
    r"capital markets", r"\becm\b", r"\bdcm\b", r"private equity", r"asset management",
    r"trading", r"\bsales\b", r"\brisk\b", r"quant", r"financ", r"portfolio",
    r"investment", r"banking", r"treasury", r"\bwealth\b", r"advisory",
]


def _any(pats, text):
    return any(re.search(p, text, re.I) for p in pats)


def categorise(title, body=""):
    """Return category string, or None if not an early-career finance role."""
    t = title or ""
    b = (body or "")[:4000]
    if _any(EXCLUDE, t) or _any(EXPERIENCED, t):
        return None

    cat = None
    if _any(OFFCYCLE, t):
        cat = "off-cycle"
    elif _any(PLACEMENT, t):
        cat = "placement"
    elif _any(SUMMER, t):
        cat = "summer"
    elif _any(GRADUATE, t):
        cat = "graduate"
    elif re.search(r"\bintern(ship)?s?\b", t, re.I):
        # bare "Intern" in the title - fall back to the body to place it
        if _any(OFFCYCLE, b):
            cat = "off-cycle"
        elif _any(SUMMER, b):
            cat = "summer"
        else:
            cat = "off-cycle"

    if not cat:
        return None
    if not _any(FINANCE, t + " " + b):
        return None
    return cat


# --------------------------------------------------------------------------
# ATS ADAPTERS
# --------------------------------------------------------------------------
def _norm(company, title, location, url, posted=None, desc="", ext_id=""):
    return {"company": company, "title": (title or "").strip(),
            "location": (location or "").strip(), "url": url,
            "posted": posted, "description": desc or "", "ext_id": str(ext_id)}


def fetch_greenhouse(c):
    r = SESSION.get(f"https://boards-api.greenhouse.io/v1/boards/{c['slug']}/jobs?content=true",
                    timeout=TIMEOUT)
    r.raise_for_status()
    return [_norm(c["name"], j.get("title"), (j.get("location") or {}).get("name", ""),
                  j.get("absolute_url"), j.get("updated_at"), j.get("content", ""), j.get("id"))
            for j in r.json().get("jobs", [])]


def fetch_lever(c):
    r = SESSION.get(f"https://api.lever.co/v0/postings/{c['slug']}?mode=json", timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for j in r.json():
        posted = j.get("createdAt")
        if isinstance(posted, int):
            posted = dt.datetime.utcfromtimestamp(posted / 1000).isoformat()
        out.append(_norm(c["name"], j.get("text"), (j.get("categories") or {}).get("location", ""),
                         j.get("hostedUrl"), posted, j.get("descriptionPlain", ""), j.get("id")))
    return out


def fetch_ashby(c):
    r = SESSION.get(f"https://api.ashbyhq.com/posting-api/job-board/{c['slug']}", timeout=TIMEOUT)
    r.raise_for_status()
    return [_norm(c["name"], j.get("title"), j.get("location", ""), j.get("jobUrl"),
                  j.get("publishedAt"), j.get("descriptionPlain", ""), j.get("id"))
            for j in r.json().get("jobs", [])]


def fetch_smartrec(c):
    out, offset = [], 0
    while True:
        r = SESSION.get(f"https://api.smartrecruiters.com/v1/companies/{c['slug']}"
                        f"/postings?limit=100&offset={offset}", timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        items = data.get("content", [])
        for j in items:
            loc = j.get("location") or {}
            out.append(_norm(c["name"], j.get("name"),
                             ", ".join(x for x in [loc.get("city"), loc.get("country")] if x),
                             (j.get("ref") or "").replace("api.smartrecruiters.com/v1",
                                                          "jobs.smartrecruiters.com"),
                             j.get("releasedDate"), "", j.get("id")))
        offset += len(items)
        if not items or offset >= data.get("totalFound", 0):
            break
    return out


def fetch_workday(c):
    endpoint = f"https://{c['host']}/wday/cxs/{c['tenant']}/{c['site']}/jobs"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    seen, out = set(), []
    for term in WORKDAY_SEARCHES:
        offset = 0
        while True:
            body = {"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": term}
            r = SESSION.post(endpoint, json=body, headers=headers, timeout=TIMEOUT)
            r.raise_for_status()
            data = r.json()
            posts = data.get("jobPostings", [])
            for j in posts:
                path = j.get("externalPath", "")
                if path in seen:
                    continue
                seen.add(path)
                out.append(_norm(c["name"], j.get("title"), j.get("locationsText", ""),
                                 f"https://{c['host']}/{c['site']}{path}",
                                 j.get("postedOn", ""),
                                 " ".join(j.get("bulletFields") or []), path))
            offset += len(posts)
            if not posts or offset >= data.get("total", 0) or offset > 300:
                break
            time.sleep(0.35)
    return out


ADAPTERS = {"greenhouse": fetch_greenhouse, "lever": fetch_lever, "ashby": fetch_ashby,
            "smartrec": fetch_smartrec, "workday": fetch_workday}


# --------------------------------------------------------------------------
# PIPELINE
# --------------------------------------------------------------------------
def job_key(j):
    raw = f"{j['company']}|{re.sub(r'[^a-z0-9]', '', j['title'].lower())}|{j['location'].lower()}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def clean_posted(val):
    """Workday gives 'Posted 3 Days Ago'. Convert what we can to a date."""
    if not val:
        return None
    s = str(val)
    iso = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    if iso:
        return iso.group(1)
    m = re.search(r"(\d+)\+?\s*(day|week|month)s?\s*ago", s, re.I)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        days = n * {"day": 1, "week": 7, "month": 30}[unit]
        return (dt.date.today() - dt.timedelta(days=days)).isoformat()
    if re.search(r"posted today|just posted", s, re.I):
        return dt.date.today().isoformat()
    return None


def collect():
    rows, errors, by_key = [], [], {}
    for c in COMPANIES:
        fn = ADAPTERS.get(c["kind"])
        if not fn:
            errors.append((c["name"], f"unknown ATS '{c['kind']}'"))
            continue
        try:
            jobs = fn(c)
        except Exception as e:
            errors.append((c["name"], f"{type(e).__name__}: {e}"))
            print(f"  FAIL  {c['name']}")
            continue
        kept = 0
        for j in jobs:
            cat = categorise(j["title"], j["description"])
            if not cat:
                continue
            k = job_key(j)
            if k in by_key:
                continue
            row = {"key": k, "company": j["company"], "title": j["title"],
                   "location": j["location"], "url": j["url"],
                   "category": cat, "posted": clean_posted(j["posted"])}
            by_key[k] = row
            rows.append(row)
            kept += 1
        print(f"  ok    {c['name']:<20} {len(jobs):>4} postings -> {kept} kept")
    return rows, errors


def run():
    print("Fetching...\n")
    rows, errors = collect()

    # first_seen lets the site show a NEW badge
    prev_path = OUT / "jobs.json"
    prev = {}
    if prev_path.exists():
        try:
            prev = {r["key"]: r for r in json.loads(prev_path.read_text())["jobs"]}
        except Exception:
            pass
    today = dt.date.today().isoformat()
    new_count = 0
    for r in rows:
        r["first_seen"] = prev.get(r["key"], {}).get("first_seen", today)
        if r["first_seen"] == today and prev:
            new_count += 1

    rows.sort(key=lambda r: (r["first_seen"], r["company"]), reverse=True)
    payload = {"updated": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
               "count": len(rows), "jobs": rows}
    prev_path.write_text(json.dumps(payload, indent=1))

    tally = {}
    for r in rows:
        tally[r["category"]] = tally.get(r["category"], 0) + 1
    print(f"\n{len(rows)} roles ({', '.join(f'{v} {k}' for k, v in sorted(tally.items()))})")
    print(f"{new_count} added today")
    if errors:
        print("\nNeeds fixing:")
        for n, e in errors:
            print(f"  {n}: {e[:80]}")
    print(f"\nWrote {prev_path}")


def verify():
    print("Testing endpoints...\n")
    bad = []
    for c in COMPANIES:
        try:
            n = len(ADAPTERS[c["kind"]](c))
            print(f"  ok    {c['name']:<20} {n} postings")
        except Exception as e:
            print(f"  FAIL  {c['name']:<20} {type(e).__name__}: {str(e)[:60]}")
            bad.append(c["name"])
    print(f"\n{len(COMPANIES) - len(bad)} working. Fix: {', '.join(bad) or 'none'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "verify"])
    a = ap.parse_args()
    run() if a.cmd == "run" else verify()
