"""Column-name matching and dedupe helpers shared by the Flask upload flow
(main.py) and the Google Sheet sync (utils/sheets_client.py)."""

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
