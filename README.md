# Book Recommendation

A Flask app that recommends new books based on the books you've already read. You
give it a list of titles/authors (typed in one at a time, or uploaded as a file),
and it looks up each one on Open Library (falling back to Google Books when Open
Library doesn't have a description), builds a taste profile from those
descriptions, searches Open Library for similar books you haven't read yet, and
ranks the results by how similar they are to your profile.

## Setup

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
uv sync
```

Open Library alone only found descriptions for about **36% of a 236-book test
library** (mostly business/self-help nonfiction, a category Open Library covers
poorly). The Google Books fallback is what makes the rest of your library usable,
so create a `.env` file with a Google Books API key:

```
GOOGLE_BOOKS_API_KEY=<your key>
```

The app still runs without one — it'll just have far fewer books to build a profile
from.

## Running it

```bash
uv run python main.py        # serves on 0.0.0.0:5000
```

Then open `http://localhost:5000`. (If port 5000 is already taken — on macOS this
is usually the AirPlay Receiver — run with a different port instead:
`uv run python -c "from main import app; app.run(host='0.0.0.0', port=5001)"`.)

To run the recommender from the command line instead of the web UI (uses a couple
of sample books):

```bash
uv run python quick_start.py
```

## Building your book list

Two ways to add books, and you can mix both:

- **One at a time** — the form on the homepage.
- **Upload files** — accepts multiple files per upload, any mix of:
  - `.csv` / `.xlsx` with `title` and `author` columns (case-insensitive) — the
    same shape as `data/books_clean.csv`, so you can upload that file directly.
  - `.txt` with one `Title - Author` per line.

Hit "Get Recommendations" once your list is built. The app looks up each book,
builds a search query from the most distinctive terms across their descriptions,
and searches Open Library for similar titles you haven't already read.

## Key files

- `main.py` — the Flask app: routes for adding/uploading/editing/deleting books
  and triggering recommendations.
- `utils.py` — the `BookRecommender` class: the recommendation pipeline (metadata
  lookup → TF-IDF profile → Open Library candidate search → cosine-similarity
  ranking).
- `metadata.py` — the Open Library / Google Books lookup client shared by
  everything above.
- `scripts/clean_books_data.py` — a standalone script (unrelated to the Flask app)
  that cleans a personal reading-log export (`data/Book Tracker - Sheet1.csv`) into
  `data/books_clean.csv`.
- `quick_start.py` — runs the recommender from the command line, no Flask UI.

## Why Open Library, and why a fallback

Open Library has no API key and no rate limit, which made it worth switching to as
the primary source. But its `description` field is inconsistently populated,
especially outside fiction — the 36% figure above was measured directly against a
real 236-book reading history before deciding to keep the Google Books fallback
rather than relying on Open Library alone.

## Tech stack

Flask, pandas, scikit-learn (TF-IDF + cosine similarity for ranking), thefuzz
(fuzzy title matching to exclude already-read books), requests, uv.
