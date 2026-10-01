"""Book recommendation pipeline.

Builds a taste profile from the user's read books (via metadata_client.py's
Open Library / Wikipedia lookups), searches Open Library for candidate books,
excludes anything already read, and ranks candidates by TF-IDF cosine
similarity against the read-books profile.
"""
import os
import re
import string
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from thefuzz import fuzz

from utils.metadata_client import MetadataClient, search_open_library_candidates


def strip_punctuation(text):
    return re.sub(f"[{re.escape(string.punctuation)}]", "", str(text))


class BookRecommender:

    def __init__(self, books, cache_path="library.parquet",
                 force_run=False, terms_in_search_query=3, candidate_pool_size=40,
                 already_read_match_score=85, top_n=10, max_workers=5,
                 min_similarity=0.05):
        """books: list of (title, author) tuples for the books already read.

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

        self.client = MetadataClient()
        self.library_df = None

    def build_library(self):
        """Fetch metadata for every read book via Open Library / Wikipedia,
        up to max_workers at a time since each lookup is independent and
        I/O-bound."""
        rows = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            for title, author in zip(self.titles_list, self.authors_list):
                print(f"Fetching: {title}")
                future = executor.submit(self.client.fetch, title, author)
                futures[future] = (title, author)

            for future in as_completed(futures):
                title, author = futures[future]
                result = future.result()
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
        """Drop books with no usable description and strip punctuation for TF-IDF."""
        df = self.library_df.copy()
        df = df.dropna(subset=["description"])
        df["clean_description"] = df["description"].apply(strip_punctuation)
        return df

    def build_search_query(self, vectorizer, df):
        """Derive a candidate search query from the top TF-IDF terms across
        all read-book descriptions.

        Open Library's search treats space-separated terms as a strict AND,
        so keep terms_in_search_query small (default 3) - piling on more
        terms collapses the result count to near zero.
        """
        tfidf_matrix = vectorizer.transform(df["clean_description"])
        feature_names = vectorizer.get_feature_names_out()
        scores = tfidf_matrix.sum(axis=0).A1

        top_indices = scores.argsort()[-self.terms_in_search_query:][::-1]
        top_keywords = [feature_names[i] for i in top_indices]
        return " ".join(top_keywords)

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

    def enrich_candidates(self, candidates):
        """Fetch descriptions for candidate books, up to max_workers at a
        time since each lookup is independent and I/O-bound."""
        enriched = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(self.client.fetch, c["title"], c["author"]): c
                       for c in candidates}

            for future in as_completed(futures):
                c = futures[future]
                result = future.result()
                if result is None or not result.get("description"):
                    continue
                enriched.append({
                    "title": c["title"],
                    "author": c["author"],
                    "description": result["description"],
                    "subtitle": result.get("subtitle"),
                })
        return enriched

    def rank_candidates(self, vectorizer, profile_df, candidates):
        """Rank candidates by cosine similarity against the read-books profile.

        Candidates below min_similarity are dropped rather than padding the
        result out to top_n regardless of match quality - a weak keyword
        match (e.g. a candidate that only shares one generic word with the
        profile) is worse than returning fewer, more confident picks."""
        candidates_df = pd.DataFrame(candidates)
        candidates_df["clean_description"] = candidates_df["description"].apply(strip_punctuation)

        profile_vector = vectorizer.transform(profile_df["clean_description"]).mean(axis=0)
        profile_vector = pd.DataFrame(profile_vector).values

        candidate_vectors = vectorizer.transform(candidates_df["clean_description"])
        candidates_df["similarity"] = cosine_similarity(candidate_vectors, profile_vector).flatten()

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
        return candidates_df[["title", "subtitle", "authors", "description", "similarity"]].head(self.top_n)

    def get_recommendations(self):
        """Main method to run the complete recommendation pipeline."""
        self.load_or_build_library()
        profile_df = self.clean_library()

        if profile_df.empty:
            raise ValueError(
                "No metadata could be found for any of your books - can't build recommendations."
            )

        vectorizer = TfidfVectorizer(stop_words="english")
        vectorizer.fit(profile_df["clean_description"])

        search_query = self.build_search_query(vectorizer, profile_df)
        candidates = self.fetch_candidates(search_query)
        enriched = self.enrich_candidates(candidates)

        if not enriched:
            raise ValueError("No candidate books with descriptions were found.")

        return self.rank_candidates(vectorizer, profile_df, enriched)
