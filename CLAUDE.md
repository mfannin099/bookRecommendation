# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

This project uses [uv](https://docs.astral.sh/uv/) for dependency management (no virtualenv/pip workflow, no Docker). Dependencies are declared in `pyproject.toml` and pinned in `uv.lock`.

Setup:
```bash
uv sync
```

Requires a `.env` file with `GOOGLE_BOOKS_API_KEY=<key>` (loaded via `python-dotenv` in `metadata.py`). The app runs without it, but Open Library alone only found descriptions for ~36% of a 236-book test library (measured directly, see README), so most real usage depends on the Google Books fallback firing.

Run the Flask app (dev):
```bash
uv run python main.py        # serves on 0.0.0.0:5000
```

Run the recommender standalone, outside the web UI (creates sample `data/titles.txt` and `data/authors.txt` if missing):
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

There is no test suite, linter, or build step configured in this repo.

## Architecture

Three-part app: a stateless-ish Flask frontend (`main.py`), a metadata lookup client (`metadata.py`), and a recommendation engine (`utils.py`) built on top of it.

**State handling (`main.py`):** The book/author list the user builds up isn't stored in a database — it's held in the module-level `book_list`/`author_list` globals and persisted to flat files (`data/titles.txt`, `data/authors.txt`), one entry per line. Files are wiped on both startup and process exit (`clear_data_files`, registered via `atexit`), so this app is designed for a single ephemeral session, not multi-user persistence. Routes: `/` (add/list entries), `/upload` (bulk-add from one or more uploaded `.csv`/`.xlsx`/`.txt` files — parsed by `parse_book_file`), `/edit`, `/delete`, `/clear`, and `/recommend` (triggers the recommendation pipeline and renders `recommend.html`).

**Metadata lookup (`metadata.py`):** `MetadataClient.fetch(title, author)` tries Open Library first (`fetch_from_open_library` — search by title/author, then fetch the work's `description`/`subjects`), and falls back to Google Books (`fetch_from_google_books`, uses `GOOGLE_BOOKS_API_KEY`) whenever Open Library has no work or no description. Also exposes `search_open_library_candidates(query)` for discovering new, not-yet-read books. Open Library was measured at ~36% description coverage alone on a 236-book test library — the Google Books fallback is load-bearing, not optional polish.

**Recommendation pipeline (`utils.py`, `BookRecommender` class):** `get_recommendations()` runs these steps in order:
1. `read_data` — load the user's titles/authors from the data files.
2. `load_or_build_library` — call `MetadataClient.fetch` for each (title, author) pair, or load a cached copy from `library.parquet` (skipped when `force_run=True`, which `main.py` always sets).
3. `clean_library` — drop books with no usable description, strip punctuation for TF-IDF.
4. `build_search_query` — TF-IDF (`scikit-learn`) over the cleaned descriptions to extract the top terms (default 3) as an Open Library search query. Kept small deliberately: Open Library's `q=` search is a strict AND across terms, so more than a handful collapses the result count to near zero.
5. `fetch_candidates` — search Open Library with that query, excluding anything fuzzy-matching (`thefuzz`) an already-read title.
6. `enrich_candidates` — fetch descriptions for the surviving candidates via `MetadataClient`.
7. `rank_candidates` — cosine similarity (`sklearn.metrics.pairwise.cosine_similarity`) between each candidate and the centroid of the read-books' TF-IDF vectors; returns the top 10 as a DataFrame.

Every call to `/recommend` rebuilds the library from the API rather than trusting the parquet cache (`force_run=True`), so the cache in `main.py`'s flow is effectively unused — it only matters when running `BookRecommender` directly (e.g. from `quick_start.py`) with `force_run=False`. `library.parquet` is gitignored (it's a rebuildable cache, not project data).

Templates (`templates/*.html`) are plain Jinja2 with no shared base template; `static/style.css` is the only styling. `notebooks/nltk_playground.ipynb` is a scratch notebook for NLP experimentation and isn't part of the app's runtime path.

**Data cleaning (`scripts/clean_books_data.py`):** Standalone script (unrelated to the Flask app's `/recommend` pipeline) that cleans a personal reading log at `data/Book Tracker - Sheet1.csv`. Notable quirk it handles: the raw sheet often has two rows per book — a bare "want to read" row (title/author only) and a fully filled-in row added after finishing it — so dedup keeps whichever row (by title+author, case-insensitive) has the most non-null fields, not just the first match. Dates are messy and mixed-format (`13-Feb`, `20-Apr-25`, `6/16/25`, `early jan`); `parse_date` resolves day-month-without-year using the row's `year` column and approximates fuzzy month references ("early/mid/late/end <month>") to day 5/15/25, leaving anything else (e.g. "after Christmas") as `NaT` with the original text preserved in `start_date_raw`/`end_date_raw`.
