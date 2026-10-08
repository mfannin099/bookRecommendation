"""Book recommendation pipeline.

Builds a taste profile from the user's read books (via metadata_client.py's
Open Library / Wikipedia lookups), searches Open Library for candidate books,
excludes anything already read, and ranks candidates by TF-IDF cosine
similarity against the read-books profile.
"""
import os
import re
import string
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from thefuzz import fuzz

from utils.metadata_client import (
    MetadataClient,
    search_open_library_candidates,
    search_open_library_subject_candidates,
)

# Generic book-marketing/citation boilerplate that isn't in sklearn's
# standard English stopword list but is common enough across book
# descriptions (especially the iTunes fallback's promotional copy, e.g.
# "...New York Times bestselling author...") to dominate the TF-IDF sum used
# to build the Open Library search query - without these, the query can end
# up being pure noise like "book new times" instead of anything topical.
# The second group is subtler: marketing superlatives that sound topical
# but are plastered on blurbs for any genre - confirmed live when a
# business-reading profile's "visionary" (real, from Steve Jobs/Elon Musk
# bios) matched a William Gibson sci-fi novel whose blurb separately calls
# Gibson "one of the most visionary... writers".
#
# "sector"/"sectors" is a different flavor of the same problem, found while
# verifying the fix above: removing "visionary" let it fill the freed query
# slot, which pulled in a cluster of unrelated healthcare-sector books that
# scored even higher than the original false positive (confirmed: they have
# real category data, just entirely healthcare-tagged - the category-overlap
# boost in rank_candidates correctly contributed nothing, since it can only
# boost real overlaps, not suppress an inflated score from generic shared
# vocabulary). This is a real pattern worth knowing about, not just a
# one-off: removing a contaminating term from this list can let a different,
# equally generic term take its place. Each case has been verified to
# produce a clean result for the profiles tested so far, but this list isn't
# a permanent fix for every future case - see rank_candidates' category-
# overlap boost and CLAUDE.md for the broader context.
BOOK_BOILERPLATE_STOPWORDS = [
    "new", "book", "books", "author", "authors", "times", "york", "press",
    "bestselling", "bestseller",
    "visionary", "groundbreaking", "compelling", "inspiring", "masterful",
    "brilliant", "riveting", "extraordinary", "unforgettable", "captivating",
    "acclaimed",
    "sector", "sectors",
]
STOP_WORDS = list(ENGLISH_STOP_WORDS) + BOOK_BOILERPLATE_STOPWORDS

# Open Library's crowdsourced subject tags mix in call numbers
# ("Bf637.s8 c37 1998"), foreign-language duplicates ("Succès", "Bedrijven"),
# and other noise alongside usable tags like "Leadership" - this keeps only
# tags that look like a plain English phrase.
_USABLE_SUBJECT_RE = re.compile(r"^[A-Za-z][A-Za-z \-']{2,40}$")

# Marketing tags like "New York Times bestseller"/"USA Today bestseller"
# pass the pattern above (they're plain English phrases) but aren't a real
# subject/genre - same kind of boilerplate noise as BOOK_BOILERPLATE_STOPWORDS,
# just checked as a substring here since banning the individual words would
# also reject genuine subjects like "New business enterprises".
_BOILERPLATE_SUBJECT_RE = re.compile(r"bestsell", re.IGNORECASE)


def strip_punctuation(text):
    return re.sub(f"[{re.escape(string.punctuation)}]", "", str(text))


def _is_usable_subject(subject):
    return bool(_USABLE_SUBJECT_RE.match(subject)) and not _BOILERPLATE_SUBJECT_RE.search(subject)


