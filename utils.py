"""Book recommendation pipeline.

Builds a taste profile from the user's read books (via metadata.py's Open
Library / Google Books lookups), searches Open Library for candidate books,
excludes anything already read, and ranks candidates by TF-IDF cosine
similarity against the read-books profile.
"""
import os
import re
import string

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from thefuzz import fuzz

from metadata import MetadataClient, search_open_library_candidates


def strip_punctuation(text):
    return re.sub(f"[{re.escape(string.punctuation)}]", "", str(text))


class BookRecommender:

    def __init__(self, authors_path, titles_path, cache_path="library.parquet",
                 force_run=False, terms_in_search_query=3, candidate_pool_size=40,
                 already_read_match_score=85, top_n=10):

        self.authors_path = authors_path
        self.titles_path = titles_path
        self.cache_path = cache_path
        self.force_run = force_run
        self.terms_in_search_query = terms_in_search_query
        self.candidate_pool_size = candidate_pool_size
        self.already_read_match_score = already_read_match_score
        self.top_n = top_n

        self.client = MetadataClient()
        self.library_df = None
        self.titles_list = None
        self.authors_list = None

    def read_data(self):
        """Read authors and titles from input files."""
        if not os.path.isfile(self.authors_path):
            raise FileNotFoundError(f"File not found: {self.authors_path}")
        if not os.path.isfile(self.titles_path):
            raise FileNotFoundError(f"File not found: {self.titles_path}")

        with open(self.authors_path, 'r', encoding='utf-8') as file:
            self.authors_list = [line.strip() for line in file if line.strip()]

        with open(self.titles_path, 'r', encoding='utf-8') as file:
            self.titles_list = [line.strip() for line in file if line.strip()]

        return self.authors_list, self.titles_list

    def build_library(self):
        """Fetch metadata for every read book via Open Library / Google Books."""
        rows = []
        for title, author in zip(self.titles_list, self.authors_list):
            print(f"Fetching: {title}")
            result = self.client.fetch(title, author)
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
        self.read_data()

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
        """Search Open Library for candidates and exclude already-read titles."""
        already_read = set(self.titles_list)
        candidates = search_open_library_candidates(search_query, limit=self.candidate_pool_size)

        filtered = []
        for c in candidates:
            title = c["title"]
            if any(fuzz.partial_ratio(title.lower(), read.lower()) >= self.already_read_match_score
                   for read in already_read):
                continue
            filtered.append(c)
        return filtered

    def enrich_candidates(self, candidates):
        """Fetch descriptions for candidate books."""
        enriched = []
        for c in candidates:
            result = self.client.fetch(c["title"], c["author"])
            if result is None or not result.get("description"):
                continue
            enriched.append({
                "title": c["title"],
                "author": c["author"],
                "description": result["description"],
            })
        return enriched

    def rank_candidates(self, vectorizer, profile_df, candidates):
        """Rank candidates by cosine similarity against the read-books profile."""
        candidates_df = pd.DataFrame(candidates)
        candidates_df["clean_description"] = candidates_df["description"].apply(strip_punctuation)

        profile_vector = vectorizer.transform(profile_df["clean_description"]).mean(axis=0)
        profile_vector = pd.DataFrame(profile_vector).values

        candidate_vectors = vectorizer.transform(candidates_df["clean_description"])
        candidates_df["similarity"] = cosine_similarity(candidate_vectors, profile_vector).flatten()

        candidates_df = candidates_df.sort_values("similarity", ascending=False)
        candidates_df["authors"] = candidates_df["author"]
        return candidates_df[["title", "authors"]].head(self.top_n)

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
