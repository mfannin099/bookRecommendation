"""Build a metadata cache for every book in data/books_clean.csv.

Usage:
    uv run python scripts/build_profile_library.py             # full 236-book build
    uv run python scripts/build_profile_library.py --sample 50  # quick smoke test
"""
import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from metadata import MetadataClient

BOOKS_CLEAN_PATH = "data/books_clean.csv"
CACHE_PATH = "data/profile_library.parquet"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=None,
                         help="Only process a random N books (for quick testing).")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    books = pd.read_csv(BOOKS_CLEAN_PATH)
    books = books.dropna(subset=["title"])

    if args.sample:
        books = books.sample(n=min(args.sample, len(books)), random_state=args.seed)

    if os.path.exists(CACHE_PATH):
        cache = pd.read_parquet(CACHE_PATH)
    else:
        cache = pd.DataFrame(columns=[
            "title", "author", "subtitle", "authors", "publishedDate",
            "pageCount", "categories", "description", "source", "genre", "end_date",
        ])

    already_cached = set(zip(cache["title"].str.lower(), cache["author"].astype(str).str.lower()))

    client = MetadataClient()
    new_rows = []

    for _, row in books.iterrows():
        title = row["title"]
        author = str(row.get("author") or "")
        key = (str(title).lower(), author.lower())
        if key in already_cached:
            continue

        print(f"Fetching: {title} - {author}")
        result = client.fetch(title, author)
        if result is None:
            print(f"  no metadata found for '{title}'")
            continue

        result["title"] = title
        result["author"] = author
        result["genre"] = row.get("genre")
        result["end_date"] = row.get("end_date")
        new_rows.append(result)

    if new_rows:
        cache = pd.concat([cache, pd.DataFrame(new_rows)], ignore_index=True)
        cache.to_parquet(CACHE_PATH)

    print(f"\nCache now has {len(cache)} books "
          f"({(cache['source'] == 'open_library').sum()} Open Library, "
          f"{(cache['source'] == 'google_books').sum()} Google Books fallback).")


if __name__ == "__main__":
    main()
