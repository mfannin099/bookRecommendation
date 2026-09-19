"""Book metadata lookup: Open Library first, falling back to Google Books.

Open Library is free/keyless and often has richer subject tags, but frequently
lacks a usable `description` for a given work -- especially for business /
nonfiction titles. When that happens we fall back to Google Books so downstream
TF-IDF steps always have something to work with.
"""
import os
import time
from urllib.parse import quote

import requests
from dotenv import load_dotenv

load_dotenv()
GOOGLE_BOOKS_API_KEY = os.getenv("GOOGLE_BOOKS_API_KEY")

OPEN_LIBRARY_SEARCH_URL = "https://openlibrary.org/search.json"
OPEN_LIBRARY_WORK_URL = "https://openlibrary.org{key}.json"
GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes"


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


def fetch_from_google_books(title, author):
    """Fallback lookup via the Google Books API. Returns a metadata dict or
    None if nothing was found or the result has no usable description."""
    try:
        url = (
            f"{GOOGLE_BOOKS_URL}?q={quote(title)}+inauthor:{quote(author)}"
            f"&key={GOOGLE_BOOKS_API_KEY}&maxResults=1"
        )
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return None

        items = resp.json().get("items", [])
        if not items:
            return None

        info = items[0]["volumeInfo"]
        description = info.get("description")
        if not description:
            return None

        return {
            "title": info.get("title", title),
            "subtitle": info.get("subtitle"),
            "authors": info.get("authors"),
            "publishedDate": info.get("publishedDate"),
            "pageCount": info.get("pageCount"),
            "categories": info.get("categories"),
            "description": description,
            "source": "google_books",
        }
    except Exception as e:
        print(f"Google Books lookup failed for '{title}' by '{author}': {e}")
        return None


def search_open_library_candidates(query, limit=40):
    """Search Open Library for candidate books matching a query string."""
    try:
        resp = requests.get(
            OPEN_LIBRARY_SEARCH_URL, params={"q": query, "limit": limit}, timeout=10
        )
        resp.raise_for_status()
        docs = resp.json().get("docs", [])
    except Exception as e:
        print(f"Open Library candidate search failed: {e}")
        docs = []

    return [
        {"title": d.get("title"), "author": ", ".join(d.get("author_name", []) or [])}
        for d in docs
        if d.get("title")
    ]


class MetadataClient:
    """Fetches book metadata, preferring Open Library and falling back to
    Google Books when Open Library has no usable description."""

    def __init__(self, rate_limit_seconds=1):
        self.rate_limit_seconds = rate_limit_seconds

    def fetch(self, title, author):
        time.sleep(self.rate_limit_seconds)

        result = fetch_from_open_library(title, author)
        if result is not None:
            return result

        return fetch_from_google_books(title, author)
