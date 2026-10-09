"""Clean and standardize the raw book-tracker CSV in data/ for downstream use.

Handles: blank -> NaN normalization, duplicate rows, inconsistent author
separators ("and" / "&"), inconsistent genre delimiters/casing, messy
mixed-format dates (exact dates, day-month without a year, and fuzzy
references like "early jan"), and numeric/boolean typing.

Usage:
    uv run python scripts/clean_books_data.py
"""
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.book_dates import parse_date

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_PATH = DATA_DIR / "Book Tracker - Sheet1.csv"
CLEAN_CSV_PATH = DATA_DIR / "books_clean.csv"
CLEAN_PARQUET_PATH = DATA_DIR / "books_clean.parquet"

def clean_genres(raw) -> str | float:
    if pd.isna(raw):
        return pd.NA
    tags = sorted({tag.strip().lower() for tag in re.split(r"[/,]", raw) if tag.strip()})
    return ", ".join(tags) if tags else pd.NA


def clean_books(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    text_cols = ["title", "author", "genre", "start_date", "end_date"]
    for col in text_cols:
        df[col] = df[col].astype(str).str.strip().replace({"": pd.NA, "nan": pd.NA})

    df = df.dropna(subset=["title"])

    # Some books have two rows: a bare "want to read" entry (title/author
    # only) and a fully filled-in one added after finishing it. Keep the
    # most complete row per (title, author) rather than just the first.
    dedup_key = df["title"].str.lower() + "|" + df["author"].fillna("").str.lower()
    completeness = df.notna().sum(axis=1)
    df = (
        df.assign(_dedup_key=dedup_key, _completeness=completeness)
        .sort_values("_completeness", ascending=False)
        .drop_duplicates(subset="_dedup_key", keep="first")
        .drop(columns=["_dedup_key", "_completeness"])
        .sort_index()
        .reset_index(drop=True)
    )

    df["author"] = (
        df["author"]
        .str.replace(r"\s*&\s*", ", ", regex=True)
        # optional leading ", " swallows an existing Oxford comma (e.g. "X, Y,
        # and Z") so it doesn't become a double comma after this substitution
        .str.replace(r"(,\s*)?\s+and\s+", ", ", regex=True)
    )
    df["genre"] = df["genre"].apply(clean_genres)

    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df["page_count"] = pd.to_numeric(df["page_count"], errors="coerce").astype("Int64")
    df["audiobook"] = df["audiobook"].astype(str).str.strip().str.lower().eq("yes")

    df["start_date_raw"] = df["start_date"]
    df["end_date_raw"] = df["end_date"]
    df["start_date"] = [parse_date(r, y) for r, y in zip(df["start_date_raw"], df["year"])]
    df["end_date"] = [parse_date(r, y) for r, y in zip(df["end_date_raw"], df["year"])]

    inferred_year = df["end_date"].dt.year.fillna(df["start_date"].dt.year)
    df["year"] = df["year"].fillna(inferred_year.astype("Int64"))

    return df[
        [
            "title", "author", "genre", "start_date", "end_date",
            "year", "page_count", "audiobook", "start_date_raw", "end_date_raw",
        ]
    ]


def main() -> None:
    df = pd.read_csv(RAW_PATH, encoding="utf-8-sig")
    cleaned = clean_books(df)

    cleaned.to_csv(CLEAN_CSV_PATH, index=False)
    cleaned.to_parquet(CLEAN_PARQUET_PATH, index=False)

    print(f"Cleaned {len(cleaned)} rows (from {len(df)} raw rows) -> {CLEAN_CSV_PATH}")

    unparsed = (cleaned["start_date"].isna() & cleaned["start_date_raw"].notna()) | (
        cleaned["end_date"].isna() & cleaned["end_date_raw"].notna()
    )
    if unparsed.any():
        print(f"\n{unparsed.sum()} row(s) have a date that couldn't be parsed (raw text kept):")
        print(
            cleaned.loc[unparsed, ["title", "start_date_raw", "end_date_raw"]].to_string(
                index=False
            )
        )


if __name__ == "__main__":
    main()
