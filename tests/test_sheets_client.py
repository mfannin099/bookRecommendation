"""Tests for the pure row-selection / naming logic behind scripts/sync_from_sheet.py.

No network: recent_tracked_books takes a DataFrame, so a small hand-built
frame stands in for the Google Sheet export.
"""
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from sync_from_sheet import output_path  # noqa: E402
from utils.book_columns import first_author  # noqa: E402
from utils.book_dates import parse_date  # noqa: E402
from utils.sheets_client import MAX_BOOKS, SheetSyncError, recent_tracked_books, validate_n  # noqa: E402

COLUMNS = ["title", "author", "start_date", "end_date", "year"]


def sheet(*rows):
    return pd.DataFrame(rows, columns=COLUMNS)


def titles(df):
    return list(df["title"])


def test_undated_want_to_read_rows_are_ignored():
    df = sheet(
        ("Old Wishlist Book", "Someone", None, None, None),
        ("Read Book", "Author A", "1-Jan", "9-Jan", 2026),
    )
    assert titles(recent_tracked_books(df)) == ["Read Book"]


def test_row_with_year_but_no_dates_counts_as_tracked():
    df = sheet(
        ("Finished", "Author A", "1-Jan", "9-Jan", 2026),
        ("Audiobook In Progress", "Author B", None, None, 2026),
    )
    result = recent_tracked_books(df)
    assert titles(result) == ["Finished", "Audiobook In Progress"]
    assert pd.isna(result["end_date"].iloc[1])


def test_keeps_sheet_order_and_takes_last_n():
    df = sheet(*[(f"Book {i}", "A", None, f"{i}-Jan", 2026) for i in range(1, 11)])
    assert titles(recent_tracked_books(df, n=3)) == ["Book 8", "Book 9", "Book 10"]


def test_rows_missing_title_or_author_are_dropped():
    df = sheet(
        ("No Author", None, None, "1-Jan", 2026),
        (None, "No Title", None, "2-Jan", 2026),
        ("Complete", "Author", None, "3-Jan", 2026),
    )
    assert titles(recent_tracked_books(df)) == ["Complete"]


def test_duplicates_are_case_and_whitespace_insensitive_and_keep_last():
    df = sheet(
        ("Dune", "Frank Herbert", None, "1-Jan", 2026),
        ("Other", "Someone", None, "2-Jan", 2026),
        ("  dune ", "FRANK HERBERT", None, "3-Jan", 2026),
    )
    result = recent_tracked_books(df)
    assert titles(result) == ["Other", "dune"]
    assert result["end_date"].iloc[-1] == pd.Timestamp("2026-01-03")


def test_column_aliases_are_matched():
    df = pd.DataFrame(
        [("Book", "Auth", "1-Jan", 2026)], columns=["Book Title", "Authors", "end_date", "year"]
    )
    assert titles(recent_tracked_books(df)) == ["Book"]


def test_missing_required_columns_raises():
    with pytest.raises(SheetSyncError, match="missing expected columns"):
        recent_tracked_books(pd.DataFrame({"foo": [1]}))


@pytest.mark.parametrize("n", [0, -1, MAX_BOOKS + 1])
def test_out_of_range_n_is_rejected(n):
    with pytest.raises(SheetSyncError):
        validate_n(n)
    with pytest.raises(SheetSyncError):
        recent_tracked_books(sheet(("B", "A", None, "1-Jan", 2026)), n=n)


def test_max_n_is_accepted():
    assert validate_n(MAX_BOOKS) == MAX_BOOKS


@pytest.mark.parametrize(
    "raw, year, expected",
    [
        ("13-Feb", 2026, "2026-02-13"),
        ("6-Sept", 2026, "2026-09-06"),  # four-letter month, as written in the sheet
        ("6/16/25", None, "2025-06-16"),
        ("early jan", 2026, "2026-01-05"),
    ],
)
def test_parse_date_handles_sheet_formats(raw, year, expected):
    assert parse_date(raw, year) == pd.Timestamp(expected)


def test_parse_date_blank_and_missing_year_are_nat():
    assert pd.isna(parse_date(None, 2026))
    assert pd.isna(parse_date("13-Feb", None))


def test_output_path_with_genres():
    name = output_path(["machine learning", "data", "business"], date(2026, 10, 9)).name
    assert name == "matt_book_recommendations_2026-10-09_machine-learning_data_business.csv"


def test_output_path_without_genres_and_unsafe_characters():
    assert output_path([], date(2026, 10, 9)).name == "matt_book_recommendations_2026-10-09.csv"
    assert output_path(["Sci-Fi / Space!"], date(2026, 10, 9)).name.endswith("_sci-fi-space.csv")


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Jocko Willink and Leif Babin", "Jocko Willink"),
        ("Benoit Mandelbrot & Richard Hudson", "Benoit Mandelbrot"),
        ("Steve Phillips, Ryan Barry, Stephan Gans, and Kate Schardt", "Steve Phillips"),
        ("T.J Tomasi and Mike Adams", "T.J Tomasi"),
        ("A. One; B. Two", "A. One"),
        ("Alexander McCall Smith", "Alexander McCall Smith"),  # "and" inside a name is not a separator
        ("Brandon Sanderson", "Brandon Sanderson"),
        ("  Dan Heath  ", "Dan Heath"),
        ("Many Authors", "Many Authors"),
        ("", ""),
        (None, ""),
    ],
)
def test_first_author(raw, expected):
    assert first_author(raw) == expected
