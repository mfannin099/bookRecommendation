"""Pull the most recent tracked books from the Google Sheet and run the
recommender on them.

Needs GOOGLE_SHEET_ID in the environment or a gitignored .env (see
.env.example). Results go to
data/recommendations/matt_book_recommendations_<YYYY-MM-DD>_<genres>.csv;
that directory is gitignored. Genres default to machine learning, data and
business; pass --genres "" to run with none.

Usage:
    uv run python scripts/sync_from_sheet.py --dry-run     # just list the books
    uv run python scripts/sync_from_sheet.py
    uv run python scripts/sync_from_sheet.py --n 30 --genres golf,business
    uv run python scripts/sync_from_sheet.py --genres ""                  # no genre steering
"""
import argparse
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.book_columns import first_author
from utils.recommender import BookRecommender
from utils.sheets_client import (
    DEFAULT_BOOKS,
    MAX_BOOKS,
    SheetSyncError,
    fetch_sheet,
    recent_tracked_books,
    validate_n,
)

OUTPUT_DIR = ROOT / "data" / "recommendations"
DEFAULT_GENRES = "machine learning,data,business"


def _n_arg(value: str) -> int:
    try:
        return validate_n(int(value))
    except (ValueError, SheetSyncError):
        raise argparse.ArgumentTypeError(f"must be a whole number from 1 to {MAX_BOOKS} (got {value!r})") from None


def output_path(genre_keywords: list[str], today: date) -> Path:
    """matt_book_recommendations_<date>[_<genre>_<genre>...].csv, with each
    genre slugged to filename-safe lowercase (spaces become hyphens)."""
    parts = ["matt_book_recommendations", f"{today:%Y-%m-%d}"]
    parts += [re.sub(r"[^a-z0-9]+", "-", g.lower()).strip("-") for g in genre_keywords]
    return OUTPUT_DIR / ("_".join(p for p in parts if p) + ".csv")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--n", type=_n_arg, default=DEFAULT_BOOKS, metavar=f"1-{MAX_BOOKS}",
        help=f"how many recent books to look back (default {DEFAULT_BOOKS}, max {MAX_BOOKS})",
    )
    parser.add_argument(
        "--genres", default=DEFAULT_GENRES,
        help=f'comma-separated keywords to steer results (default "{DEFAULT_GENRES}"; "" for none)',
    )
    parser.add_argument("--dry-run", action="store_true", help="list the books and stop; no recommendations")
    args = parser.parse_args()

    try:
        books = recent_tracked_books(fetch_sheet(), args.n)
    except SheetSyncError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"{len(books)} most recent tracked books (oldest first):")
    for row in books.itertuples():
        finished = f"{row.end_date:%Y-%m-%d}" if pd.notna(row.end_date) else "(no end date)"
        print(f"  {finished:<13} {row.title}  --  {row.author}")
    if args.dry_run:
        return 0
    if books.empty:
        print("Error: no tracked books found in the sheet.", file=sys.stderr)
        return 1

    genre_keywords = [g.strip() for g in args.genres.split(",") if g.strip()]
    recommender = BookRecommender(
        # Co-authored books: look up by the first author only (see first_author).
        books=[(title, first_author(author)) for title, author in zip(books["title"], books["author"])],
        force_run=True,
        genre_keywords=genre_keywords,
    )
    recommendations = recommender.get_recommendations()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = output_path(genre_keywords, date.today())
    recommendations.to_csv(out_path, index=False)

    print(f"\nBased on {recommender.matched_book_count} of {recommender.total_book_count} books.")
    print(recommendations[["title", "authors", "similarity"]].to_string(index=False))
    print(f"\nWrote {out_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
