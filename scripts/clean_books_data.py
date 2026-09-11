"""Clean and standardize the raw book-tracker CSV in data/ for downstream use.

Handles: blank -> NaN normalization, duplicate rows, inconsistent author
separators ("and" / "&"), inconsistent genre delimiters/casing, messy
mixed-format dates (exact dates, day-month without a year, and fuzzy
references like "early jan"), and numeric/boolean typing.

Usage:
    uv run python scripts/clean_books_data.py
"""
import re
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_PATH = DATA_DIR / "Book Tracker - Sheet1.csv"
CLEAN_CSV_PATH = DATA_DIR / "books_clean.csv"
CLEAN_PARQUET_PATH = DATA_DIR / "books_clean.parquet"

MONTH_ALIASES = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
APPROX_DAY = {"early": 5, "mid": 15, "late": 25, "end": 28}

FUZZY_MONTH_RE = re.compile(r"^(early|mid|late|end)\s+([a-z]+)$")
DAY_MONTH_RE = re.compile(r"^(\d{1,2})[-/]([a-z]+)$")


def parse_date(raw, year) -> pd.Timestamp:
    """Best-effort parse of a messy date string into a Timestamp.

    Tries, in order: fuzzy month references ("early jan" -> day 5 of that
    month), day-month with no year token ("13-Feb", using the row's `year`
    column), then falls back to pandas' general parser for anything that
    already carries an explicit year ("20-Apr-25", "6/16/25"). Anything
    that still doesn't resolve (e.g. "after Christmas") is left as NaT.
    """
    if pd.isna(raw):
        return pd.NaT
    text = str(raw).strip().lower()
    if not text:
        return pd.NaT

    m = FUZZY_MONTH_RE.match(text)
    if m:
        month = MONTH_ALIASES.get(m.group(2)[:3])
        if month and pd.notna(year):
            return pd.Timestamp(year=int(year), month=month, day=APPROX_DAY[m.group(1)])
        return pd.NaT

    m = DAY_MONTH_RE.match(text)
    if m:
        month = MONTH_ALIASES.get(m.group(2)[:3])
        if month and pd.notna(year):
            try:
                return pd.Timestamp(year=int(year), month=month, day=int(m.group(1)))
            except ValueError:
                return pd.NaT
        return pd.NaT

    parsed = pd.to_datetime(text, errors="coerce")
    return parsed if pd.notna(parsed) else pd.NaT


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
        .str.replace(r"\s+and\s+", ", ", regex=True)
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
