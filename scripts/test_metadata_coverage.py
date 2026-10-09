"""Measures MetadataClient description coverage (Open Library / Wikipedia /
iTunes / not found) against the books in data/recent_20_books.csv.

Those rows were logged in real time, so unlike older history they are
reliable test data. Authors go through first_author, exactly as the sheet sync
does, so this measures the lookups the sync actually performs.

Usage:
    uv run python scripts/test_metadata_coverage.py
"""
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.book_columns import first_author
from utils.metadata_client import MetadataClient

BOOKS_CSV = Path(__file__).resolve().parent.parent / "data" / "recent_20_books.csv"


def load_test_rows():
    df = pd.read_csv(BOOKS_CSV)[["title", "author"]].dropna()
    df["author"] = df["author"].map(first_author)
    return df


def main():
    rows = load_test_rows()
    client = MetadataClient()
    counts = Counter()

    for _, row in rows.iterrows():
        result = client.fetch(row["title"], row["author"])
        source = result["source"] if result else "none"
        counts[source] += 1
        print(f"{row['title']} ({row['author']}) -> {source}")

    total = sum(counts.values())
    found = total - counts["none"]

    print()
    print("=" * 50)
    print(f"Tested {total} books")
    for source, count in counts.most_common():
        print(f"  {source}: {count} ({count / total:.0%})")
    print(f"\nOverall coverage: {found}/{total} ({found / total:.0%})")


if __name__ == "__main__":
    main()
