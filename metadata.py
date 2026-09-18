"""Book metadata lookup: Open Library first, falling back to Google Books.

Open Library is free/keyless and often has richer subject tags, but frequently
lacks a usable `description` for a given work -- especially for business /
nonfiction titles. When that happens we fall back to the existing Google Books
lookup in `utils.py` so downstream TF-IDF steps always have something to work with.
"""
import time

import requests

from utils import BookRecommender

OPEN_LIBRARY_SEARCH_URL = "https://openlibrary.org/search.json"
OPEN_LIBRARY_WORK_URL = "https://openlibrary.org{key}.json"


def _extract_description(raw):
    if isinstance(raw, dict):
        return raw.get("value")
    return raw


def fetch_from_open_library(title, author):
    """Look up a single book on Open Library. Returns a metadata dict or None
    if no work was found or the work has no usable description."""
    try:
        resp = requests.get(
            OPEN_LIBRARY_SEARCH_URL,
            params={"title": title, "author": author, "limit": 1},
            timeout=10,
        )
        resp.raise_for_status()
        docs = resp.json().get("docs", [])
        if not docs:
            return None

        doc = docs[0]
        work_key = doc.get("key")
        if not work_key:
            return None

        work_resp = requests.get(OPEN_LIBRARY_WORK_URL.format(key=work_key), timeout=10)
        work_resp.raise_for_status()
        work = work_resp.json()

        description = _extract_description(work.get("description"))
        if not description:
            return None

        return {
            "title": doc.get("title", title),
            "subtitle": doc.get("subtitle"),
            "authors": doc.get("author_name"),
            "publishedDate": str(doc.get("first_publish_year") or ""),
            "pageCount": doc.get("number_of_pages_median"),
            "categories": work.get("subjects"),
            "description": description,
            "source": "open_library",
        }
    except Exception as e:
        print(f"Open Library lookup failed for '{title}' by '{author}': {e}")
        return None


class MetadataClient:
    """Fetches book metadata, preferring Open Library and falling back to
    Google Books when Open Library has no usable description."""

    def __init__(self, rate_limit_seconds=1):
        self.rate_limit_seconds = rate_limit_seconds
        # Reuse the existing Google Books call rather than duplicating it.
        self._google_fallback = BookRecommender(authors_path="", titles_path="")

    def fetch(self, title, author):
        time.sleep(self.rate_limit_seconds)

        result = fetch_from_open_library(title, author)
        if result is not None:
            return result

        google_df = self._google_fallback.fetch_book_from_google(title, author)
        if google_df.empty:
            return None

        row = google_df.iloc[0].to_dict()
        row["source"] = "google_books"
        return row
