# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

This project uses [uv](https://docs.astral.sh/uv/) for dependency management (no virtualenv/pip workflow, no Docker). Dependencies are declared in `pyproject.toml` and pinned in `uv.lock`.

Setup:
```bash
uv sync
```

No API key or `.env` file needed — all three metadata sources (Open Library, Wikipedia, iTunes) are free and keyless. Open Library alone only found descriptions for ~36% of a 236-book test library (measured before any fallback existed). With all three sources and current (typo-fixed) data, coverage on the 58-book accurately-tracked tail of `data/books_clean.csv` is 71% (28% Open Library + 19% Wikipedia + 24% iTunes) — see `scripts/test_metadata_coverage.py` to re-measure after further data or code changes.

Run the Flask app (dev):
```bash
uv run python main.py        # serves on 0.0.0.0:5001
```

Run the recommender standalone, outside the web UI (against the hardcoded `BOOKS` list at the top of the file):
```bash
uv run python quick_start.py
```

Add a new dependency:
```bash
uv add <package>
```

Clean the raw personal book-tracker CSV (`data/Book Tracker - Sheet1.csv`) into `data/books_clean.csv` / `data/books_clean.parquet`:
```bash
uv run python scripts/clean_books_data.py
```

Measure `MetadataClient` description coverage (Open Library vs. Wikipedia fallback vs. not found) against the accurately-tracked tail of `data/books_clean.csv` (everything from "Why Machines learn" onward — earlier rows were reconstructed from memory and aren't reliable test data):
```bash
uv run python scripts/test_metadata_coverage.py
```

There is no other test suite, linter, or build step configured in this repo.

## Architecture

Three-part app: a stateless-ish Flask frontend (`main.py`), a metadata lookup client (`utils/metadata_client.py`), and a recommendation engine (`utils/recommender.py`) built on top of it.

**State handling (`main.py`):** The book/author list the user builds up isn't stored in a database or on disk at all — it's held purely in the module-level `book_list`/`author_list` globals (position-paired: index N of one corresponds to index N of the other), so this app is designed for a single ephemeral session, not multi-user persistence, and nothing survives a restart. Routes: `/` (add/list entries), `/upload` (bulk-add from one or more uploaded `.csv`/`.xlsx`/`.txt` files — parsed by `parse_book_file`), `/edit`, `/delete`, `/clear`, and `/recommend` (triggers the recommendation pipeline and renders `recommend.html`). `/recommend` passes `list(zip(book_list, author_list))` straight into `BookRecommender(books=...)` — no file round-trip.

Both the manual-add form and `/upload` dedupe against the existing list via `_dedupe_key(title, author)` (case-insensitive exact match on the pair) before appending — duplicates are skipped rather than silently added, since a duplicate read-book double-weights that book's vocabulary in the TF-IDF profile, not just clutters the list. `/upload` reports counts back via `redirect(f'/?added={added}&skipped={skipped}')`, which `index.html` reads from `request.args` to show a one-line summary (no session/flash machinery needed). All error paths (`/upload`'s bad-file-type/missing-columns/parse failures, `/recommend`'s "no books yet") render `error.html` for a consistent, auto-redirecting error page instead of raw inline HTML strings.

`parse_book_file`'s `.txt` format splits each `Title - Author` line on the *last* `" - "` (`rsplit`), not the first — a subtitled title containing its own `" - "` (e.g. "Chip War - The Fight for the World's Most Critical Technology") would otherwise get split in the wrong place, since an author name essentially never contains `" - "` but a nonfiction subtitle commonly does.

**Metadata lookup (`utils/metadata_client.py`):** `MetadataClient.fetch(title, author)` tries three sources in order, stopping at the first usable description: Open Library (`fetch_from_open_library` — search by title/author, then fetch the work's `description`/`subjects`), Wikipedia (`fetch_from_wikipedia`), then Apple's iTunes Search API / ebook listings (`fetch_from_itunes`). Both fallbacks do a loose free-text search that can return a wrong-but-plausible page/listing rather than no result, so both validate before trusting a match: Wikipedia requires the author's name to appear in the returned page's lead-section extract; iTunes requires *both* the author's name to appear in the listing's `artistName` *and* the title to fuzzy-match (`thefuzz`, `ITUNES_TITLE_MATCH_THRESHOLD = 70`) the listing's `trackName` — author-only matching isn't enough for iTunes since it can surface a different book by the same author (a companion/summary title, another edition) that an author check alone wouldn't catch. iTunes descriptions are HTML-formatted marketing copy, cleaned via `_strip_html` (strip tags, unescape entities, collapse whitespace) before use. `_wikipedia_get` retries with backoff on Wikipedia's 429 rate limit; iTunes has no documented rate limit or a clean signal to react to if one is hit, so `itunes_pause` (default 1.0s) is a flat, conservative guess rather than adaptive backoff. No API key needed for any of the three sources. `MetadataClient.fetch` sleeps `open_library_pause` (default 0.2s, a light courtesy delay — Open Library has no documented rate limit) before the Open Library attempt, and `wikipedia_pause` (default 0.5s) before falling back to Wikipedia. All request call sites (`fetch_from_open_library` x2, `_wikipedia_get`, `fetch_from_itunes`, `search_open_library_candidates`) go through one module-level `_SESSION = requests.Session()` rather than bare `requests.get(...)`, so repeated requests reuse an already-open connection per host instead of a fresh TCP+TLS handshake each time — safe to share across the thread pool below since `requests`' underlying connection pool is internally lock-protected. `DEFAULT_HEADERS` (the descriptive User-Agent Wikipedia requires) is set on `_SESSION` once at module load rather than passed per-call. Even so, a full pipeline run is many requests over a real network — see "Why it's slow" in README.md. Also exposes `search_open_library_candidates(query)` for discovering new, not-yet-read books.

**Recommendation pipeline (`utils/recommender.py`, `BookRecommender` class):** `BookRecommender(books=[(title, author), ...], ...)` takes the read-books list directly (no file paths — `titles_list`/`authors_list` are derived from `books` in `__init__`). `get_recommendations()` then runs these steps in order:
1. `load_or_build_library` — call `MetadataClient.fetch` for each (title, author) pair, or load a cached copy from `library.parquet` (skipped when `force_run=True`, which `main.py` always sets). The fetches run on a bounded `ThreadPoolExecutor` (`max_workers`, default 5, constructor param) rather than one at a time — each fetch is I/O-bound, so this cuts wall-clock time roughly `max_workers`-fold without materially increasing CPU/memory use. Lower `max_workers` on a more constrained machine; raise it for more speed at the cost of more concurrent load on Open Library/Wikipedia.
2. `clean_library` — drop books with no usable description, strip punctuation for TF-IDF.
3. `build_search_query` — TF-IDF (`scikit-learn`) over the cleaned descriptions to extract the top terms (default 3) as an Open Library search query. Kept small deliberately: Open Library's `q=` search is a strict AND across terms, so more than a handful collapses the result count to near zero.
4. `fetch_candidates` — search Open Library with that query, excluding anything fuzzy-matching (`thefuzz`, `already_read_match_score`, default 85) an already-read title, *and* excluding anything fuzzy-matching a candidate already kept this run — Open Library often returns the same work twice as separate editions differing only in case/whitespace (e.g. "The Man Who Loved China" / "the man who loved china"), which would otherwise occupy two of the final slots.
5. `enrich_candidates` — fetch descriptions (and subtitle, when present) for the surviving candidates via `MetadataClient`, same bounded thread pool as step 1. With `candidate_pool_size=40` by default, this step is the dominant cost in the whole pipeline.
6. `rank_candidates` — cosine similarity (`sklearn.metrics.pairwise.cosine_similarity`) between each candidate and the centroid of the read-books' TF-IDF vectors; candidates below `min_similarity` (default 0.05) are dropped rather than padding the result out to `top_n` regardless of match quality (a bare top-3-TF-IDF-term Open Library search can surface a spurious keyword-collision match — e.g. Ray Bradbury's *Death Is a Lonely Business* matching on the word "business" alone — that a similarity floor filters back out); returns up to `top_n` (default 10) as a DataFrame with `title`, `subtitle`, `authors`, a `description` snippet (truncated to ~240 chars at a word boundary), and the raw `similarity` score.

`MetadataClient` itself needed no changes to support this — `fetch()` only reads its own immutable `open_library_pause`/`wikipedia_pause` attributes and has no shared mutable state, so it's already safe to call concurrently from multiple threads.

Every call to `/recommend` rebuilds the library from the API rather than trusting the parquet cache (`force_run=True`), so the cache in `main.py`'s flow is effectively unused — it only matters when running `BookRecommender` directly (e.g. from `quick_start.py`) with `force_run=False`. `library.parquet` is gitignored (it's a rebuildable cache, not project data).

Templates (`templates/*.html`) are plain Jinja2 with no shared base template; `static/style.css` is the only styling. `notebooks/nltk_playground.ipynb` is a scratch notebook for NLP experimentation and isn't part of the app's runtime path.

**Data cleaning (`scripts/clean_books_data.py`):** Standalone script (unrelated to the Flask app's `/recommend` pipeline) that cleans a personal reading log at `data/Book Tracker - Sheet1.csv` (248 raw rows → 235 clean rows as of this writing). Notable quirk it handles: the raw sheet often has two rows per book — a bare "want to read" row (title/author only) and a fully filled-in row added after finishing it — so dedup keeps whichever row (by title+author, case-insensitive) has the most non-null fields, not just the first match. This dedup is exact-match on the lowercased title+author string, so a typo in either field on just one of the two rows defeats it silently (the pair survives as two rows instead of merging) — this happened for several books in the raw data before a typo-fixing pass corrected it. Author lists get `&`/`and` normalized to `, ` (regex handles an existing Oxford comma too, e.g. "X, Y, and Z" → "X, Y, Z", not "X, Y,, Z"). Dates are messy and mixed-format (`13-Feb`, `20-Apr-25`, `6/16/25`, `early jan`); `parse_date` resolves day-month-without-year using the row's `year` column and approximates fuzzy month references ("early/mid/late/end <month>") to day 5/15/25, leaving anything else (e.g. "after Christmas") as `NaT` with the original text preserved in `start_date_raw`/`end_date_raw`.
