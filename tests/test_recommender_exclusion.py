"""Offline tests for excluding already-tracked sheet books from recommendations."""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils import recommender  # noqa: E402
from utils.recommender import BookRecommender, _is_same_book  # noqa: E402
from utils.sheets_client import recent_tracked_books, tracked_books  # noqa: E402


def make(exclude):
    return BookRecommender(books=[("Profile Book", "Someone")], exclude_books=exclude)


def cand(title, author):
    return {"title": title, "author": author}


def test_exact_title_excluded_regardless_of_author():
    assert _is_same_book("Atomic Habits", "James Clear", "atomic habits", "", 85)


def test_subtitle_is_ignored():
    assert _is_same_book("Atomic Habits: An Easy Way", "James Clear", "Atomic Habits", "James Clear", 85)


def test_short_title_substring_needs_matching_author():
    # "Dune" is contained in the candidate title; a different author must not exclude it.
    assert not _is_same_book("Dune Buggy Racing", "Joe Smith", "Dune", "Frank Herbert", 85)
    assert _is_same_book("Dune Messiah Edition", "Frank Herbert", "Dune", "Frank Herbert", 85)


def test_fetch_candidates_drops_excluded_and_keeps_replacements(monkeypatch):
    monkeypatch.setattr(recommender, "search_open_library_candidates", lambda q, limit: [
        cand("Already On Sheet", "Jane Doe"),
        cand("Fresh Pick", "Alan Poe"),
    ])
    rec = make([("Already On Sheet", "Jane Doe")])
    assert [c["title"] for c in rec.fetch_candidates("q")] == ["Fresh Pick"]
    assert rec.excluded_titles == ["Already On Sheet"]


def test_no_exclusions_changes_nothing(monkeypatch):
    monkeypatch.setattr(recommender, "search_open_library_candidates", lambda q, limit: [
        cand("Already On Sheet", "Jane Doe"),
    ])
    rec = make(None)
    assert len(rec.fetch_candidates("q")) == 1
    assert rec.excluded_titles == []


def test_tracked_books_ignores_want_to_read_and_is_uncapped():
    df = pd.DataFrame(
        [("Wishlist", "A", None, None, None)]
        + [(f"Book {i}", f"Author {i}", "1-Jan", "9-Jan", 2026) for i in range(30)],
        columns=["title", "author", "start_date", "end_date", "year"],
    )
    assert len(tracked_books(df)) == 30
    assert "Wishlist" not in set(tracked_books(df)["title"])
    assert len(recent_tracked_books(df, 5)) == 5
