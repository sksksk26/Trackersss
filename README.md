# UK finance early-careers tracker

A self-updating job board for off-cycle, graduate, summer and placement roles.
Reads directly from the application systems banks and funds post on, so no
Python needs to run on your machine — GitHub does it for free, three times a day.

## Setup (about 15 minutes)

**1. Make the repo.** New public repo on GitHub, upload these files, keeping the
folder structure.

**2. Turn on Pages.** Settings → Pages → Source: *Deploy from a branch* →
Branch: `main`, folder: `/docs` → Save. Your site appears at
`https://<your-username>.github.io/<repo-name>/` within a minute or two.

**3. Allow the workflow to commit.** Settings → Actions → General → scroll to
*Workflow permissions* → select *Read and write permissions* → Save. Without
this the scraper runs but can't save what it finds.

**4. First run.** Actions tab → *Refresh job board* → *Run workflow*. Takes two
or three minutes. Open the run log to see which companies worked.

**5. Fix the broken slugs.** Some will fail on the first run — the log names
them. `scrape.py` explains how to find the correct value for each system. Edit
the `COMPANIES` list, commit, run again.

From then on it updates on its own at 06:00, 12:00 and 18:00 UTC.

## Running it locally instead

Only needed if you want to test changes before pushing:

```
pip install -r requirements.txt
python scrape.py verify     # check which endpoints work
python scrape.py run        # fetch and write docs/jobs.json
```

Then open `docs/index.html` through a local server (`python -m http.server`
inside `docs/`), not by double-clicking it — browsers block the data file
otherwise.

## Adding companies

Each entry in `COMPANIES` needs a `name` and a `kind`. Greenhouse, Lever, Ashby
and SmartRecruiters take a `slug`; Workday takes `host`, `tenant` and `site`.
The comments at the top of `scrape.py` show where to find each.

The gap worth filling is UK mid-market and smaller boutiques — that's where
off-cycles are most common and where the existing trackers are thinnest.

## How roles are sorted

Titles are matched against keyword sets, then checked for finance relevance.
Experienced-hire titles (VP, Director, Senior) and spring weeks are dropped.
If something lands in the wrong bucket, adjust the pattern lists in `scrape.py`
— they're plain regex and near the top of the file.

`first_seen` is recorded the first time a role appears, which is what drives the
green edge and the "added this week" count. Delete `docs/jobs.json` and
everything looks new again.
