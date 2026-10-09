"""Parsing for the messy, mixed-format dates in the personal book-tracker sheet.

Shared by scripts/clean_books_data.py (local CSV cleaning) and
utils/sheets_client.py (live Google Sheet sync).
"""
import re

import pandas as pd

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
