# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

This project uses [uv](https://docs.astral.sh/uv/) for dependency management (no virtualenv/pip workflow, no Docker). Dependencies are declared in `pyproject.toml` and pinned in `uv.lock`.

Setup:
```bash
uv sync
```

Requires a `.env` file with `GOOGLE_BOOKS_API_KEY=<key>` (loaded via `python-dotenv` in `utils.py`).

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

There is no test suite, linter, or build step configured in this repo.

## Architecture

Two-part app: a stateless-ish Flask frontend (`main.py`) and a recommendation engine (`utils.py`).

**State handling (`main.py`):** The book/author list the user builds up isn't stored in a database — it's held in the module-level `book_list`/`author_list` globals and persisted to flat files (`data/titles.txt`, `data/authors.txt`), one entry per line. Files are wiped on both startup and process exit (`clear_data_files`, registered via `atexit`), so this app is designed for a single ephemeral session, not multi-user persistence. Routes: `/` (add/list entries), `/upload` (bulk-add from uploaded `.txt` files), `/edit`, `/delete`, `/clear`, and `/recommend` (triggers the recommendation pipeline and renders `recommend.html`).

**Recommendation pipeline (`utils.py`, `BookRecommender` class):** `get_recommendations()` runs these steps in order:
1. `read_data` — load the user's titles/authors from the data files.
2. `load_or_build_library` — for each (title, author) pair, hit the Google Books API (`fetch_book_from_google`) to pull metadata (description, categories, etc.), or load a cached copy from `library.parquet` (skipped when `force_run=True`, which `main.py` always sets).
3. `clean_and_filter_library` — fuzzy-match (`thefuzz`) each cached title back against the user's input titles to filter noise, keep only the last N books, and strip punctuation from descriptions.
4. `generate_search_query` — TF-IDF (`scikit-learn`) over the cleaned descriptions to extract the top keywords as a Google Books search query.
5. `fetch_recommendations` — issue that search query against the Google Books API to get a candidate pool.
6. `rank_by_jaccard_similarity` — score each candidate's description against the search query terms via Jaccard similarity and return the top 10 as a DataFrame.

Every call to `/recommend` rebuilds the library from the API rather than trusting the parquet cache (`force_run=True`), so the cache in `main.py`'s flow is effectively unused — it only matters when running `BookRecommender` directly (e.g. from `quick_start.py`) with `force_run=False`.

Templates (`templates/*.html`) are plain Jinja2 with no shared base template; `static/style.css` is the only styling. `notebooks/nltk_playground.ipynb` is a scratch notebook for NLP experimentation and isn't part of the app's runtime path.
