"""Recommend new books based on your full reading history in
data/profile_library.parquet (built by build_profile_library.py).

Replaces the old Jaccard word-overlap ranking with TF-IDF cosine similarity
against a taste-profile vector (the centroid of your read books), and pulls
candidates from Open Library / Google Books rather than re-searching with the
same query used to rank -- so candidates aren't scored against the exact terms
that found them.

Usage:
    uv run python scripts/recommend_from_profile.py
"""
import os
import re
import string
import sys

import pandas as pd
import requests
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from thefuzz import fuzz

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from metadata import MetadataClient

PROFILE_PATH = "data/profile_library.parquet"
OUTPUT_PATH = "data/profile_recommendations.csv"
OPEN_LIBRARY_SEARCH_URL = "https://openlibrary.org/search.json"

TERMS_IN_SEARCH_QUERY = 10
CANDIDATE_POOL_SIZE = 40
ALREADY_READ_MATCH_SCORE = 85
TOP_N = 15


def strip_punctuation(text):
    return re.sub(f"[{re.escape(string.punctuation)}]", "", str(text))


def load_profile():
    df = pd.read_parquet(PROFILE_PATH)
    df = df.dropna(subset=["description"])
    df["clean_description"] = df["description"].apply(strip_punctuation)
    return df


def build_search_query(profile_df, vectorizer):
    tfidf_matrix = vectorizer.transform(profile_df["clean_description"])
    feature_names = vectorizer.get_feature_names_out()
    scores = tfidf_matrix.sum(axis=0).A1

    # Boost hand-tagged genres (a stronger signal than API-derived subjects).
    genre_terms = set()
    for genres in profile_df["genre"].dropna():
        genre_terms.update(g.strip().lower() for g in str(genres).split(","))

    top_indices = scores.argsort()[-TERMS_IN_SEARCH_QUERY:][::-1]
    top_keywords = [feature_names[i] for i in top_indices]

    query_terms = list(dict.fromkeys(list(genre_terms) + top_keywords))
    return " ".join(query_terms[:TERMS_IN_SEARCH_QUERY])


def fetch_candidates(search_query, exclude_titles):
    try:
        resp = requests.get(
            OPEN_LIBRARY_SEARCH_URL,
            params={"q": search_query, "limit": CANDIDATE_POOL_SIZE},
            timeout=10,
        )
        resp.raise_for_status()
        docs = resp.json().get("docs", [])
    except Exception as e:
        print(f"Open Library candidate search failed: {e}")
        docs = []

    candidates = []
    for doc in docs:
        title = doc.get("title")
        if not title:
            continue
        if any(fuzz.partial_ratio(title.lower(), read.lower()) >= ALREADY_READ_MATCH_SCORE
               for read in exclude_titles):
            continue
        candidates.append({
            "title": title,
            "author": ", ".join(doc.get("author_name", []) or []),
            "key": doc.get("key"),
        })

    return candidates


def enrich_candidates(candidates):
    client = MetadataClient()
    enriched = []
    for c in candidates:
        result = client.fetch(c["title"], c["author"])
        if result is None or not result.get("description"):
            continue
        enriched.append({
            "title": c["title"],
            "author": c["author"],
            "description": result["description"],
        })
    return enriched


def main():
    profile_df = load_profile()
    if profile_df.empty:
        print("No books with descriptions in the profile cache. "
              "Run scripts/build_profile_library.py first.")
        return

    vectorizer = TfidfVectorizer(stop_words="english")
    vectorizer.fit(profile_df["clean_description"])

    search_query = build_search_query(profile_df, vectorizer)
    print(f"Search query: {search_query}")

    already_read = set(profile_df["title"].str.lower())
    candidates = fetch_candidates(search_query, already_read)
    print(f"Found {len(candidates)} candidate books after excluding already-read titles.")

    enriched = enrich_candidates(candidates)
    if not enriched:
        print("No candidates had usable descriptions.")
        return

    candidates_df = pd.DataFrame(enriched)
    candidates_df["clean_description"] = candidates_df["description"].apply(strip_punctuation)

    profile_vector = vectorizer.transform(profile_df["clean_description"]).mean(axis=0)
    profile_vector = pd.DataFrame(profile_vector).values

    candidate_vectors = vectorizer.transform(candidates_df["clean_description"])
    similarities = cosine_similarity(candidate_vectors, profile_vector).flatten()
    candidates_df["similarity"] = similarities

    results = candidates_df.sort_values("similarity", ascending=False).head(TOP_N)
    results = results[["title", "author", "similarity"]]

    print("\nTop recommendations:")
    print(results.to_string(index=False))
    results.to_csv(OUTPUT_PATH, index=False)
    print(f"\nSaved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
