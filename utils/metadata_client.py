"""Book metadata lookup: Open Library first, falling back to Wikipedia.

Open Library is free/keyless and often has richer subject tags, but frequently
lacks a usable `description` for a given work -- especially for business /
nonfiction titles. When that happens we fall back to Wikipedia (also free and
keyless) so downstream TF-IDF steps always have something to work with.
"""
import time
from urllib.parse import quote

import requests

OPEN_LIBRARY_SEARCH_URL = "https://openlibrary.org/search.json"
OPEN_LIBRARY_WORK_URL = "https://openlibrary.org{key}.json"
WIKIPEDIA_SEARCH_URL = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"

# Shared across every lookup (and every worker thread in BookRecommender's
# thread pool) so repeated requests to the same host reuse an already-open
# connection instead of paying a fresh TCP+TLS handshake each time. Safe to
# share across threads for simple, independent GETs like these - the
# underlying urllib3 connection pool is internally lock-protected.
_SESSION = requests.Session()

# Wikipedia rejects requests with no descriptive User-Agent (403), per its API
# etiquette policy: https://meta.wikimedia.org/wiki/User-Agent_policy. Applied
# session-wide so every request carries it - harmless for Open Library.
DEFAULT_HEADERS = {"User-Agent": "bookRecommendation/1.0 (local personal project)"}
_SESSION.headers.update(DEFAULT_HEADERS)


def _extract_description(raw):
    if isinstance(raw, dict):
        return raw.get("value")
    return raw


def fetch_from_open_library(title, author):
    """Look up a single book on Open Library. Returns a metadata dict or None
    if no work was found or the work has no usable description."""
    try:
        resp = _SESSION.get(
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

        work_resp = _SESSION.get(OPEN_LIBRARY_WORK_URL.format(key=work_key), timeout=10)
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


def _wikipedia_get(url, params=None, max_retries=3):
    """GET with backoff on Wikipedia's 429 (rate limit), which shows up in
    normal use once a run makes more than a couple hundred requests."""
    resp = None
    for attempt in range(max_retries):
        resp = _SESSION.get(url, params=params, timeout=10)
        if resp.status_code != 429:
            return resp
        time.sleep(int(resp.headers.get("Retry-After", 2**attempt)))
    return resp


def fetch_from_wikipedia(title, author):
    """Fallback lookup via Wikipedia. Searches for the book's page, then reads
    its lead-section extract as the description. Returns a metadata dict or
    None if no matching page is found or the page has no usable extract.

    Wikipedia's free-text search frequently returns an unrelated page for
    lesser-known book titles (TV episodes, films, politicians sharing a word
    or two) rather than no result at all, so a match is only trusted when the
    author's name actually appears in the returned page's extract."""
    if not author:
        return None

    try:
        search_resp = _wikipedia_get(
            WIKIPEDIA_SEARCH_URL,
            params={
                "action": "query",
                "list": "search",
                "srsearch": f"{title} {author} book",
                "format": "json",
                "srlimit": 1,
            },
        )
        search_resp.raise_for_status()
        results = search_resp.json().get("query", {}).get("search", [])
        if not results:
            return None

        page_title = results[0]["title"]
        summary_resp = _wikipedia_get(WIKIPEDIA_SUMMARY_URL.format(title=quote(page_title)))
        if summary_resp.status_code != 200:
            return None

        summary = summary_resp.json()
        description = summary.get("extract")
        if not description:
            return None

        if author.strip().lower() not in description.lower():
            return None

        return {
            "title": summary.get("title", title),
            "subtitle": None,
            "authors": [author] if author else None,
            "publishedDate": None,
            "pageCount": None,
            "categories": None,
            "description": description,
            "source": "wikipedia",
        }
    except Exception as e:
        print(f"Wikipedia lookup failed for '{title}' by '{author}': {e}")
        return None


def search_open_library_candidates(query, limit=40):
    """Search Open Library for candidate books matching a query string."""
    try:
        resp = _SESSION.get(
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
    Wikipedia when Open Library has no usable description."""

    def __init__(self, open_library_pause=0.2, wikipedia_pause=0.5):
        self.open_library_pause = open_library_pause
        self.wikipedia_pause = wikipedia_pause

    def fetch(self, title, author):
        """Open Library has no documented rate limit, so its pause is just a
        light courtesy delay. Wikipedia does rate-limit (see _wikipedia_get's
        429 backoff), so it gets a longer pause to make that less likely to
        trigger in the first place."""
        time.sleep(self.open_library_pause)
        result = fetch_from_open_library(title, author)
        if result is not None:
            return result

        time.sleep(self.wikipedia_pause)
        return fetch_from_wikipedia(title, author)
