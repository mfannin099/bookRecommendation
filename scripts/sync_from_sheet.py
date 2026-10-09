"""Pull the most recent tracked books from the Google Sheet and run the
recommender on them.

Needs GOOGLE_SHEET_ID in the environment or a gitignored .env (see
.env.example). Results go to data/recommendations/latest.csv (plus a dated
copy); that directory is gitignored.

Usage:
    uv run python scripts/sync_from_sheet.py --dry-run     # just list the books
    uv run python scripts/sync_from_sheet.py
    uv run python scripts/sync_from_sheet.py --n 30 --genres golf,business
"""
import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.recommender import BookRecommender
from utils.sheets_client import (
    DEFAULT_BOOKS,
    MAX_BOOKS,
    SheetSyncError,
    fetch_sheet,
    recent_tracked_books,
)

OUTPUT_DIR = ROOT / "data" / "recommendations"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--n", type=int, default=DEFAULT_BOOKS, choices=range(1, MAX_BOOKS + 1), metavar=f"1-{MAX_BOOKS}",
        help=f"how many recent books to look back (default {DEFAULT_BOOKS}, max {MAX_BOOKS})",
    )
    parser.add_argument("--genres", default="", help="comma-separated genre keywords to steer results")
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
        books=list(zip(books["title"], books["author"])),
        force_run=True,
        genre_keywords=genre_keywords,
    )
    recommendations = recommender.get_recommendations()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    latest = OUTPUT_DIR / "latest.csv"
    dated = OUTPUT_DIR / f"{date.today():%Y-%m-%d}.csv"
    for path in (latest, dated):
        recommendations.to_csv(path, index=False)

    print(f"\nBased on {recommender.matched_book_count} of {recommender.total_book_count} books.")
    print(recommendations[["title", "authors", "similarity"]].to_string(index=False))
    print(f"\nWrote {latest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
