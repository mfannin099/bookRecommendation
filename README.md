# Book Recommendation

A Flask app that recommends books based on a list of titles/authors you've read, using the Google Books API and a TF-IDF + Jaccard similarity pipeline.

🚀 Getting Started
This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

Setup:
```bash
uv sync
```

Create a `.env` file with your Google Books API key:
```
GOOGLE_BOOKS_API_KEY=<your key>
```

Run the Flask app:
```bash
uv run python main.py
```

Run the recommender standalone (no web UI):
```bash
uv run python quick_start.py
```

Clean the personal reading-log CSV in `data/`:
```bash
uv run python scripts/clean_books_data.py
```

🛠️ How It Works
The recommendation engine follows a specific data pipeline to ensure relevance:

User Input: Accepts book titles or authors through a Flask frontend.

Data Acquisition: Queries the Google Books API to retrieve metadata (descriptions, categories, etc.).

Data Cleaning: Processes text data to prepare it for similarity analysis.

Similarity Engine: Uses Jaccard Similarity (implemented in utils.py) to compare book attributes and find the closest matches.

Output: Returns a curated list of recommendations back to the user interface.

📁 Key Files
main.py: The core Flask application handling routes and user interaction.

utils.py: The "brains" of the operation. Contains the `BookRecommender` class with logic for API calls, data cleaning, and the recommendation workflow.

quick_start.py: Runs the recommendation pipeline directly from the command line, without the Flask UI.

scripts/clean_books_data.py: Cleans the personal reading-log CSV (`data/Book Tracker - Sheet1.csv`) into standardized `data/books_clean.csv` / `.parquet` files.

data/: Raw and cleaned reading-log CSVs (separate from `library.parquet`, which is the recommender's API-response cache).

notebooks/nltk_playground.ipynb: An exploratory sandbox where NLTK and NLP strategies are tested.

library.parquet: Local data storage for optimized performance during processing.

pyproject.toml / uv.lock: uv-managed project dependencies.

🧪 Tech Stack & Learnings
This project served as a practical application of several data science and web development concepts:

Web Framework: Flask

Natural Language Processing: scikit-learn TF-IDF is used in the live recommendation pipeline to generate search queries; NLTK was explored separately in `notebooks/nltk_playground.ipynb` but isn't part of the live pipeline.

Recommendation Systems: Content-based filtering using Jaccard Similarity.

Data Handling: Pandas and Parquet for efficient data storage.

Dependency Management: uv.