class BookRecommender:

    def __init__(self, books, cache_path="library.parquet",
                 force_run=False, terms_in_search_query=3, candidate_pool_size=40,
                 already_read_match_score=85, top_n=10, max_workers=5,
                 min_similarity=0.05, genre_keywords=None, genre_boost_repeats=5,
                 on_progress=None, subject_count=3, subject_candidate_limit=10):
        """books: list of (title, author) tuples for the books already read.

        subject_count/subject_candidate_limit control the second candidate
        source (fetch_subject_candidates): the subject_count most common
        subject tags across your matched books (e.g. "Leadership",
        "Golf" - from categories/subjects data every source already
        returns but nothing previously used) are each searched via Open
        Library's popularity-ranked subject-browse endpoint, up to
        subject_candidate_limit results apiece. Kept modest (3 x 10 = 30
        raw, before dedup) so this doesn't double the keyword search's
        existing candidate_pool_size=40 and proportionally double
        /recommend's runtime.

        on_progress, if given, is called with a dict at each meaningful step
        (a book/candidate finishing its metadata lookup, or a phase
        starting) so a caller can surface live progress - see _report and
        get_recommendations.

        max_workers caps how many metadata fetches run concurrently. Each
        fetch is I/O-bound (mostly waiting on the network), so this is cheap
        on CPU/memory even on a modest machine - the default of 5 is a
        balance between speed and being polite to the free Open
        Library/Wikipedia APIs. Lower it on a more constrained machine or
        raise it for more speed at the cost of more concurrent API load.

        min_similarity drops candidates whose cosine similarity to the
        read-books profile falls below this floor, rather than always
        padding out to top_n regardless of match quality - see
        rank_candidates.

        genre_keywords optionally steers recommendations toward a genre
        (e.g. ["business", "psychology"]) without changing your actual
        reading list - see clean_library and build_search_query for the two
        places this takes effect. genre_boost_repeats controls how strongly:
        a light touch by default, nudging the profile rather than dominating
        it, so your actual books still drive most of the signal.
        """

        self.titles_list = [title for title, _author in books]
        self.authors_list = [author for _title, author in books]
        self.cache_path = cache_path
        self.force_run = force_run
        self.terms_in_search_query = terms_in_search_query
        self.candidate_pool_size = candidate_pool_size
        self.already_read_match_score = already_read_match_score
        self.top_n = top_n
        self.max_workers = max_workers
        self.min_similarity = min_similarity
        self.genre_keywords = [g.strip().lower() for g in (genre_keywords or []) if g.strip()]
        self.genre_boost_repeats = genre_boost_repeats
        self.on_progress = on_progress
        self.subject_count = subject_count
        self.subject_candidate_limit = subject_candidate_limit

        self.client = MetadataClient()
        self.library_df = None

    def _report(self, phase, **details):
        if self.on_progress:
            self.on_progress({"phase": phase, **details})

    def build_library(self):
        """Fetch metadata for every read book via Open Library / Wikipedia,
        up to max_workers at a time since each lookup is independent and
        I/O-bound."""
        rows = []
        total = len(self.titles_list)
        completed = 0
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            for title, author in zip(self.titles_list, self.authors_list):
                print(f"Fetching: {title}")
                future = executor.submit(self.client.fetch, title, author)
                futures[future] = (title, author)

            for future in as_completed(futures):
                title, author = futures[future]
                result = future.result()
                completed += 1
                self._report("reading_library", completed=completed, total=total,
                             title=title, source=(result.get("source") if result else None))
                if result is None:
                    print(f"  no metadata found for '{title}'")
                    continue
                result["title"] = title
                result["author"] = author
                rows.append(result)

        df = pd.DataFrame(rows)
        df.to_parquet(self.cache_path)
        self.library_df = df
        return df

    def load_or_build_library(self):
        """Load library from cache or build it if needed."""
        if os.path.exists(self.cache_path) and not self.force_run:
            self.library_df = pd.read_parquet(self.cache_path)
        else:
            self.library_df = self.build_library()

        return self.library_df

    def clean_library(self):
        """Drop books with no usable description and strip punctuation for TF-IDF.

        If genre_keywords are set, append them (repeated genre_boost_repeats
        times) to every row's clean_description. This is the one injection
        point for the genre-steering feature: it shifts both the TF-IDF
        vocabulary/IDF used to build the search query (build_search_query)
        and the profile centroid used for ranking (rank_candidates) toward
        the genre, without a separate mechanism for each."""
        df = self.library_df.copy()
        df = df.dropna(subset=["description"])
        df["clean_description"] = df["description"].apply(strip_punctuation)

        if self.genre_keywords:
            boost_text = " " + " ".join(self.genre_keywords * self.genre_boost_repeats)
            df["clean_description"] = df["clean_description"] + boost_text

        return df

    def build_search_query(self, vectorizer, df):
        """Derive a candidate search query from the top TF-IDF terms across
        all read-book descriptions, plus any genre_keywords.

        Open Library's search treats space-separated terms as a strict AND,
        so keep terms_in_search_query small (default 3) - piling on more
        terms collapses the result count to near zero. genre_keywords are
        guaranteed to be included (rather than relying on clean_library's
        repetition alone to make them statistically dominant), so the
        auto-derived term count shrinks to make room for them within the
        same overall budget.
        """
        tfidf_matrix = vectorizer.transform(df["clean_description"])
        feature_names = vectorizer.get_feature_names_out()
        scores = tfidf_matrix.sum(axis=0).A1

        auto_term_count = max(self.terms_in_search_query - len(self.genre_keywords), 1)
        top_indices = scores.argsort()[-auto_term_count:][::-1]
        top_keywords = [feature_names[i] for i in top_indices]

        all_terms = list(dict.fromkeys([*self.genre_keywords, *top_keywords]))
        return " ".join(all_terms)

    def fetch_candidates(self, search_query):
        """Search Open Library for candidates, excluding already-read titles
        and near-duplicates of a candidate already kept (Open Library often
        returns the same work twice under slightly different editions/casing,
        e.g. "The Man Who Loved China" and "the man who loved china")."""
        already_read = set(self.titles_list)
        candidates = search_open_library_candidates(search_query, limit=self.candidate_pool_size)

        filtered = []
        kept_titles = []
        for c in candidates:
            title = c["title"]
            if any(fuzz.partial_ratio(title.lower(), read.lower()) >= self.already_read_match_score
                   for read in already_read):
                continue
            if any(fuzz.ratio(title.lower(), kept.lower()) >= self.already_read_match_score
                   for kept in kept_titles):
                continue
            filtered.append(c)
            kept_titles.append(title)
        return filtered

    def top_subjects(self, profile_df):
        """Count usable subject/category tags (see _is_usable_subject)
        across every matched book's categories column, and return the
        subject_count most common - these feed fetch_subject_candidates as
        a second, popularity-ranked candidate source."""
        counts = Counter()
        for categories in profile_df["categories"]:
            # categories is a plain list fresh from build_library(), but a
            # numpy array once round-tripped through the library.parquet
            # cache (force_run=False) - `if not categories` is ambiguous
            # for a multi-element array, so check length explicitly.
            if categories is None or len(categories) == 0:
                continue
            for subject in categories:
                subject = subject.strip()
                if _is_usable_subject(subject):
                    counts[subject] += 1
        return [subject for subject, _count in counts.most_common(self.subject_count)]

    def fetch_subject_candidates(self, subjects):
        """Discover candidates via Open Library's subject-browse endpoint
        (search_open_library_subject_candidates), one call per subject,
        excluding already-read titles - same filtering as fetch_candidates,
        kept separate since this method's raw candidates come from a
        different source (per-subject, not a single keyword query)."""
        already_read = set(self.titles_list)
        filtered = []
        kept_titles = []
        for subject in subjects:
            candidates = search_open_library_subject_candidates(
                subject, limit=self.subject_candidate_limit
            )
            for c in candidates:
                title = c["title"]
                if any(fuzz.partial_ratio(title.lower(), read.lower()) >= self.already_read_match_score
                       for read in already_read):
                    continue
                if any(fuzz.ratio(title.lower(), kept.lower()) >= self.already_read_match_score
                       for kept in kept_titles):
                    continue
                filtered.append(c)
                kept_titles.append(title)
        return filtered

    def _merge_candidates(self, *candidate_lists):
        """Combine candidate lists from different sources (keyword search,
        subject search), dropping anything fuzzy-matching a candidate
        already kept - the same work can surface from both sources."""
        merged = []
        kept_titles = []
        for candidates in candidate_lists:
            for c in candidates:
                title = c["title"]
                if any(fuzz.ratio(title.lower(), kept.lower()) >= self.already_read_match_score
                       for kept in kept_titles):
                    continue
                merged.append(c)
                kept_titles.append(title)
        return merged

    def enrich_candidates(self, candidates):
        """Fetch descriptions for candidate books, up to max_workers at a
        time since each lookup is independent and I/O-bound."""
        enriched = []
        total = len(candidates)
        completed = 0
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(self.client.fetch, c["title"], c["author"]): c
                       for c in candidates}

            for future in as_completed(futures):
                c = futures[future]
                result = future.result()
                completed += 1
                self._report("checking_candidates", completed=completed, total=total,
                             title=c["title"], source=(result.get("source") if result else None))
                if result is None or not result.get("description"):
                    continue
                enriched.append({
                    "title": c["title"],
                    "author": c["author"],
                    "description": result["description"],
                    "subtitle": result.get("subtitle"),
                    "categories": result.get("categories"),
                })
        return enriched

    def _matched_subjects(self, categories, subjects):
        """Which of a candidate's categories case-insensitively match the
        profile's top_subjects (case preserved from `subjects`) - used by
        rank_candidates both as a light secondary ranking signal (its
        count) and, surfaced to the user, as part of "why was this
        recommended"."""
        if not categories or not subjects:
            return []
        subject_lookup = {s.lower(): s for s in subjects}
        matched = []
        for c in categories:
            if isinstance(c, str) and c.strip().lower() in subject_lookup:
                matched.append(subject_lookup[c.strip().lower()])
        return matched

    def _top_matched_terms(self, feature_names, contributions, limit=4):
        """The feature names with the largest positive contribution to a
        candidate's cosine similarity against the profile centroid - i.e.
        which shared vocabulary actually drove the match, used to show
        "why was this recommended" alongside matched_subjects."""
        top_indices = contributions.argsort()[::-1][:limit]
        return [feature_names[i] for i in top_indices if contributions[i] > 0]

    def rank_candidates(self, vectorizer, profile_df, candidates, subjects=None):
        """Rank candidates by cosine similarity against the read-books profile.

        A candidate whose own categories overlap the profile's subjects
        (top_subjects) gets a modest similarity boost - a light touch
        (15% per matching category), nudging rather than overriding the
        text-similarity signal, in the same spirit as genre_boost_repeats.
        This doesn't catch every surface-vocabulary false positive (some
        candidates have no category data at all to compare), but helps for
        ones that do.

        Candidates below min_similarity are dropped rather than padding the
        result out to top_n regardless of match quality - a weak keyword
        match (e.g. a candidate that only shares one generic word with the
        profile) is worse than returning fewer, more confident picks.

        Also computes matched_terms/matched_subjects per surviving
        candidate - the shared TF-IDF vocabulary and shared categories that
        actually drove its score, surfaced on the recommendations page so
        a pick isn't just a bare, unexplained similarity number."""
        candidates_df = pd.DataFrame(candidates)
        candidates_df["clean_description"] = candidates_df["description"].apply(strip_punctuation)

        profile_vector = vectorizer.transform(profile_df["clean_description"]).mean(axis=0)
        profile_vector = pd.DataFrame(profile_vector).values

        candidate_vectors = vectorizer.transform(candidates_df["clean_description"])
        candidates_df["similarity"] = cosine_similarity(candidate_vectors, profile_vector).flatten()

        # Elementwise product of each candidate's vector with the profile
        # centroid gives each term's contribution to that candidate's raw
        # cosine similarity - the same vectors already driving the score
        # above, just inspected per-term instead of summed.
        feature_names = vectorizer.get_feature_names_out()
        contributions = candidate_vectors.toarray() * profile_vector.flatten()
        candidates_df["matched_terms"] = [
            self._top_matched_terms(feature_names, contributions[i])
            for i in range(contributions.shape[0])
        ]

        matched_subjects = candidates_df["categories"].apply(lambda cats: self._matched_subjects(cats, subjects))
        candidates_df["matched_subjects"] = matched_subjects
        candidates_df["similarity"] = candidates_df["similarity"] * (1 + 0.15 * matched_subjects.apply(len))

        candidates_df = candidates_df[candidates_df["similarity"] >= self.min_similarity]
        if candidates_df.empty:
            raise ValueError(
                "No candidates were similar enough to your reading profile to recommend confidently."
            )

        candidates_df = candidates_df.sort_values("similarity", ascending=False)
        candidates_df["authors"] = candidates_df["author"]
        candidates_df["description"] = candidates_df["description"].apply(
            lambda d: d if len(d) <= 240 else d[:240].rsplit(" ", 1)[0] + "..."
        )
        return candidates_df[[
            "title", "subtitle", "authors", "description", "similarity",
            "matched_terms", "matched_subjects",
        ]].head(self.top_n)

    def get_recommendations(self):
        """Main method to run the complete recommendation pipeline."""
        self._report("reading_library", completed=0, total=len(self.titles_list), title=None, source=None)
        self.load_or_build_library()
        profile_df = self.clean_library()

        # Exposed for the caller to show "N of M books matched" - how many
        # of the submitted books actually had a usable description to build
        # the taste profile from, vs. how many were submitted.
        self.total_book_count = len(self.titles_list)
        self.matched_book_count = len(profile_df)

        if profile_df.empty:
            raise ValueError(
                "No metadata could be found for any of your books - can't build recommendations."
            )

        vectorizer = TfidfVectorizer(stop_words=STOP_WORDS)
        vectorizer.fit(profile_df["clean_description"])

        search_query = self.build_search_query(vectorizer, profile_df)
        subjects = self.top_subjects(profile_df)
        self._report("searching_open_library", query=search_query, subjects=subjects)
        keyword_candidates = self.fetch_candidates(search_query)
        subject_candidates = self.fetch_subject_candidates(subjects) if subjects else []
        candidates = self._merge_candidates(keyword_candidates, subject_candidates)
        self._report("checking_candidates", completed=0, total=len(candidates), title=None, source=None)
        enriched = self.enrich_candidates(candidates)

        if not enriched:
            raise ValueError("No candidate books with descriptions were found.")

        self._report("ranking")
        return self.rank_candidates(vectorizer, profile_df, enriched, subjects)
