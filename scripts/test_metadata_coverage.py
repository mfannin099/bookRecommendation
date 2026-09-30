"""Measures MetadataClient description coverage (Open Library / Wikipedia /
not found) against the accurately-tracked tail of the reading history.

Everything before "Why Machines learn" in data/books_clean.csv was
reconstructed from memory rather than logged in real time, so it isn't
reliable test data -- this script only scores rows from that title onward.
"""
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from metadata import MetadataClient

BOOKS_CSV = Path(__file__).resolve().parent.parent / "data" / "books_clean.csv"
TEST_START_TITLE = "why machines learn"


def load_test_rows():
    df = pd.read_csv(BOOKS_CSV)
    start_idx = df.index[df["title"].str.lower() == TEST_START_TITLE][0]
    return df.iloc[start_idx:][["title", "author"]].dropna()


def main():
    rows = load_test_rows()
    client = MetadataClient(rate_limit_seconds=1)
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
