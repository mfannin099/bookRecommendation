# Book Recommendation

Recommends new books based on the ones you've read. It looks up each book on Open
Library (falling back to Wikipedia, then Apple's iTunes Search API, when Open
Library has no description), builds a taste profile from those descriptions,
searches Open Library for similar unread books, and ranks them by similarity. All
sources are free and keyless.

Two ways to use it:

1. **Web app** (`main.py`) — type or upload a book list, get recommendations in the
   browser. Nothing is saved between restarts.
2. **Weekly automation** (`scripts/sync_from_sheet.py` + GitHub Actions) — reads your
   reading-log Google Sheet and, every Saturday, commits two fresh recommendation
   CSVs to a `results` branch. Your laptop doesn't need to be on.

**Status:** feature-complete. See [Limitations](#known-limitations) and
[ideas not built](#ideas-not-built).

## Setup

```bash
uv sync          # uv manages the virtualenv; no API keys needed for the web app
uv run pytest    # 47 offline tests
```

## Web app

```bash
uv run python main.py        # http://localhost:5001
```

- **Add books** one at a time on the homepage, or **upload** `.csv`/`.xlsx` (title +
  author columns; aliases like `book title`, `authors` work) or `.txt` (one
  `Title - Author` per line). Duplicates are skipped and counted in a banner.
- **Get Recommendations** runs the pipeline and shows "Based on N of M books"
  (how many had a usable description). An optional "steer toward genre" field
  (e.g. `golf, business`) nudges results without changing your list.
- Returns 10 results. Weak matches are dropped, not padded in.
- Your list lives in memory only; keep your own `.csv` to re-upload.
- `/recommend` is slow (minutes): it makes 150–250 rate-limited network calls.

Other scripts:

| Script | Purpose |
|---|---|
| `quick_start.py` | Run the pipeline on a hardcoded list, no browser. |
| `scripts/clean_books_data.py` | Idempotently re-clean `data/recent_20_books.csv`. |
| `scripts/test_metadata_coverage.py` | Measure how many of those books get a description from each source (currently ~70%). |

## Syncing from a Google Sheet

`scripts/sync_from_sheet.py` takes your most recent books from the sheet, runs the
recommender, and writes
`data/recommendations/matt_book_recommendations_<date>_<genres>.csv` (gitignored).

**Setup**

1. Share the sheet as **Anyone with the link: Viewer** (no Google login needed). It
   needs a title column, an author column, `end_date`, and ideally `start_date` and
   `year`.
2. `cp .env.example .env` and set `GOOGLE_SHEET_ID` (the string between `/d/` and
   `/edit` in the sheet URL). Optional: `GOOGLE_SHEET_GID` for a tab other than the
   first.

> **Keep the sheet ID out of Git.** On a link-shared sheet the ID is the password.
> It's read only from the environment and never logged or put in error messages.
> Check before pushing: `git ls-files -co --exclude-standard | xargs grep -l "<id>"`
> should print nothing.

```bash
uv run python scripts/sync_from_sheet.py --dry-run     # list the books it would use
uv run python scripts/sync_from_sheet.py              # defaults
uv run python scripts/sync_from_sheet.py --n 30 --top 20 --genres "golf,business"
```

| Flag | Default | Meaning |
|---|---|---|
| `--n` | 20 (max 50) | Recent books to look back. |
| `--top` | 15 (max 50) | Recommendations to return. |
| `--genres` | `analytics,strategy,business,data` | Topic keywords; `""` for none. |
| `--dry-run` | off | List the books and stop. |

A full run takes ~5 minutes. Failures print one `Error: ...` line and exit 1.

**Which books:** the last `n` rows, in sheet order, that have a `year` or a parseable
date (so undated "want to read" rows are ignored, but an audiobook with only a year
counts). Rows missing a title or author are skipped; duplicates keep the latest.
Messy dates (`13-Feb`, `6/16/25`, `6-Sept`) are parsed against the `year` column.
Co-authored books are looked up by their **first author**, because Wikipedia and
iTunes need the author string to match exactly (the CSV still shows all authors).

**Genre keywords** are added to the taste profile and to the Open Library search,
which requires *all* terms to match, so more keywords means *fewer* candidates.
Concrete topic nouns beat umbrella labels. Tried on a 30-book profile:

| Keywords | Result |
|---|---|
| `analytics,strategy,business,data` | Best, ~13/15 on topic (default) |
| `data,business` | Good, weaker tail |
| `habits,discipline,mindset` | Improved (*Atomic Habits* first), thin tail |
| `machine learning,data,business` | On topic but all academic textbooks |
| `motivation,productivity`, `psychology,self-help` | Weak, ~2/10 on topic |

**Output columns:** `title, subtitle, authors, description, similarity, matched_terms,
matched_subjects`.

## Weekly automation

`.github/workflows/weekly-recommendations.yml` runs **Saturdays at 12:17 UTC** (8:17
AM EDT; 7:17 AM after Nov 1 since cron ignores daylight saving — use `17 13` to
keep 8:17 AM). You can also start it from the Actions tab (**Run workflow**, optional
`n`, default 30). One job, up to 60 minutes:

1. install, run the tests, check the `GOOGLE_SHEET_ID` secret exists;
2. run the sync with the default genres;
3. run it again with `habits,discipline,mindset` (still runs if step 2 failed);
4. commit both CSVs to the **`results`** branch under `recommendations/`.

**Setup:** add the repository secret `GOOGLE_SHEET_ID` (Settings → Secrets and
variables → Actions). Nothing else is needed.

**The `results` branch** is created on the first run, has its own history, and is
written only by the workflow — never merge `master` into it. Each run adds one commit
with two new files. View it at
`github.com/mfannin099/bookRecommendation/tree/results/recommendations`, or locally:
`git fetch origin results && git ls-tree -r --name-only origin/results`.

**Privacy:** the repo is public, so logs and `results` show your recent book titles,
authors and finish dates plus the recommendations — never the sheet ID or other
columns. Making the repo private would hide them.

**Timing:** GitHub scheduled runs are best-effort. Here, the first slot never fired
and a test slot ran about 4 hours late (then succeeded in ~10 min). Expect hours of
delay and the occasional skipped week; GitHub shows no "next run" view and may
disable schedules after ~60 days without repo activity. Use **Run workflow** to get
results on demand.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `GOOGLE_SHEET_ID is not set` | Create `.env` (local) or add the repo secret (CI). |
| `HTTP 404` | Wrong sheet ID or `GOOGLE_SHEET_GID`. |
| `returned a web page instead of CSV` | Sheet isn't shared as "Anyone with the link: Viewer". |
| `Sheet is missing expected columns` | Header changed; need title, author and `end_date`. |
| "Based on 20 of 30 books" | Normal: title typos in the sheet (capitalization is ignored) or books missing from all sources. |
| Lookup `500` / timeout | Open Library is flaky; that lookup is skipped, so results vary slightly. |
| Saturday run missing | Wait a few hours, then use **Run workflow**. |
| Unrelated novels in the list | The keywords found few candidates; try different or fewer, more concrete ones. |

## Project layout

```
main.py                    Flask app
quick_start.py             CLI runner for a hardcoded list
utils/
  recommender.py           BookRecommender: lookup -> TF-IDF profile -> candidates -> ranking
  metadata_client.py       Open Library / Wikipedia / iTunes lookups
  sheets_client.py         reads the sheet CSV, picks the last n tracked books
  book_columns.py          column aliases, dedupe key, first_author()
  book_dates.py            parse_date() for the sheet's messy dates
scripts/                   sync_from_sheet, clean_books_data, test_metadata_coverage
tests/                     offline tests (selection rules, dates, filenames, CLI, filters)
data/recent_20_books.csv   fixture; data/recommendations/ is generated and gitignored
.github/workflows/         weekly-recommendations.yml
CLAUDE.md                  detailed architecture notes
```

`master` holds all code; `results` is automation-only.

## Why Open Library, and two fallbacks

Open Library needs no key and has no rate limit, but its descriptions are patchy:
alone it covered ~36% of a 236-book test library. Wikipedia and iTunes (ebooks) were
added as free, keyless fallbacks (Google Books' keyless access is disabled). They
complement each other: iTunes covers current commercial nonfiction, Wikipedia and
Open Library catch niche titles. Together they cover ~70% of the sample in
`data/recent_20_books.csv` (30% Open Library, 15% Wikipedia, 25% iTunes).

Lookups run on a bounded thread pool (5 workers) through one shared
`requests.Session`, with built-in pauses per source (0.2 s Open Library, 0.5 s
Wikipedia, 1.0 s iTunes). To try one lookup:

```python
from utils.metadata_client import MetadataClient
r = MetadataClient().fetch("Why Machines Learn", "Anil Ananthaswamy")
print(r["source"], r["description"])   # None if all three miss
```

## Design decisions

- **Sheet read as public CSV:** no credentials or Cloud project; the tradeoff is that
  the ID is the only protection, so it lives only in `.env` / a GitHub secret.
- **"Tracked" rows, sheet order:** detailed tracking began partway down the sheet, so
  anything with a year or date counts, including undated audiobooks.
- **First author for lookups** (see above).
- **Generic Open Library subjects ignored** for candidate discovery (`Books`,
  `Nonfiction`, `History`, `Biography`, catalog tags): "most popular books tagged
  History" returned the same crowd-pleasers (*Shoe Dog*, *Born a Crime*) for every
  profile. Its effect was not measured separately.
- **Separate `results` branch:** bot commits stay out of code history and can't
  conflict with yours.
- **One job, two sequential runs:** parallel jobs would race to push the same branch.
- **Cron at minute 17:** avoids GitHub's busiest slot (the top of the hour).
- **Stateless web app:** no database; nothing survives a restart.

## Known limitations

- ~30% of books get no description even when spelled correctly (e.g. *Broken Supply
  Chains*); fixing the sheet can't help.
- Ranking is TF-IDF word overlap, so it can't match synonyms and generic words can
  pull in unrelated popular books (the "filler tail").
- Near-duplicate editions with very different title lengths can both appear.
- The web app returns 10 results and doesn't use first-author lookup.
- Placeholder authors in the sheet (e.g. "Many Authors") can't match anything.
- `pyarrow` in `pyproject.toml` is unused and can be removed.

## Ideas not built

Text-embedding ranking (biggest likely quality gain; evaluate by hiding the 5 newest
books and checking their rank), a fourth metadata source with an API key, recency
weighting, email notifications, a lookup cache, and a backup cron (it would
double-publish when both fire).

## Tech stack

Flask, pandas, scikit-learn (TF-IDF, cosine similarity), thefuzz, requests,
python-dotenv, pytest, uv, GitHub Actions. Python 3.10+.
