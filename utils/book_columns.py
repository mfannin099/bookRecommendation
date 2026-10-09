"""Column-name matching and author/dedupe helpers shared by the Flask upload flow
(main.py) and the Google Sheet sync (utils/sheets_client.py)."""
import re

# Real export tools vary their column naming (StoryGraph uses "Authors"
# plural, LibraryThing often uses "Primary Author", etc.), so match against
# a set of common aliases rather than requiring the exact words.
TITLE_COLUMN_ALIASES = {"title", "book", "book title", "name"}
AUTHOR_COLUMN_ALIASES = {"author", "authors", "author name", "writer"}


def find_column(columns, aliases):
    for col in columns:
        if col.strip().lower() in aliases:
            return col
    return None


def dedupe_key(title, author):
    return (title.strip().lower(), author.strip().lower())


# "A & B", "A and B", "A, B, and C", "A; B" - the ways the tracker sheet (and
# real export tools) join co-authors. \band\b so names like "Alexander" are safe.
_AUTHOR_SEPARATOR_RE = re.compile(r"\s*(?:,|;|&|\band\b)\s*", re.IGNORECASE)


def first_author(authors):
    """The first author of a possibly multi-author string.

    The metadata lookups need one author name: Wikipedia and iTunes require
    the whole author string to appear in the page text / artistName, which a
    combined "A & B" almost never does, while a single co-author does (iTunes
    lists "Jocko Willink & Leif Babin" as one artistName). Open Library's
    author filter is loose, so the first author is enough there too. Returns
    the input unchanged (stripped) when there is nothing to split.
    """
    parts = [p for p in _AUTHOR_SEPARATOR_RE.split(authors or "") if p.strip()]
    return parts[0].strip() if parts else (authors or "").strip()
