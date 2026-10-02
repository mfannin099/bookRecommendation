# Book Recommendation

A Flask app that recommends new books based on the books you've already read. You
give it a list of titles/authors (typed in one at a time, or uploaded as a file),
and it looks up each one on Open Library (falling back to Wikipedia, then to
Apple's iTunes Search API, when Open Library doesn't have a description), builds
a taste profile from those descriptions, searches Open Library for similar books
you haven't read yet, and ranks the results by how similar they are to your
profile.

## Setup

This project uses [uv](https://docs.astral.sh/uv/) for dependency management —
no virtualenv/pip, no Docker.

```bash
uv sync
```

That's the only setup step. No API key or `.env` file is needed — all three
metadata sources (Open Library, Wikipedia, iTunes) are free and keyless.

## Running the web app

```bash
uv run python main.py        # serves on 0.0.0.0:5001
```

Then open `http://localhost:5001` in a browser. (Port 5001 was picked over the
Flask default of 5000 because on macOS, 5000 is usually taken by the AirPlay
Receiver. If 5001 is taken too, run on a different port instead:
`uv run python -c "from main import app; app.run(host='0.0.0.0', port=5002)"`.)

What you'll see:

1. **Homepage** (`/`) — a form to add one book (title + author) at a time, plus
   the running list of what you've added so far, with edit/delete controls next
   to each entry. Adding a book already in your list is a no-op (with a message
   saying so) rather than a silent duplicate.
2. **Upload** (`/upload`) — add many books at once instead of typing them in.
   Accepts multiple files per upload, any mix of:
   - `.csv` / `.xlsx` with a title column (`title`, `book`, `book title`, or
     `name`) and an author column (`author`, `authors`, `author name`, or
     `writer`) — case-insensitive, and comma-, semicolon-, or tab-separated
     `.csv` all work. The same shape as `data/books_clean.csv`, so you can
     upload that file directly. If the columns can't be found, the error
     message shows exactly what columns were detected so you can fix the file.
   - `.txt` with one `Title - Author` per line. If your title itself contains
     `" - "` (common in subtitled nonfiction, e.g. "Chip War - The Fight for
     the World's Most Critical Technology"), it's split on the *last*
     `" - "` in the line, since an author name essentially never contains one.
   After uploading, you'll see how many books were added and how many were
   skipped as duplicates of ones already in your list.
3. **Get Recommendations** (`/recommend`) — once your list has at least one book,
   this triggers the pipeline: look up each book's description, build a search
   query from the most distinctive terms across them, search Open Library for
   similar titles you haven't already read, and rank the results. Each result
   shows a description snippet, not just a bare title, and weak/spurious
   matches are dropped rather than padded in to fill out a round number of
   recommendations. There's also an optional "steer toward genre" field on
   this form — type a genre (or a few, comma-separated, e.g. "golf, business")
   to nudge results that direction without changing your actual reading list.
   It's a light touch by default: your own books still drive most of the
   signal, but it's enough to meaningfully shift results (tested: a reading
   list with no golf books at all still returned nearly all golf
   recommendations when "golf" was typed in). Leave it blank for today's
   behavior, typed fresh each time you click the button — nothing is saved.

Your list lives only in the running process's memory — nothing is written to
disk. **This app has no persistence across restarts**, by design. There's
nothing to log into and nothing to lose by restarting; if you want a list to
survive, keep your own copy as a `.csv` and re-upload it next time.

Expect `/recommend` to take a while (see "Why it's slow" below) — it's making
real, rate-limited network calls for every book in your list plus every
candidate it considers, one at a time.

## Scripts

These are the pieces you'd run yourself, outside the web UI, from a terminal in
the project root:

| Script | What it's for | Command |
|---|---|---|
| `quick_start.py` | Run the recommendation pipeline against a couple of hardcoded books (`BOOKS` list at the top of the file — edit it to try your own), no Flask/browser needed. Good for checking the pipeline still works end to end. | `uv run python quick_start.py` |
| `scripts/clean_books_data.py` | Turn your raw reading-log export (`data/Book Tracker - Sheet1.csv`) into the cleaned `data/books_clean.csv` / `.parquet` — dedupes rows, standardizes dates/genres. Run this after editing the raw sheet. | `uv run python scripts/clean_books_data.py` |
| `scripts/test_metadata_coverage.py` | Reports what fraction of your real reading history gets a usable description from Open Library vs. Wikipedia vs. iTunes vs. none. Useful after changing `utils/metadata_client.py` or the source data, to see whether coverage got better or worse. | `uv run python scripts/test_metadata_coverage.py` |

None of these take command-line arguments — settings (file paths, thresholds)
are constants near the top of each file if you need to change them.

## Using the metadata lookup directly

`utils/metadata_client.py` doesn't expose a web API of its own — it's a plain Python module
you call from code. If you want to test a single lookup without running the
whole app, drop into a Python shell in the project root:

```bash
uv run python
```

```python
from utils.metadata_client import MetadataClient

client = MetadataClient()
result = client.fetch("Why Machines Learn", "Anil Ananthaswamy")
print(result["source"])       # "open_library", "wikipedia", or "itunes"
print(result["description"])  # None if none of the three sources had a match
```

`fetch()` tries Open Library, then Wikipedia, then iTunes, stopping at the
first usable description; it returns `None` if all three miss. There's a
built-in pause before each network call (see "Why it's slow" below), so don't
loop this over a large list without expecting it to take a while.

## Why it's slow

The pipeline makes one live HTTP lookup per book it looks up metadata for —
every book in your reading list, *and* every candidate book it's considering
recommending (up to 40 by default). Each lookup has a built-in pause (0.2s
before the Open Library attempt, 0.5s more before falling back to Wikipedia,
1.0s more before falling back further to iTunes if Wikipedia also misses —
Open Library has no documented rate limit so it only needs a light courtesy
delay; Wikipedia does rate-limit and its fallback also means two extra
requests, plus up to 3 retries with backoff if it 429s; iTunes has no
documented rate limit *or* a clean signal to react to if one is hit, so its
pause is a flat, conservative guess rather than adaptive backoff). A single
`/recommend` call or `quick_start.py` run can still add up to 150-250+ network
requests total — that's expected, not a bug. It's a straightforward tradeoff
for using free, keyless APIs instead of a paid one with better rate limits.

These fetches now run concurrently rather than strictly one at a time:
`BookRecommender` uses a bounded thread pool (`max_workers`, default 5) for
both the read-books lookup and candidate enrichment, since each lookup is
independent and I/O-bound (mostly waiting on the network, not using CPU) —
cheap to parallelize even on a modest machine. Total request count is
unchanged, but up to `max_workers` of them are in flight at once instead of
strictly one-at-a-time, so wall-clock time drops roughly in proportion.
Pass a smaller `max_workers` to `BookRecommender(...)` on a more constrained
machine, or a larger one for more speed at the cost of more concurrent load
on Open Library/Wikipedia.

All of those lookups also go through one shared `requests.Session`
(`utils/metadata_client.py`) instead of opening a fresh connection per
request, so repeated requests to the same host reuse an already-open TCP/TLS
connection — a smaller, free win on top of the thread pool. Further levers
(skipping the Wikipedia fallback for candidates, caching lookups across
repeated `/recommend` calls) were considered and are still on the table if
this isn't fast enough.

## Key files

- `main.py` — the Flask app: routes for adding/uploading/editing/deleting books
  and triggering recommendations.
- `utils/recommender.py` — the `BookRecommender` class: the recommendation pipeline (metadata
  lookup → TF-IDF profile → Open Library candidate search → cosine-similarity
  ranking).
- `utils/metadata_client.py` — the Open Library / Wikipedia / iTunes lookup client shared by
  everything above (see "Using the metadata lookup directly").
- `scripts/clean_books_data.py` — cleans the raw personal reading-log export.
- `scripts/test_metadata_coverage.py` — measures description coverage against
  real reading history.
- `quick_start.py` — runs the recommender from the command line, no Flask UI.

## Why Open Library, and why two fallbacks

Open Library has no API key and no rate limit, which made it worth switching to
as the primary source. But its `description` field is inconsistently populated,
especially outside fiction — Open Library alone only found descriptions for
about **36% of a 236-book test library** (mostly business/self-help nonfiction),
measured before any fallback existed. Wikipedia and Apple's iTunes Search API
(ebook listings) were picked as those fallbacks (over Google Books, whose
keyless access is now hard-disabled — `quota_limit_value: 0` on every
unauthenticated request) because both are also free and keyless, with no
account or API key to manage. The two are complementary rather than redundant:
iTunes tends to cover current commercial nonfiction/self-help that Open Library
misses, while missing niche/technical titles Wikipedia or Open Library catch.
With all three sources and the current (typo-fixed) data, coverage on the
58-book accurately-tracked tail of `data/books_clean.csv` is **71%** (28%
Open Library + 19% Wikipedia + 24% iTunes) — up from 47% with just the
Wikipedia fallback. Run `scripts/test_metadata_coverage.py` any time to
re-measure it after further data or code changes.

## Tech stack

Flask, pandas, scikit-learn (TF-IDF + cosine similarity for ranking), thefuzz
(fuzzy title matching to exclude already-read books), requests, uv.
