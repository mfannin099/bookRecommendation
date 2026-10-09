"""Read the personal book-tracker Google Sheet and pick out the most recently
finished books.

The sheet is shared as "anyone with the link: Viewer", so no Google auth is
needed - Google serves any tab as CSV from a predictable export URL. That
also means the sheet ID is the only thing protecting the data, so it is read
from the environment (GOOGLE_SHEET_ID, loaded from a gitignored .env locally
or an Actions secret in CI) and is never hardcoded, logged, or included in an
error message.

The sheet is messy by design (see CLAUDE.md): ~190 of its rows are older
"want to read" entries with no dates, no year and often no author, while rows
from when detailed tracking began carry a year and dates in mixed formats.
A row counts as tracked if it has a year or a parseable date, so audiobooks
logged with a year but no dates yet are included. The sheet is appended to
chronologically, so "most recent" means "last in sheet order".
parse_date (utils/book_dates.py) resolves day-month dates against the row's
`year` column.
"""
import io
import os

import pandas as pd
import requests
from dotenv import load_dotenv

from utils.book_columns import (
    AUTHOR_COLUMN_ALIASES,
    TITLE_COLUMN_ALIASES,
    dedupe_key,
    find_column,
)
from utils.book_dates import parse_date

SHEET_ID_ENV = "GOOGLE_SHEET_ID"
SHEET_GID_ENV = "GOOGLE_SHEET_GID"  # optional; defaults to the first tab
EXPORT_URL = "https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
REQUEST_TIMEOUT = 30
DEFAULT_BOOKS = 20
MAX_BOOKS = 50  # each book costs live metadata lookups, so cap the look-back


class SheetSyncError(Exception):
    """Raised for any failure to read the sheet. Messages never contain the URL."""


def _export_url() -> str:
    load_dotenv()
    sheet_id = os.environ.get(SHEET_ID_ENV, "").strip()
    if not sheet_id:
        raise SheetSyncError(
            f"{SHEET_ID_ENV} is not set. Put it in a .env file (see .env.example) "
            f"or export it in your environment."
        )
    gid = os.environ.get(SHEET_GID_ENV, "0").strip() or "0"
    return EXPORT_URL.format(sheet_id=sheet_id, gid=gid)


def fetch_sheet() -> pd.DataFrame:
    """Download the sheet tab as a DataFrame, raising SheetSyncError on failure."""
    url = _export_url()
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as e:
        # str(e) embeds the full URL, so report only the exception type.
        raise SheetSyncError(f"Could not reach Google Sheets ({type(e).__name__}).") from None

    if resp.status_code != 200:
        raise SheetSyncError(
            f"Google Sheets returned HTTP {resp.status_code}. Check {SHEET_ID_ENV} "
            f"and that the sheet is shared as 'Anyone with the link: Viewer'."
        )
    # A sheet that is no longer link-shared answers 200 with a sign-in HTML page.
    if "text/csv" not in resp.headers.get("content-type", ""):
        raise SheetSyncError(
            "Google returned a web page instead of CSV - the sheet is probably not "
            "shared as 'Anyone with the link: Viewer'."
        )
    return pd.read_csv(io.StringIO(resp.text))


def _tidy(value) -> str:
    return " ".join(str(value).split()) if pd.notna(value) else ""


def recent_tracked_books(df: pd.DataFrame, n: int = DEFAULT_BOOKS) -> pd.DataFrame:
    """Return the `n` most recent tracked books as a DataFrame with columns
    title, author, end_date (NaT if no end date logged yet), oldest first.

    Tracked = has a year or a parseable start/end date. Rows without a title
    or author are skipped (a lookup without an author is unreliable);
    duplicate title+author pairs keep their last occurrence.
    """
    if not 1 <= n <= MAX_BOOKS:
        raise SheetSyncError(f"n must be between 1 and {MAX_BOOKS} (got {n}).")
    title_col = find_column(df.columns, TITLE_COLUMN_ALIASES)
    author_col = find_column(df.columns, AUTHOR_COLUMN_ALIASES)
    if title_col is None or author_col is None or "end_date" not in df.columns:
        raise SheetSyncError(
            f"Sheet is missing expected columns. Found: {', '.join(map(str, df.columns))}. "
            f"Need a title column, an author column, and 'end_date'."
        )
    years = df["year"] if "year" in df.columns else pd.Series([None] * len(df), index=df.index)
    starts = df["start_date"] if "start_date" in df.columns else pd.Series([None] * len(df), index=df.index)

    end_dates = [parse_date(raw, year) for raw, year in zip(df["end_date"], years)]
    start_dates = [parse_date(raw, year) for raw, year in zip(starts, years)]
    books = pd.DataFrame({
        "title": df[title_col].map(_tidy),
        "author": df[author_col].map(_tidy),
        "end_date": end_dates,
    })
    tracked = years.notna() | pd.Series(end_dates, index=df.index).notna() | pd.Series(start_dates, index=df.index).notna()
    books = books[tracked & (books["title"] != "") & (books["author"] != "")]
    books = books[~books.apply(lambda r: dedupe_key(r["title"], r["author"]), axis=1).duplicated(keep="last")]
    return books.tail(n).reset_index(drop=True)


def fetch_recent_books(n: int = DEFAULT_BOOKS) -> list[tuple[str, str]]:
    """(title, author) pairs for the `n` most recent tracked books."""
    books = recent_tracked_books(fetch_sheet(), n)
    return list(zip(books["title"], books["author"]))
