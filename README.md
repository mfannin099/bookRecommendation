# Book Recommendation

A Flask app that recommends new books based on the books you've already read. You
give it a list of titles/authors (typed in one at a time, or uploaded as a file),
and it looks up each one on Open Library (falling back to Wikipedia when Open
Library doesn't have a description), builds a taste profile from those
descriptions, searches Open Library for similar books you haven't read yet, and
ranks the results by how similar they are to your profile.

## Setup

This project uses [uv](https://docs.astral.sh/uv/) for dependency management —
no virtualenv/pip, no Docker.

```bash
uv sync
```

That's the only setup step. No API key or `.env` file is needed — both metadata
sources (Open Library, Wikipedia) are free and keyless.

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
   to each entry.
2. **Upload** (`/upload`) — add many books at once instead of typing them in.
   Accepts multiple files per upload, any mix of:
   - `.csv` / `.xlsx` with `title` and `author` columns (case-insensitive) — the
     same shape as `data/books_clean.csv`, so you can upload that file directly.
   - `.txt` with one `Title - Author` per line.
3. **Get Recommendations** (`/recommend`) — once your list has at least one book,
   this triggers the pipeline: look up each book's description, build a search
   query from the most distinctive terms across them, search Open Library for
   similar titles you haven't already read, and rank the results.

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
| `scripts/test_metadata_coverage.py` | Reports what fraction of your real reading history gets a usable description from Open Library vs. Wikipedia vs. neither. Useful after changing `metadata.py` or the source data, to see whether coverage got better or worse. | `uv run python scripts/test_metadata_coverage.py` |

None of these take command-line arguments — settings (file paths, thresholds)
are constants near the top of each file if you need to change them.

## Using the metadata lookup directly

`metadata.py` doesn't expose a web API of its own — it's a plain Python module
you call from code. If you want to test a single lookup without running the
whole app, drop into a Python shell in the project root:

```bash
uv run python
```

```python
from metadata import MetadataClient

client = MetadataClient()
result = client.fetch("Why Machines Learn", "Anil Ananthaswamy")
print(result["source"])       # "open_library" or "wikipedia"
print(result["description"])  # None if neither source had a match
```

`fetch()` always tries Open Library first and only falls back to Wikipedia if
Open Library has no usable description; it returns `None` if neither source
finds one. There's a built-in pause before each network call (see "Why it's
slow" below), so don't loop this over a large list without expecting it to take
a while.

## Why it's slow

The pipeline makes one live HTTP lookup per book it looks up metadata for —
every book in your reading list, *and* every candidate book it's considering
recommending (up to 40 by default). Each lookup has a built-in pause (0.2s
before the Open Library attempt, 0.5s more before falling back to Wikipedia —
Open Library has no documented rate limit so it only needs a light courtesy
delay, but Wikipedia does rate-limit and its fallback also means two extra
requests, plus up to 3 retries with backoff if it 429s). A single `/recommend`
call or `quick_start.py` run can still add up to 80-150+ sequential network
requests — that's expected, not a bug. It's a straightforward tradeoff for
using free, keyless APIs instead of a paid one with better rate limits.

## Key files

- `main.py` — the Flask app: routes for adding/uploading/editing/deleting books
  and triggering recommendations.
- `utils.py` — the `BookRecommender` class: the recommendation pipeline (metadata
  lookup → TF-IDF profile → Open Library candidate search → cosine-similarity
  ranking).
- `metadata.py` — the Open Library / Wikipedia lookup client shared by
  everything above (see "Using the metadata lookup directly").
- `scripts/clean_books_data.py` — cleans the raw personal reading-log export.
- `scripts/test_metadata_coverage.py` — measures description coverage against
  real reading history.
- `quick_start.py` — runs the recommender from the command line, no Flask UI.

## Why Open Library, and why a Wikipedia fallback

Open Library has no API key and no rate limit, which made it worth switching to
as the primary source. But its `description` field is inconsistently populated,
especially outside fiction — Open Library alone only found descriptions for
about **36% of a 236-book test library** (mostly business/self-help nonfiction),
measured before any fallback existed. Wikipedia was picked as that fallback
(over Google Books) because it's also free and keyless — no API key to manage.
With the Wikipedia fallback and the current (typo-fixed) data, coverage on the
58-book accurately-tracked tail of `data/books_clean.csv` is **47%** (26%
Open Library + 21% Wikipedia) — run `scripts/test_metadata_coverage.py` any
time to re-measure it after further data or code changes.

## Tech stack

Flask, pandas, scikit-learn (TF-IDF + cosine similarity for ranking), thefuzz
(fuzzy title matching to exclude already-read books), requests, uv.
